"""The AI model the user talks to about their skill tree (Recommendations), chosen by the user:
none, a local model through Ollama, any OpenAI-compatible API (OpenAI, OpenRouter, Groq, Gemini, LM Studio...),
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
from pathlib import Path

import anthropic


PROVIDERS = ("none", "ollama", "openai", "anthropic", "claude_code")
LABELS = {
    "none": "No AI", "ollama": "Ollama", "openai": "OpenAI-compatible",
    "anthropic": "Claude", "claude_code": "Claude Code",
}
DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434", "model": ""},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "", "api_key": ""},
    "anthropic": {"model": "claude-opus-5-5", "api_key": ""},
    # Empty model and effort: Claude Code's own default.
    "claude_code": {"path": "", "model": "claude-opus-5-5", "effort": "medium"},
}
TIMEOUT = 300  # local models on a laptop can take minutes for a long answer


class AIError(Exception):
    """Something the user can fix: the model isn't running, the key is wrong..."""


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

    def describe(self) -> str:
        return LABELS[self.name] + (f" {self.model}" if self.model else "")

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

    def _chat(self, messages: list[dict]) -> str:
        body = {"model": self.model, "messages": messages, "stream": False}
        try:
            res = _http_json(f"{self.base}/api/chat", body)
        except urllib.error.HTTPError as e:
            raise AIError(f"Ollama: {_http_error(e)}") from e
        except OSError as e:
            raise AIError("Ollama isn't running. Open the Ollama app, or choose another model.") from e
        return res.get("message", {}).get("content", "")

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

    def chat(self, system: str, messages: list[dict]) -> str:
        """Claude Code runs one prompt at a time, so the conversation so far is sent each time."""
        history = "\n\n".join(f"{'User' if m['role'] == 'user' else 'You'}: {m['content']}" for m in messages[:-1])
        text = (f"Conversation so far:\n\n{history}\n\nThe user's new message:\n\n" if history else "") + messages[-1]["content"]
        return str(self._run(text, system).get("result") or "")

    def _run(self, text: str, system: str) -> dict:
        binary = self.binary()
        cmd = [
            binary, "-p", "--output-format", "json",
            "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
            "--disable-slash-commands", "--system-prompt", system,
        ]
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
        return "Claude Code usage limit reached. Try again later."
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
