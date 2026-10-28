import { ORG_KINDS, ORG_KIND_LABELS, type CompanyInput, type OrgKind } from "../types";

export function emptyOrg(): CompanyInput {
  return { name: "", kind: "company", website: null, careers_url: null, linkedin_url: null, notes: "" };
}

interface Props {
  value: CompanyInput;
  onChange: (value: CompanyInput) => void;
  autoFocus?: boolean;
}

export default function OrgFields({ value, onChange, autoFocus }: Props) {
  const set = <K extends keyof CompanyInput>(key: K, v: CompanyInput[K]) => onChange({ ...value, [key]: v });
  const url = (key: "website" | "careers_url" | "linkedin_url") => (e: React.ChangeEvent<HTMLInputElement>) =>
    set(key, e.target.value.trim() ? e.target.value : null);

  return (
    <div className="fields">
      <label>
        Name *
        <input
          required
          autoFocus={autoFocus}
          placeholder="Company, lab or university"
          value={value.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </label>
      <label>
        Type
        <select value={value.kind} onChange={(e) => set("kind", e.target.value as OrgKind)}>
          {ORG_KINDS.map((k) => (
            <option key={k} value={k}>
              {ORG_KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Website
        <input placeholder="example.com" value={value.website ?? ""} onChange={url("website")} title="Used for the logo" />
      </label>
      <label>
        Careers page
        <input placeholder="Where they post open positions" value={value.careers_url ?? ""} onChange={url("careers_url")} />
      </label>
      <label className="wide">
        LinkedIn page
        <input
          placeholder="https://www.linkedin.com/company/…"
          value={value.linkedin_url ?? ""}
          onChange={url("linkedin_url")}
          title="Its LinkedIn jobs tab opens from the watchlist"
        />
      </label>
      <label className="wide">
        Notes
        <textarea
          rows={4}
          placeholder="Why you are interested, who you know there, what they work on…"
          value={value.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
      </label>
    </div>
  );
}
