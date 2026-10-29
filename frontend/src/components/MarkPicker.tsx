import { SKILL_MARKS, SKILL_MARK_LABELS, type SkillMark } from "../types";

interface Props {
  value: SkillMark | null;
  onChange: (mark: SkillMark | null) => void;
  name: string;
}

/** Have, Learning, Gap or Ignore. Clicking the chosen one again clears it (no mark counts as a gap). */
export default function MarkPicker({ value, onChange, name }: Props) {
  return (
    <div className="mark-picker" role="radiogroup" aria-label={`Your level in ${name}`} onClick={(e) => e.stopPropagation()}>
      {SKILL_MARKS.map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={value === m}
          className={`mark-${m} ${value === m ? "on" : ""}`}
          onClick={() => onChange(value === m ? null : m)}
        >
          {SKILL_MARK_LABELS[m]}
        </button>
      ))}
    </div>
  );
}
