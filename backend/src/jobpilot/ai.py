"""The AI model that reads job descriptions, chosen by the user: none (dictionary only), a local
model through Ollama, any OpenAI-compatible API (OpenAI, OpenRouter, Groq, Gemini, LM Studio...)
or Claude. Settings, including API keys, live in a file next to the database that only the user
can read."""

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import anthropic

from jobpilot.models import Importance
from jobpilot.skills import CATEGORIES

PROVIDERS = ("none", "ollama", "openai", "anthropic")
LABELS = {"none": "Dictionary only", "ollama": "Ollama", "openai": "OpenAI-compatible", "anthropic": "Claude"}
DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434", "model": ""},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "", "api_key": ""},
    "anthropic": {"model": "claude-opus-5-5", "api_key": ""},
}
TIMEOUT = 300  # local models on a laptop can take minutes for a long posting


class AIError(Exception):
    """Something the user can fix: the model isn't running, the key is wrong..."""


@dataclass(frozen=True)
class ModelItem:
    name: str
    category: str
    importance: Importance
    evidence: str


SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "importance": {"type": "string", "enum": ["must", "nice"]},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "category", "importance", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["requirements"],
    "additionalProperties": False,
}

PROMPT = """List everything this job asks of a candidate: skills, tools, concepts, experience, education and spoken languages.
Look at the requirements and also at the responsibilities ("deploy with Docker" means Docker is needed).
- One item per skill: "PyTorch and Hugging Face" is two items.
- name: the skill in 1 to 4 words ("PyTorch", "RAG", "A/B testing", "2+ years of experience", "Master's degree").
- importance: "nice" when the posting says plus, nice to have, preferred, bonus or advantage; otherwise "must".
- evidence: the short phrase from the posting it comes from.
- Only what a candidate must know or have, never the tasks of the job: "Monitor model performance" and
  "Prepare reports" are tasks, not skills. From a task, take only a skill it names ("deploy with Docker": Docker).
- Use the posting's own words for the name.
- Leave out benefits and anything about the company itself.

Job posting:
"""


def _parse(text: str) -> list[ModelItem]:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise AIError("The model didn't answer in the expected format. Try another model.") from e
    items = []
    for raw in data.get("requirements", []) if isinstance(data, dict) else []:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            continue
        category = raw.get("category") if raw.get("category") in CATEGORIES else "other"
        importance = Importance.NICE if raw.get("importance") == "nice" else Importance.MUST
        items.append(ModelItem(str(raw["name"]).strip()[:200], category, importance, str(raw.get("evidence", ""))[:300]))
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

    def describe(self) -> str:
        return LABELS[self.name] + (f" {self.model}" if self.model else "")

    def extract(self, text: str) -> list[ModelItem]:
        return []

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

    def extract(self, text: str) -> list[ModelItem]:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": PROMPT + text}],
            "format": SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            res = _http_json(f"{self.base}/api/chat", body)
        except urllib.error.HTTPError as e:
            raise AIError(f"Ollama: {_http_error(e)}") from e
        except OSError as e:
            raise AIError("Ollama isn't running. Open the Ollama app, or choose another model.") from e
        return _parse(res.get("message", {}).get("content", ""))


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

    def extract(self, text: str) -> list[ModelItem]:
        if not self.model:
            raise AIError("Choose a model in the AI settings.")
        messages = [{"role": "user", "content": PROMPT + text}]
        body = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "requirements", "schema": SCHEMA, "strict": True}},
        }
        try:
            res = _http_json(f"{self.base}/chat/completions", body, self._headers())
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise AIError(_http_error(e)) from e
            # Servers without JSON schema support still take plain JSON mode.
            body["response_format"] = {"type": "json_object"}
            body["messages"] = [{"role": "user", "content": PROMPT + text + "\n\nAnswer with JSON matching this schema:\n" + json.dumps(SCHEMA)}]
            try:
                res = _http_json(f"{self.base}/chat/completions", body, self._headers())
            except urllib.error.HTTPError as e2:
                raise AIError(_http_error(e2)) from e2
        except OSError as e:
            raise AIError(f"Couldn't reach {self.base}") from e
        try:
            return _parse(res["choices"][0]["message"]["content"] or "")
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

    def extract(self, text: str) -> list[ModelItem]:
        try:
            response = self._client().messages.create(
                model=self.model or DEFAULTS["anthropic"]["model"],
                max_tokens=16000,
                messages=[{"role": "user", "content": PROMPT + text}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
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
        return _parse(next((b.text for b in response.content if b.type == "text"), ""))


_CLASSES: dict[str, type[Provider]] = {"none": Provider, "ollama": Ollama, "openai": OpenAICompatible, "anthropic": Claude}


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
        provider = data.get("provider") if data.get("provider") in PROVIDERS else "ollama"
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
