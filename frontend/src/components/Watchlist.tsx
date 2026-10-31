import { useMemo } from "react";
import { createPortal } from "react-dom";
import { daysSince, fmtAgo } from "../format";
import { STALE_AFTER_DAYS, linkedinJobsUrl } from "../orgs";
import { ORG_KINDS, ORG_KIND_LABELS, type Company, type Job, type Openings, type OrgKind } from "../types";
import CompanyLogo from "./CompanyLogo";
import FavoriteButton from "./FavoriteButton";
import HiringButtons from "./HiringButtons";
import { BriefcaseIcon, BuildingIcon, ExternalIcon, GlobeIcon, PlusIcon, SearchIcon, StarIcon } from "./Icons";

type HiringFilter = "" | Openings | "unchecked";
type Sort = "name" | "checked" | "added";
// "due": not checked for a while (or never), so worth a look.
export type Group = "all" | "favorites" | "due";
export const GROUPS: readonly Group[] = ["all", "favorites", "due"];

// Kept by the app, so they survive switching to the Jobs page and back.
export interface CompanyFilters {
  query: string;
  kind: OrgKind | "";
  hiring: HiringFilter;
  sort: Sort;
  group: Group;
}

export const DEFAULT_COMPANY_FILTERS: CompanyFilters = { query: "", kind: "", hiring: "", sort: "name", group: "all" };

interface Props {
  orgs: Company[];
  jobs: Job[];
  onOpen: (id: number) => void;
  onAdd: () => void;
  onAddJob: (org: Company) => void;
  onSetOpenings: (id: number, openings: Openings) => void;
  onToggleFavorite: (org: Company) => void;
  filters: CompanyFilters;
  onFiltersChange: (filters: CompanyFilters) => void;
  /** Where the page puts its lists in the app sidebar. */
  sideSlot: HTMLElement | null;
}

const isDue = (o: Company) => !o.last_checked_at || daysSince(o.last_checked_at) > STALE_AFTER_DAYS;

export default function Watchlist({
  orgs,
  jobs,
  onOpen,
  onAdd,
  onAddJob,
  onSetOpenings,
  onToggleFavorite,
  filters,
  onFiltersChange,
  sideSlot,
}: Props) {
  const { query, kind, hiring, sort, group } = filters;
  const set = (patch: Partial<CompanyFilters>) => onFiltersChange({ ...filters, ...patch });
  const setQuery = (query: string) => set({ query });
  const setKind = (kind: OrgKind | "") => set({ kind });
  const setHiring = (hiring: HiringFilter) => set({ hiring });
  const setSort = (sort: Sort) => set({ sort });
  const setGroup = (group: Group) => set({ group });

  const jobCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const j of jobs) if (!["rejected", "ghosted"].includes(j.status)) counts.set(j.company_id, (counts.get(j.company_id) ?? 0) + 1);
    return counts;
  }, [jobs]);

  const shown = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    const list = orgs.filter(
      (o) =>
        (group === "all" || (group === "favorites" ? o.watching : isDue(o))) &&
        (!kind || o.kind === kind) &&
        (!hiring || (hiring === "unchecked" ? !o.openings : o.openings === hiring)) &&
        (!q || [o.name, o.notes].some((v) => v.toLocaleLowerCase("tr").includes(q))),
    );
    const by: Record<Sort, (a: Company, b: Company) => number> = {
      name: (a, b) => a.name.localeCompare(b.name, "tr"),
      // Never checked first, then the longest ago.
      checked: (a, b) => (a.last_checked_at ?? "").localeCompare(b.last_checked_at ?? ""),
      added: (a, b) => (b.date_watched ?? "").localeCompare(a.date_watched ?? ""),
    };
    return list.sort(by[sort]);
  }, [orgs, query, kind, hiring, sort, group]);

  const hiringCount = orgs.filter((o) => o.openings === "hiring").length;
  const dueCount = orgs.filter(isDue).length;

  return (
    <>
      {sideSlot &&
        createPortal(
          <>
            {(
              [
                ["all", "All", orgs.length],
                ["favorites", "Favorites", orgs.filter((o) => o.watching).length],
                ["due", "Due for a check", dueCount],
              ] as [Group, string, number][]
            ).map(([g, label, n]) => (
              <button key={g} type="button" className={`side-item${group === g ? " on" : ""}`} onClick={() => setGroup(g)}>
                {g === "favorites" && <StarIcon filled />}
                <span className="side-label">{label}</span>
                <span className="side-count">{n}</span>
              </button>
            ))}
            <div className="side-heading">Type</div>
            {ORG_KINDS.filter((k) => orgs.some((o) => o.kind === k)).map((k) => (
              <button key={k} type="button" className={`side-item${kind === k ? " on" : ""}`} onClick={() => setKind(kind === k ? "" : k)}>
                <span className="side-label">{ORG_KIND_LABELS[k]}</span>
                <span className="side-count">{orgs.filter((o) => o.kind === k).length}</span>
              </button>
            ))}
          </>,
          sideSlot,
        )}

      <header className="page-head">
        <h2>{group === "favorites" ? "Favorites" : group === "due" ? "Due for a check" : "All companies"}{kind ? ` · ${ORG_KIND_LABELS[kind]}` : ""}</h2>
        <span className="muted page-summary">
          {hiringCount} hiring · {dueCount} due for a check
        </span>
        <span className="spacer" />
        <label className="search compact">
          <SearchIcon />
          <input type="search" data-page-search placeholder="Search companies" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <select aria-label="Hiring" value={hiring} onChange={(e) => setHiring(e.target.value as HiringFilter)}>
          <option value="">Hiring: any</option>
          <option value="hiring">Hiring · {hiringCount}</option>
          <option value="none">Not hiring · {orgs.filter((o) => o.openings === "none").length}</option>
          <option value="unchecked">Not checked yet · {orgs.filter((o) => !o.openings).length}</option>
        </select>
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="name">Sort by name</option>
          <option value="checked">Least recently checked</option>
          <option value="added">Recently added</option>
        </select>
        <button className="primary" onClick={onAdd}>
          <PlusIcon />
          Add organization
        </button>
      </header>

      <main>
        {orgs.length === 0 ? (
          <div className="empty hero">
            <span className="logo big" aria-hidden>
              <BuildingIcon />
            </span>
            <p>
              Every company you save a job at shows up here. Add companies, labs and universities you would like to work
              at, and star your favorites.
            </p>
            <button className="primary" onClick={onAdd}>
              <PlusIcon /> Add your first one
            </button>
          </div>
        ) : shown.length === 0 ? (
          <p className="empty">
            {group === "favorites" && !orgs.some((o) => o.watching)
              ? "No favorites yet. Click Favorite on a company to add it here."
              : group === "due" && dueCount === 0
                ? "Nothing is due: every company was checked in the last two weeks."
                : "No company matches these filters."}
          </p>
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
                    <FavoriteButton name={o.name} favorite={o.watching} onToggle={() => onToggleFavorite(o)} />
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
