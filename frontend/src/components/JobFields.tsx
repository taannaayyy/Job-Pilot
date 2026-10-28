import { DISTRICTS, ISTANBUL, SIDE_LABELS, type Side } from "../locations";
import { WORK_MODES, WORK_MODE_LABELS, type JobInput, type WorkMode } from "../types";

export const SOURCES = ["LinkedIn", "Company site", "Referral", "Kariyer.net", "Other"];

export function emptyInput(): JobInput {
  return {
    company: "",
    company_website: null,
    title: "",
    url: null,
    city: ISTANBUL,
    district: null,
    work_mode: null,
    source: "LinkedIn",
    next_action: null,
    notes: "",
  };
}

type CityMode = "istanbul" | "other" | "none";

const cityMode = (city: string | null): CityMode => (city === ISTANBUL ? "istanbul" : city === null ? "none" : "other");

interface Props {
  value: JobInput;
  onChange: (value: JobInput) => void;
  autoFocus?: boolean;
}

export default function JobFields({ value, onChange, autoFocus }: Props) {
  const set = <K extends keyof JobInput>(key: K, v: JobInput[K]) => onChange({ ...value, [key]: v });
  const text = (key: "url" | "company_website" | "next_action") => (e: React.ChangeEvent<HTMLInputElement>) =>
    set(key, e.target.value.trim() ? e.target.value : null);
  const mode = cityMode(value.city);

  const setMode = (next: CityMode) => {
    if (next === mode) return;
    // "Other" starts as an empty string (not null) so the city text box shows up.
    const city = next === "istanbul" ? ISTANBUL : next === "other" ? "" : null;
    onChange({ ...value, city, district: null });
  };

  return (
    <div className="fields">
      <label>
        Company *
        <input required autoFocus={autoFocus} value={value.company} onChange={(e) => set("company", e.target.value)} />
      </label>
      <label>
        Company website
        <input
          placeholder="company.com"
          value={value.company_website ?? ""}
          onChange={text("company_website")}
          title="Used to show the company logo"
        />
      </label>
      <label className="wide">
        Role title *
        <input required value={value.title} onChange={(e) => set("title", e.target.value)} />
      </label>
      <label className="wide">
        Job URL
        <input type="url" placeholder="https://www.linkedin.com/jobs/view/…" value={value.url ?? ""} onChange={text("url")} />
      </label>

      <label>
        City
        <select value={mode} onChange={(e) => setMode(e.target.value as CityMode)}>
          <option value="istanbul">Istanbul</option>
          <option value="other">Other city…</option>
          <option value="none">— (not set)</option>
        </select>
      </label>
      {mode === "istanbul" && (
        <label className="reveal">
          District
          <select value={value.district ?? ""} onChange={(e) => set("district", e.target.value || null)}>
            <option value="">Any district</option>
            {(Object.keys(DISTRICTS) as Side[]).map((side) => (
              <optgroup key={side} label={SIDE_LABELS[side]}>
                {DISTRICTS[side].map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      )}
      {mode === "other" && (
        <label className="reveal">
          City name
          <input
            autoFocus
            placeholder="Ankara, Berlin…"
            value={value.city ?? ""}
            onChange={(e) => set("city", e.target.value)}
          />
        </label>
      )}
      {mode === "none" && <div />}

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
      <label className="wide">
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
