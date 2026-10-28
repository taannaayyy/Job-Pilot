import type { Openings } from "../types";

/** Records the result of checking an organization for open positions. */
export default function HiringButtons({
  value,
  onChange,
  small,
}: {
  value: Openings | null;
  onChange: (value: Openings) => void;
  small?: boolean;
}) {
  return (
    <div className={`hiring-buttons ${small ? "small" : ""}`} role="group" aria-label="Open positions">
      <button
        type="button"
        className={`hire-yes ${value === "hiring" ? "on" : ""}`}
        aria-pressed={value === "hiring"}
        onClick={(e) => {
          e.stopPropagation();
          onChange("hiring");
        }}
      >
        Hiring
      </button>
      <button
        type="button"
        className={`hire-no ${value === "none" ? "on" : ""}`}
        aria-pressed={value === "none"}
        onClick={(e) => {
          e.stopPropagation();
          onChange("none");
        }}
      >
        Not hiring
      </button>
    </div>
  );
}
