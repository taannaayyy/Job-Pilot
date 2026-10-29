import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { AIProvider, AIProviderInput, AISettings } from "../types";
import { useClosing } from "../useClosing";
import { CheckIcon, RefreshIcon } from "./Icons";

interface Props {
  onClose: () => void;
  onSaved: (settings: AISettings) => void;
}

const CHOICES: { value: AIProvider; title: string; text: string }[] = [
  { value: "none", title: "Dictionary only", text: "No AI. Finds the skills the app knows, instantly. Free." },
  { value: "ollama", title: "Local model (Ollama)", text: "Runs on this Mac. Free, and nothing leaves the computer." },
  { value: "openai", title: "OpenAI-compatible API", text: "OpenAI, OpenRouter, Groq, Gemini, Mistral, LM Studio and others." },
  { value: "anthropic", title: "Claude", text: "Anthropic's API, with your own key." },
];

// Common servers that speak the OpenAI API; any other address can be typed in.
const PRESETS = [
  { label: "OpenAI", url: "https://api.openai.com/v1" },
  { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { label: "Groq", url: "https://api.groq.com/openai/v1" },
  { label: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { label: "Mistral", url: "https://api.mistral.ai/v1" },
  { label: "LM Studio (local)", url: "http://localhost:1234/v1" },
];

type Form = Record<string, AIProviderInput & { has_key?: boolean }>;

export default function AISettingsDialog({ onClose, onSaved }: Props) {
  const [provider, setProvider] = useState<AIProvider>("ollama");
  const [form, setForm] = useState<Form | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [closing, close] = useClosing(onClose);

  useEffect(() => {
    api.getAISettings().then(
      (s) => {
        setProvider(s.provider);
        setForm(s.providers as Form);
      },
      (e) => setError(e.message),
    );
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const body = useCallback(
    (p: AIProvider = provider) => {
      if (!form || p === "none") return { provider: p };
      const { has_key: _, ...fields } = form[p] ?? {};
      return { provider: p, providers: { [p]: fields } };
    },
    [form, provider],
  );

  const loadModels = useCallback(async () => {
    if (provider === "none") return;
    setLoadingModels(true);
    setModelsError(null);
    try {
      setModels((await api.listModels(body())).models);
    } catch (e) {
      setModels([]);
      setModelsError((e as Error).message);
    } finally {
      setLoadingModels(false);
    }
  }, [body, provider]);

  // Local models are listed right away; APIs once a key is there.
  useEffect(() => {
    setTest(null);
    setModels([]);
    setModelsError(null);
    if (!form) return;
    const config = form[provider] ?? {};
    if (provider === "ollama" || (provider !== "none" && (config.has_key || config.api_key))) loadModels();
    // Only when the chosen provider changes, not on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, !!form]);

  const set = (field: keyof AIProviderInput, value: string) =>
    setForm((f) => (f ? { ...f, [provider]: { ...f[provider], [field]: value } } : f));

  const config = form?.[provider] ?? {};

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const r = await api.testAI(body());
      setTest({ ok: true, text: `${r.used} found ${r.found.join(", ")} in ${r.seconds}s.` });
    } catch (e) {
      setTest({ ok: false, text: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    try {
      onSaved(await api.saveAISettings(body()));
      close();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className={`overlay ${closing ? "closing" : ""}`} onMouseDown={close}>
      <div className="modal" role="dialog" aria-labelledby="ai-title" onMouseDown={(e) => e.stopPropagation()}>
        <h2 id="ai-title">AI model</h2>
        <p className="modal-hint">
          Reads your target jobs' descriptions together with the skill dictionary. The dictionary always runs; a model
          adds the skills it doesn't know. Pick whatever you like, and change it any time.
        </p>

        {!form ? (
          <div className="empty">{error ?? <span className="spinner" aria-label="Loading" />}</div>
        ) : (
          <>
            <div className="ai-choices" role="radiogroup" aria-label="Model">
              {CHOICES.map((c) => (
                <label key={c.value} className={`ai-choice ${provider === c.value ? "on" : ""}`}>
                  <input
                    type="radio"
                    name="provider"
                    checked={provider === c.value}
                    onChange={() => setProvider(c.value)}
                  />
                  <span>
                    <strong>{c.title}</strong>
                    <span className="muted">{c.text}</span>
                  </span>
                </label>
              ))}
            </div>

            {provider !== "none" && (
              <div className="fields ai-fields">
                {provider === "openai" && (
                  <label className="wide">
                    Server
                    <div className="row">
                      <select
                        value={PRESETS.find((p) => p.url === config.base_url)?.url ?? ""}
                        onChange={(e) => e.target.value && set("base_url", e.target.value)}
                      >
                        <option value="">Other address</option>
                        {PRESETS.map((p) => (
                          <option key={p.url} value={p.url}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <input
                        value={config.base_url ?? ""}
                        onChange={(e) => set("base_url", e.target.value)}
                        placeholder="https://…/v1"
                      />
                    </div>
                  </label>
                )}
                {provider === "ollama" && (
                  <label className="wide">
                    Ollama address
                    <input value={config.base_url ?? ""} onChange={(e) => set("base_url", e.target.value)} />
                  </label>
                )}
                {(provider === "openai" || provider === "anthropic") && (
                  <label className="wide">
                    API key
                    <input
                      type="password"
                      autoComplete="off"
                      value={config.api_key ?? ""}
                      onChange={(e) => set("api_key", e.target.value)}
                      placeholder={config.has_key ? "Saved. Type a new one to replace it." : "Paste your key"}
                    />
                    <span className="field-note">Kept on this Mac only, in a file only you can read.</span>
                  </label>
                )}
                <label className="wide">
                  Model
                  <div className="row">
                    <input
                      list="ai-models"
                      value={config.model ?? ""}
                      onChange={(e) => set("model", e.target.value)}
                      placeholder={provider === "ollama" ? "First installed model" : "Choose or type a model"}
                    />
                    <datalist id="ai-models">
                      {models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                    <button type="button" onClick={loadModels} disabled={loadingModels} title="List the models again">
                      {loadingModels ? <span className="spinner tiny" /> : <RefreshIcon />}
                      List models
                    </button>
                  </div>
                  {modelsError ? (
                    <span className="field-note err">{modelsError}</span>
                  ) : models.length > 0 ? (
                    <span className="field-note">{models.length} available. Click the field to pick one.</span>
                  ) : null}
                </label>
              </div>
            )}

            {test && <div className={test.ok ? "ai-test ok" : "error"}>{test.ok && <CheckIcon />}{test.text}</div>}
            {error && <div className="error">{error}</div>}

            <div className="actions">
              <button type="button" onClick={runTest} disabled={testing}>
                {testing ? <span className="spinner tiny" /> : null}
                {testing ? "Testing…" : "Test"}
              </button>
              <span className="spacer" />
              <button type="button" onClick={close}>
                Cancel
              </button>
              <button type="button" className="primary" onClick={save}>
                Save
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
