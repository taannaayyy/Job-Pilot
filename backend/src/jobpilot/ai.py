"""The AI model that reads job descriptions, chosen by the user: none (dictionary only), a local
model through Ollama, any OpenAI-compatible API (OpenAI, OpenRouter, Groq, Gemini, LM Studio...),
Claude with an API key, or Claude Code (the user's Claude subscription, no key). Settings,
including API keys, live in a file next to the database that only the user can read."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import anthropic

from jobpilot.models import Importance
from jobpilot import taxonomy

PROVIDERS = ("none", "ollama", "openai", "anthropic", "claude_code")
LABELS = {
    "none": "Dictionary only", "ollama": "Ollama", "openai": "OpenAI-compatible",
    "anthropic": "Claude", "claude_code": "Claude Code",
}
# model_decides: the model, not the dictionary's section rules, says whether a skill the
# dictionary found is a must or a nice to have. Off for small local models, which judge it badly.
DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434", "model": "", "model_decides": False},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "", "api_key": "", "model_decides": True},
    "anthropic": {"model": "claude-opus-5-5", "api_key": "", "model_decides": True},
    # Empty model and effort: Claude Code's own default.
    "claude_code": {"path": "", "model": "claude-opus-5-5", "effort": "medium", "model_decides": True},
}
TIMEOUT = 300  # local models on a laptop can take minutes for a long posting


class AIError(Exception):
    """Something the user can fix: the model isn't running, the key is wrong..."""


@dataclass(frozen=True)
class ModelItem:
    name: str
    group: str  # a path from the tree, "Technologies › Cloud & infrastructure"
    importance: Importance
    evidence: str
    parent: str = ""
    min_years: int | None = None
    max_years: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class Group:
    path: str
    description: str


SEP = " › "


def default_tree() -> list[Group]:
    """The starting tree, for when there is no database (tests, the tune tool on a text file)."""
    names = {}
    groups = []
    keys_with_children = {parent for _, _, _, parent, _ in taxonomy.flatten() if parent}
    for key, name, description, parent, _ in taxonomy.flatten():
        names[key] = (names[parent] + SEP if parent else "") + name
        if key not in keys_with_children:
            groups.append(Group(names[key], description))
    return groups


def _nullable_int():
    return {"anyOf": [{"type": "integer"}, {"type": "null"}]}


def schema(tree: list[Group]) -> dict:
    return {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "group": {"type": "string", "enum": [g.path for g in tree]},
                        "importance": {"type": "string", "enum": ["must", "nice"]},
                        "evidence": {"type": "string"},
                        "parent": {"type": "string"},
                        "min_years": _nullable_int(),
                        "max_years": _nullable_int(),
                        "detail": {"type": "string"},
                    },
                    "required": ["name", "group", "importance", "evidence", "parent", "min_years", "max_years", "detail"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    }


SCHEMA = schema(default_tree())

# The rules; the user's tree is put in front of them (prompt()).
RULES = """Rules:
- One item per skill or technology: "PyTorch and Hugging Face" is two items.
- name: the skill itself in 1 to 4 words, in the posting's words ("PyTorch", "RAG", "Model training").
  Never a sentence, never "Experience with ...".
- group: what the item is, not how the posting words it. "Hands-on experience with model training" is
  Model training in machine learning; "strong analytical thinking" is a soft skill.
- parent: the technology it belongs to, if any (pandas: Python, SageMaker: AWS, pgvector: Vector databases); else "".
- min_years, max_years: the years asked for this item ("3-5 years of Python": 3 and 5 on Python; "2+ years
  with SQL": 2 and null on SQL). Years not about one skill: an item "Professional experience" in the experience
  group. Otherwise null.
- importance: "nice" when the posting says plus, nice to have, preferred, bonus or advantage, or lists it apart
  from the main requirements (for example after the duties); otherwise "must".
- Degrees: one item per degree level ("Bachelor's degree", "Master's degree", "PhD") with the accepted fields of
  study in detail. "BSc or MSc" means the Bachelor's is a must and the Master's is nice. detail is "" otherwise.
- Only what a candidate must know or have, never the tasks of the job: "Monitor model performance" and
  "Prepare reports" are tasks. From a task, take only a skill it names ("deploy with Docker": Docker).
- evidence: the short phrase from the posting it comes from.
- Leave out benefits and anything about the company itself.
"""


def prompt(tree: list[Group]) -> str:
    groups = "\n".join(f"- {g.path}: {g.description}" if g.description else f"- {g.path}" for g in tree)
    return (
        "List everything this job posting asks of a candidate.\n\n"
        f"File every item in exactly one of these groups (write the group exactly as shown):\n{groups}\n\n"
        f"{RULES}\nJob posting:\n"
    )


def _int(value) -> int | None:
    return value if isinstance(value, int) and 0 < value <= 30 else None


def _parse(text: str, tree: list[Group] | None = None) -> list[ModelItem]:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise AIError("The model didn't answer in the expected format. Try another model.") from e
    paths = {g.path for g in tree} if tree else None
    items = []
    for raw in data.get("requirements", []) if isinstance(data, dict) else []:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            continue
        group = str(raw.get("group") or "")
        if paths is not None and group not in paths:
            group = ""  # the app files it as unsorted; the user can move it
        importance = Importance.NICE if raw.get("importance") == "nice" else Importance.MUST
        items.append(ModelItem(
            str(raw["name"]).strip()[:200], group, importance, str(raw.get("evidence") or "")[:300],
            str(raw.get("parent") or "").strip()[:200], _int(raw.get("min_years")), _int(raw.get("max_years")),
            str(raw.get("detail") or "").strip()[:300],
        ))
    return items


def _http_json(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def _http_error(e: urllib.error.HTTPError) -> str:
    try:
        body = json.load(e)
        detail = body.get("error")
        detail = detail.get("message") if isinstance(detail, dict) else detail
    except (ValueError, AttributeError):
        detail = None
    return f"{e.code}: {detail}" if detail else f"Error {e.code}"


class Provider:
    name = "none"

    def __init__(self, config: dict):
        self.config = config

    @property
    def model(self) -> str:
        return self.config.get("model", "")

    @property
    def model_decides(self) -> bool:
        return bool(self.config.get("model_decides", False))

    def describe(self) -> str:
        return LABELS[self.name] + (f" {self.model}" if self.model else "")

    def extract(self, text: str, tree: list[Group] | None = None) -> list[ModelItem]:
        return []

    def chat(self, system: str, messages: list[dict]) -> str:
        """A free-form conversation (the tree recommendations). messages: [{"role", "content"}]."""
        raise AIError("Choose an AI model in the AI settings first.")

    def models(self) -> list[str]:
        return []


class Ollama(Provider):
    name = "ollama"

    @property
    def base(self) -> str:
        return (self.config.get("base_url") or DEFAULTS["ollama"]["base_url"]).rstrip("/")

    def models(self) -> list[str]:
        """Installed models that can write text; embedding models (e.g. bge-m3) can't read a posting."""
        try:
            tags = _http_json(f"{self.base}/api/tags", timeout=3)
        except (OSError, ValueError) as e:
            raise AIError("Ollama isn't running. Open the Ollama app, or choose another model.") from e
        return sorted(m["name"] for m in tags.get("models", []) if self._can_chat(m["name"]))

    def _can_chat(self, name: str) -> bool:
        try:
            capabilities = _http_json(f"{self.base}/api/show", {"model": name}, timeout=5).get("capabilities")
        except (OSError, ValueError):
            return True  # older Ollama: no way to tell
        return capabilities is None or "completion" in capabilities

    @property
    def model(self) -> str:
        # No model chosen: the first one installed, so a fresh install works without settings.
        if not self.config.get("model"):
            installed = self.models()
            if not installed:
                raise AIError("Ollama has no models yet. Run `ollama pull qwen2.5:3b` in Terminal, or choose another model.")
            self.config = {**self.config, "model": installed[0]}
        return self.config["model"]

    def _chat(self, messages: list[dict], fmt: dict | None = None) -> str:
        body = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0}}
        if fmt:
            body["format"] = fmt
        try:
            res = _http_json(f"{self.base}/api/chat", body)
        except urllib.error.HTTPError as e:
            raise AIError(f"Ollama: {_http_error(e)}") from e
        except OSError as e:
            raise AIError("Ollama isn't running. Open the Ollama app, or choose another model.") from e
        return res.get("message", {}).get("content", "")

    def extract(self, text: str, tree: list[Group] | None = None) -> list[ModelItem]:
        tree = tree or default_tree()
        return _parse(self._chat([{"role": "user", "content": prompt(tree) + text}], schema(tree)), tree)

    def chat(self, system: str, messages: list[dict]) -> str:
        return self._chat([{"role": "system", "content": system}, *messages])


class OpenAICompatible(Provider):
    """Any server with the OpenAI chat completions API."""

    name = "openai"

    @property
    def base(self) -> str:
        return (self.config.get("base_url") or DEFAULTS["openai"]["base_url"]).rstrip("/")

    def _headers(self) -> dict:
        key = self.config.get("api_key")
        return {"Authorization": f"Bearer {key}"} if key else {}

    def models(self) -> list[str]:
        try:
            res = _http_json(f"{self.base}/models", headers=self._headers(), timeout=10)
        except urllib.error.HTTPError as e:
            raise AIError(f"Couldn't list models: {_http_error(e)}") from e
        except (OSError, ValueError) as e:
            raise AIError(f"Couldn't reach {self.base}") from e
        return sorted(m["id"] for m in res.get("data", []) if isinstance(m, dict) and "id" in m)

    def _post(self, body: dict) -> dict:
        try:
            return _http_json(f"{self.base}/chat/completions", body, self._headers())
        except urllib.error.HTTPError as e:
            raise AIError(_http_error(e)) from e
        except OSError as e:
            raise AIError(f"Couldn't reach {self.base}") from e

    def chat(self, system: str, messages: list[dict]) -> str:
        if not self.model:
            raise AIError("Choose a model in the AI settings.")
        res = self._post({"model": self.model, "messages": [{"role": "system", "content": system}, *messages]})
        try:
            return res["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise AIError("The model sent an unexpected answer.") from e

    def extract(self, text: str, tree: list[Group] | None = None) -> list[ModelItem]:
        if not self.model:
            raise AIError("Choose a model in the AI settings.")
        tree = tree or default_tree()
        request, json_schema = prompt(tree), schema(tree)
        messages = [{"role": "user", "content": request + text}]
        body = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "requirements", "schema": json_schema, "strict": True}},
        }
        try:
            res = _http_json(f"{self.base}/chat/completions", body, self._headers())
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise AIError(_http_error(e)) from e
            # Servers without JSON schema support still take plain JSON mode.
            body["response_format"] = {"type": "json_object"}
            body["messages"] = [{"role": "user", "content": request + text + "\n\nAnswer with JSON matching this schema:\n" + json.dumps(json_schema)}]
            try:
                res = _http_json(f"{self.base}/chat/completions", body, self._headers())
            except urllib.error.HTTPError as e2:
                raise AIError(_http_error(e2)) from e2
        except OSError as e:
            raise AIError(f"Couldn't reach {self.base}") from e
        try:
            return _parse(res["choices"][0]["message"]["content"] or "", tree)
        except (KeyError, IndexError, TypeError) as e:
            raise AIError("The model sent an unexpected answer.") from e


class Claude(Provider):
    name = "anthropic"

    def _client(self) -> anthropic.Anthropic:
        if not self.config.get("api_key"):
            raise AIError("Paste your Claude API key in the AI settings.")
        return anthropic.Anthropic(api_key=self.config["api_key"], timeout=TIMEOUT, max_retries=2)

    def models(self) -> list[str]:
        try:
            return [m.id for m in self._client().models.list(limit=100)]
        except anthropic.AuthenticationError as e:
            raise AIError("The Claude API key is wrong.") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Couldn't reach the Claude API. Check the internet connection.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude API: {e.message}") from e

    def chat(self, system: str, messages: list[dict]) -> str:
        return self._create(system=system, messages=messages)

    def extract(self, text: str, tree: list[Group] | None = None) -> list[ModelItem]:
        tree = tree or default_tree()
        return _parse(self._create(
            messages=[{"role": "user", "content": prompt(tree) + text}],
            output_config={"format": {"type": "json_schema", "schema": schema(tree)}},
        ), tree)

    def _create(self, **kwargs) -> str:
        try:
            response = self._client().messages.create(
                model=self.model or DEFAULTS["anthropic"]["model"], max_tokens=16000, **kwargs
            )
        except anthropic.AuthenticationError as e:
            raise AIError("The Claude API key is wrong.") from e
        except anthropic.NotFoundError as e:
            raise AIError(f"Claude has no model called {self.model}.") from e
        except anthropic.RateLimitError as e:
            raise AIError("Claude API rate limit reached. Try again in a minute.") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Couldn't reach the Claude API. Check the internet connection.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude API: {e.message}") from e
        if response.stop_reason == "refusal":
            raise AIError("Claude declined to read this posting.")
        if response.stop_reason == "max_tokens":
            raise AIError("The answer was cut off. Try again.")
        return "".join(b.text for b in response.content if b.type == "text")


# An app opened from /Applications doesn't get the shell's PATH, so `which` alone can miss it.
_CLAUDE_PLACES = ("~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude")
SYSTEM = "You read job postings and list what they require of a candidate, as structured data."
# How long the model thinks before answering; more takes longer and uses more of the plan.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_CODE_MODELS = [
    ("claude-opus-5-5", "Opus 5.5"),
    ("claude-sonnet-5-5", "Sonnet 5.5"),
    ("claude-fable-5-1", "Fable 5.1"),
    ("claude-haiku-5-5", "Haiku 5.5"),
    ("claude-haiku-4-5", "Haiku 4.5"),
    ("claude-sonnet-5", "Sonnet 5"),
]


def _run_cli(cmd: list[str], prompt: str, cwd: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd, env=env)


class ClaudeCode(Provider):
    """The user's own Claude Code, run headless: no API key, it uses their Claude subscription.
    It runs in an empty folder with no tools, MCP servers or settings, so it can only read the
    posting it is given, and leaves no sessions behind."""

    name = "claude_code"

    def binary(self) -> str:
        path = os.path.expanduser(self.config.get("path") or "")
        if path:
            if os.access(path, os.X_OK):
                return path
            raise AIError(f"There is no Claude Code at {path}.")
        found = shutil.which("claude") or next(
            (p for p in map(os.path.expanduser, _CLAUDE_PLACES) if os.access(p, os.X_OK)), None
        )
        if not found:
            raise AIError("Claude Code isn't installed. Install it, or set its path in the AI settings.")
        return found

    def describe(self) -> str:
        """'Claude Code Opus 5.5, medium effort'."""
        name = dict(CLAUDE_CODE_MODELS).get(self.model, self.model)
        effort = self.config.get("effort")
        return "Claude Code" + (f" {name}" if name else "") + (f", {effort} effort" if effort else "")

    def models(self) -> list[str]:
        """Claude Code has no command that lists models; the settings dialog shows the current
        ones and lets the user type any other name."""
        self.binary()  # says so when it isn't installed
        return [m for m, _ in CLAUDE_CODE_MODELS]

    def extract(self, text: str, tree: list[Group] | None = None) -> list[ModelItem]:
        tree = tree or default_tree()
        out = self._run(prompt(tree) + text, SYSTEM, schema(tree))
        if isinstance(out.get("structured_output"), dict):
            return _parse(json.dumps(out["structured_output"]), tree)
        return _parse(str(out.get("result") or ""), tree)

    def chat(self, system: str, messages: list[dict]) -> str:
        """Claude Code runs one prompt at a time, so the conversation so far is sent each time."""
        history = "\n\n".join(f"{'User' if m['role'] == 'user' else 'You'}: {m['content']}" for m in messages[:-1])
        text = (f"Conversation so far:\n\n{history}\n\nThe user's new message:\n\n" if history else "") + messages[-1]["content"]
        return str(self._run(text, system).get("result") or "")

    def _run(self, text: str, system: str, json_schema: dict | None = None) -> dict:
        binary = self.binary()
        cmd = [
            binary, "-p", "--output-format", "json",
            "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
            "--disable-slash-commands", "--system-prompt", system,
        ]
        if json_schema:
            cmd += ["--json-schema", json.dumps(json_schema)]
        if self.model:
            cmd += ["--model", self.model]
        if self.config.get("effort") in EFFORTS:
            cmd += ["--effort", self.config["effort"]]
        env = {**os.environ, "PATH": os.pathsep.join([os.path.dirname(binary), os.environ.get("PATH", "/usr/bin:/bin")])}
        with tempfile.TemporaryDirectory(prefix="jobpilot-") as empty:
            try:
                done = _run_cli(cmd, text, empty, env)
            except subprocess.TimeoutExpired as e:
                raise AIError("Claude Code took too long. Try again.") from e
            except OSError as e:
                raise AIError(f"Couldn't start Claude Code: {e}") from e
        try:
            out = json.loads(done.stdout)
        except ValueError:
            out = None
        if not isinstance(out, dict):
            raise AIError(_cli_error(done.stderr or done.stdout or f"Claude Code stopped (exit {done.returncode})."))
        if out.get("is_error") or done.returncode != 0:
            raise AIError(_cli_error(str(out.get("result") or done.stderr or "Claude Code couldn't answer.")))
        return out


def _cli_error(message: str) -> str:
    text = message.strip().splitlines()[0][:300] if message.strip() else "Claude Code couldn't answer."
    lowered = text.lower()
    if any(w in lowered for w in ("not logged in", "log in", "login", "authenticat", "invalid api key", "oauth")):
        return "Claude Code isn't logged in. Run claude once in Terminal and log in."
    if any(w in lowered for w in ("usage limit", "rate limit", "limit reached", "out of extra usage")):
        return "Claude Code usage limit reached. Try again later; the job can be read again then."
    return f"Claude Code: {text}"


_CLASSES: dict[str, type[Provider]] = {
    "none": Provider, "ollama": Ollama, "openai": OpenAICompatible, "anthropic": Claude, "claude_code": ClaudeCode,
}


def _default_provider() -> str:
    """Before the user picks one: Claude Code when it's installed (best results, no key),
    otherwise the free local model."""
    try:
        ClaudeCode({}).binary()
        return "claude_code"
    except AIError:
        return "ollama"


class Settings:
    """The chosen provider and each provider's own settings, so switching back keeps them."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        provider = data.get("provider") if data.get("provider") in PROVIDERS else _default_provider()
        stored = data.get("providers") if isinstance(data.get("providers"), dict) else {}
        return {"provider": provider, "providers": {p: {**d, **stored.get(p, {})} for p, d in DEFAULTS.items()}}

    def save(self, data: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.chmod(0o600)  # holds API keys
            tmp.replace(self.path)

    def provider(self, name: str | None = None, overrides: dict | None = None) -> Provider:
        data = self.load()
        name = name or data["provider"]
        return _CLASSES[name]({**data["providers"].get(name, {}), **(overrides or {})})
