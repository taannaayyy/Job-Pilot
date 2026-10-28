import { useMemo, useState } from "react";
import { daysSince, fmtAgo } from "../format";
import { STALE_AFTER_DAYS, linkedinJobsUrl } from "../orgs";
import { ORG_KINDS, ORG_KIND_LABELS, type Company, type Job, type Openings, type OrgKind } from "../types";
import CompanyLogo from "./CompanyLogo";
import HiringButtons from "./HiringButtons";
import { BriefcaseIcon, ExternalIcon, EyeIcon, GlobeIcon, PlusIcon, SearchIcon } from "./Icons";

type HiringFilter = "" | Openings | "unchecked" | "due";
type Sort = "name" | "checked" | "added";

interface Props {
  orgs: Company[];
  jobs: Job[];
  onOpen: (id: number) => void;
  onAdd: () => void;
  onAddJob: (org: Company) => void;
  onSetOpenings: (id: number, openings: Openings) => void;
}

const isDue = (o: Company) => !o.last_checked_at || daysSince(o.last_checked_at) > STALE_AFTER_DAYS;

export default function Watchlist({ orgs, jobs, onOpen, onAdd, onAddJob, onSetOpenings }: Props) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<OrgKind | "">("");
  const [hiring, setHiring] = useState<HiringFilter>("");
  const [sort, setSort] = useState<Sort>("name");

  const jobCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const j of jobs) if (!["rejected", "ghosted"].includes(j.status)) counts.set(j.company_id, (counts.get(j.company_id) ?? 0) + 1);
    return counts;
  }, [jobs]);

  const shown = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    const list = orgs.filter(
      (o) =>
        (!kind || o.kind === kind) &&
        (!hiring ||
          (hiring === "unchecked" ? !o.openings : hiring === "due" ? isDue(o) : o.openings === hiring)) &&
        (!q || [o.name, o.notes].some((v) => v.toLocaleLowerCase("tr").includes(q))),
    );
    const by: Record<Sort, (a: Company, b: Company) => number> = {
      name: (a, b) => a.name.localeCompare(b.name, "tr"),
      // Never checked first, then the longest ago.
      checked: (a, b) => (a.last_checked_at ?? "").localeCompare(b.last_checked_at ?? ""),
      added: (a, b) => (b.date_watched ?? "").localeCompare(a.date_watched ?? ""),
    };
    return list.sort(by[sort]);
  }, [orgs, query, kind, hiring, sort]);

  const hiringCount = orgs.filter((o) => o.openings === "hiring").length;
  const dueCount = orgs.filter(isDue).length;

  return (
    <>
      <div className="toolbar">
        <label className="search">
          <SearchIcon />
          <input type="search" placeholder="Search watchlist" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <select value={kind} onChange={(e) => setKind(e.target.value as OrgKind | "")}>
          <option value="">All types</option>
          {ORG_KINDS.map((k) => (
            <option key={k} value={k}>
              {ORG_KIND_LABELS[k]}
            </option>
          ))}
        </select>
        <select value={hiring} onChange={(e) => setHiring(e.target.value as HiringFilter)}>
          <option value="">Any hiring status</option>
          <option value="hiring">Hiring</option>
          <option value="none">Not hiring</option>
          <option value="unchecked">Not checked yet</option>
          <option value="due">Due for a check</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="name">Sort by name</option>
          <option value="checked">Least recently checked</option>
          <option value="added">Recently added</option>
        </select>
        <span className="toolbar-note">
          {hiringCount} hiring · {dueCount} due for a check
        </span>
      </div>

      <main>
        {orgs.length === 0 ? (
          <div className="empty hero">
            <span className="logo big" aria-hidden>
              <EyeIcon />
            </span>
            <p>Save companies, labs and universities you would like to work at, then check them for openings.</p>
            <button className="primary" onClick={onAdd}>
              <PlusIcon /> Add your first one
            </button>
          </div>
        ) : shown.length === 0 ? (
          <p className="empty">Nothing on the watchlist matches these filters.</p>
        ) : (
          <div className="org-grid">
            {shown.map((o, i) => {
              const count = jobCounts.get(o.id) ?? 0;
              const due = isDue(o);
              return (
                <article
                  key={o.id}
                  className={`org-card ${o.openings ?? "unchecked"}`}
                  style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}
                  tabIndex={0}
                  onClick={() => onOpen(o.id)}
                  onKeyDown={(e) => e.key === "Enter" && onOpen(o.id)}
                >
                  <header className="org-head">
                    <CompanyLogo name={o.name} logoUrl={o.logo_url} size={40} />
                    <div className="org-title">
                      <h3>{o.name}</h3>
                      <span className="org-kind">{ORG_KIND_LABELS[o.kind]}</span>
                    </div>
                    <span className={`hire-chip ${o.openings ?? "unchecked"}`}>
                      {o.openings === "hiring" ? "Hiring" : o.openings === "none" ? "Not hiring" : "Not checked"}
                    </span>
                  </header>

                  {o.notes && <p className="org-notes">{o.notes}</p>}

                  <div className="org-meta">
                    <span className={due && o.last_checked_at ? "due" : undefined}>
                      {o.last_checked_at ? `Checked ${fmtAgo(o.last_checked_at)}` : "Never checked"}
                    </span>
                    {count > 0 && (
                      <span>
                        {count} {count === 1 ? "job" : "jobs"} tracked
                      </span>
                    )}
                  </div>

                  <div className="org-links" onClick={(e) => e.stopPropagation()}>
                    {(o.careers_url || o.website) && (
                      <a className="org-link" href={o.careers_url ?? o.website!} target="_blank" rel="noreferrer">
                        {o.careers_url ? <BriefcaseIcon /> : <GlobeIcon />}
                        {o.careers_url ? "Careers" : "Website"}
                        <ExternalIcon />
                      </a>
                    )}
                    <a className="org-link" href={linkedinJobsUrl(o)} target="_blank" rel="noreferrer">
                      <BriefcaseIcon />
                      LinkedIn jobs
                      <ExternalIcon />
                    </a>
                  </div>

                  <footer className="org-foot">
                    <HiringButtons small value={o.openings} onChange={(v) => onSetOpenings(o.id, v)} />
                    <button
                      className="small"
                      title="Add a job at this organization"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAddJob(o);
                      }}
                    >
                      <PlusIcon /> Job
                    </button>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
