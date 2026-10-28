import type { ReactNode } from "react";

interface Option<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface Props<T extends string> {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  iconOnly?: boolean;
  ariaLabel: string;
}

/** Segmented control with a thumb that slides to the selected option. */
export default function Segmented<T extends string>({ options, value, onChange, iconOnly, ariaLabel }: Props<T>) {
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  return (
    <div
      className={`segmented ${iconOnly ? "icon-only" : ""}`}
      role="radiogroup"
      aria-label={ariaLabel}
      style={{ "--count": options.length, "--index": index } as React.CSSProperties}
    >
      <span className="segmented-thumb" aria-hidden />
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          title={o.label}
          aria-label={iconOnly ? o.label : undefined}
          className="no-ripple"
          onClick={() => onChange(o.value)}
        >
          {o.icon}
          {!iconOnly && <span>{o.label}</span>}
        </button>
      ))}
    </div>
  );
}
