import { useState } from "react";
import { CheckIcon } from "./Icons";

interface Props {
  model: string;
  effort: string;
  onChange: (change: { model?: string; effort?: string }) => void;
}

// Claude Code has no command that lists its models, so the current ones are listed here; any
// other name can be typed under "Other model".
const MODELS = [
  { id: "claude-opus-5-5", name: "Opus 5.5", text: "For complex work and everyday tasks", recommended: true },
  { id: "claude-sonnet-5-5", name: "Sonnet 5.5", text: "Most efficient for simpler tasks" },
  { id: "claude-fable-5-1", name: "Fable 5.1", text: "For your toughest challenges. May need extra usage." },
  { id: "claude-haiku-5-5", name: "Haiku 5.5", text: "Fastest for quick answers" },
  { id: "claude-haiku-4-5", name: "Haiku 4.5", text: "Fastest for quick answers" },
  { id: "claude-sonnet-5", name: "Sonnet 5", text: "Efficient for routine tasks" },
];

const EFFORTS = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "Extra high" },
  { value: "max", label: "Max" },
];

/** Claude Code's model and how long it thinks, picked from a list like Claude Code's own menu. */
export default function ClaudeModelPicker({ model, effort, onChange }: Props) {
  const known = model === "" || MODELS.some((m) => m.id === model);
  const [other, setOther] = useState(!known);
  const effortIndex = Math.max(0, EFFORTS.findIndex((e) => e.value === effort));

  const option = (id: string, name: string, text: string, recommended = false) => {
    const on = !other && model === id;
    return (
      <button
        key={id || "default"}
        type="button"
        role="radio"
        aria-checked={on}
        className={`model-option ${on ? "on" : ""}`}
        onClick={() => {
          setOther(false);
          onChange({ model: id });
        }}
      >
        <span className="model-text">
          <span className="model-name">
            {name}
            {recommended && <span className="model-tag">Recommended</span>}
          </span>
          <span className="muted">{text}</span>
        </span>
        {on && <CheckIcon />}
      </button>
    );
  };

  return (
    <div className="model-picker">
      <div className="model-list" role="radiogroup" aria-label="Model">
        {MODELS.map((m) => option(m.id, m.name, m.text, m.recommended))}
        {option("", "Claude Code's default", "Whatever Claude Code uses on its own")}
        <button
          type="button"
          role="radio"
          aria-checked={other}
          className={`model-option ${other ? "on" : ""}`}
          onClick={() => {
            setOther(true);
            if (known) onChange({ model: "" });
          }}
        >
          <span className="model-text">
            <span className="model-name">Other model</span>
            <span className="muted">Type any model name, e.g. a newer one</span>
          </span>
          {other && <CheckIcon />}
        </button>
        {other && (
          <input
            className="model-other"
            autoFocus
            value={model}
            placeholder="claude-…"
            onChange={(e) => onChange({ model: e.target.value.trim() })}
          />
        )}
      </div>

      <div className="effort">
        <span>
          Effort <span className="muted">({EFFORTS[effortIndex].label})</span>
          <span className="field-note"> More thinking: better answers, slower, more of your plan's usage.</span>
        </span>
        <div
          className="effort-track"
          role="radiogroup"
          aria-label="Effort"
          style={{ "--index": effortIndex, "--count": EFFORTS.length } as React.CSSProperties}
        >
          <span className="effort-knob" aria-hidden />
          {EFFORTS.map((e) => (
            <button
              key={e.value}
              type="button"
              role="radio"
              aria-checked={e.value === EFFORTS[effortIndex].value}
              aria-label={e.label}
              title={e.label}
              className="effort-dot no-ripple"
              onClick={() => onChange({ effort: e.value })}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
