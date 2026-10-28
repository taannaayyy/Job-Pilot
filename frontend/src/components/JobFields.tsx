import { WORK_MODES, WORK_MODE_LABELS, type JobInput, type WorkMode } from "../types";

export const SOURCES = ["LinkedIn", "Company site", "Referral", "Kariyer.net", "Other"];

export function emptyInput(): JobInput {
  return {
    company: "",
    title: "",
    url: null,
    location: null,
    work_mode: null,
    source: "LinkedIn",
    next_action: null,
    notes: "",
  };
}

interface Props {
  value: JobInput;
  onChange: (value: JobInput) => void;
  autoFocus?: boolean;
}

export default function JobFields({ value, onChange, autoFocus }: Props) {
  const set = <K extends keyof JobInput>(key: K, v: JobInput[K]) => onChange({ ...value, [key]: v });
  const text = (key: "url" | "location" | "next_action") => (e: React.ChangeEvent<HTMLInputElement>) =>
    set(key, e.target.value.trim() ? e.target.value : null);

  return (
    <div className="fields">
      <label>
        Company *
        <input required autoFocus={autoFocus} value={value.company} onChange={(e) => set("company", e.target.value)} />
      </label>
      <label>
        Role title *
        <input required value={value.title} onChange={(e) => set("title", e.target.value)} />
      </label>
      <label className="wide">
        Job URL
        <input type="url" placeholder="https://www.linkedin.com/jobs/view/…" value={value.url ?? ""} onChange={text("url")} />
      </label>
      <label>
        Location
        <input placeholder="Istanbul" value={value.location ?? ""} onChange={text("location")} />
      </label>
      <label>
        Work mode
        <select
          value={value.work_mode ?? ""}
          onChange={(e) => set("work_mode", (e.target.value || null) as WorkMode | null)}
        >
          <option value="">—</option>
          {WORK_MODES.map((m) => (
            <option key={m} value={m}>
              {WORK_MODE_LABELS[m]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Source
        <input
          list="sources"
          value={value.source ?? ""}
          onChange={(e) => set("source", e.target.value.trim() ? e.target.value : null)}
        />
        <datalist id="sources">
          {SOURCES.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </label>
      <label>
        Next action
        <input placeholder="Message the recruiter" value={value.next_action ?? ""} onChange={text("next_action")} />
      </label>
      <label className="wide">
        Notes
        <textarea rows={6} value={value.notes} onChange={(e) => set("notes", e.target.value)} />
      </label>
    </div>
  );
}
