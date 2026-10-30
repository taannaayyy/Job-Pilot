import { useEffect, useRef, useState } from "react";
import { CheckIcon, ChevronIcon } from "./Icons";

interface Option {
  value: string;
  label: string;
  count: number;
}

interface Props {
  label: string;
  options: Option[];
  /** Values not shown. Kept as what's hidden, so a kind that appears later is shown. */
  hidden: string[];
  onChange: (hidden: string[]) => void;
}

/** A filter where any number of values can be turned off, or one kept on its own ("only"). */
export default function MultiFilter({ label, options, hidden, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const shown = options.filter((o) => !hidden.includes(o.value));
  const summary =
    shown.length === options.length
      ? "All"
      : shown.length === 0
        ? "None"
        : shown.length === 1
          ? shown[0].label
          : options.length - shown.length <= 2
            ? `Not ${options.filter((o) => hidden.includes(o.value)).map((o) => o.label).join(", ")}`
            : `${shown.length} of ${options.length}`;

  const toggle = (value: string) =>
    onChange(hidden.includes(value) ? hidden.filter((v) => v !== value) : [...hidden, value]);

  return (
    <div className="multi-filter" ref={ref}>
      <button
        type="button"
        className={`picker-trigger ${open ? "open" : ""} ${shown.length < options.length ? "filtered" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="picker-value">
          <span className="muted">{label}:</span> {summary}
        </span>
        <ChevronIcon />
      </button>
      {open && (
        <div className="picker-pop multi-pop" role="listbox" aria-multiselectable>
          <div className="multi-actions">
            <button type="button" className="link quiet" onClick={() => onChange([])}>
              Show all
            </button>
            <button type="button" className="link quiet" onClick={() => onChange(options.map((o) => o.value))}>
              Hide all
            </button>
          </div>
          <div className="multi-list">
            {options.map((o) => {
              const on = !hidden.includes(o.value);
              return (
                <div key={o.value} className="multi-option" role="option" aria-selected={on}>
                  <label>
                    <input type="checkbox" checked={on} onChange={() => toggle(o.value)} />
                    <span className="multi-label">{o.label}</span>
                    <span className="picker-tag">{o.count}</span>
                  </label>
                  <button
                    type="button"
                    className="link quiet only"
                    title={`Show only ${o.label}`}
                    onClick={() => onChange(options.filter((x) => x.value !== o.value).map((x) => x.value))}
                  >
                    {shown.length === 1 && on ? <CheckIcon /> : "Only"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
