import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import Board from "./components/Board";
import JobForm from "./components/JobForm";
import JobPanel from "./components/JobPanel";
import JobTable from "./components/JobTable";
import { AutoIcon, BoardIcon, BriefcaseIcon, EyeIcon, MoonIcon, PlusIcon, SearchIcon, SunIcon, TableIcon } from "./components/Icons";
import OrgForm from "./components/OrgForm";
import OrgPanel from "./components/OrgPanel";
import Segmented from "./components/Segmented";
import Watchlist from "./components/Watchlist";
import { useTheme } from "./theme";
import { SIDE_LABELS, matchesLocation, type LocationFilter } from "./locations";
import {
  JOB_TYPES,
  JOB_TYPE_LABELS,
  STATUSES,
  STATUS_LABELS,
  WORK_MODES,
  WORK_MODE_LABELS,
  type Company,
  type Job,
  type JobInput,
  type JobType,
  type Openings,
  type Status,
  type WorkMode,
} from "./types";

type View = "board" | "table";
type Page = "jobs" | "watchlist";

// Saved only when the user picks a view. (Renamed from "jobpilot.view", which older builds wrote on every launch.)
const VIEW_KEY = "jobpilot.ui.view";
const PAGE_KEY = "jobpilot.ui.page";

function load<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // per-viewer convenience only
  }
}

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [orgs, setOrgs] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Table is the default until the user picks a view.
  const [view, setViewState] = useState<View>(() => load(VIEW_KEY, ["board", "table"], "table"));
  const [page, setPageState] = useState<Page>(() => load(PAGE_KEY, ["jobs", "watchlist"], "jobs"));
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [modeFilter, setModeFilter] = useState<WorkMode | "">("");
  const [typeFilter, setTypeFilter] = useState<JobType | "">("");
  const [locationFilter, setLocationFilter] = useState<LocationFilter>("");
  // null: closed; otherwise the job form is open, prefilled with these fields.
  const [newJob, setNewJob] = useState<Partial<JobInput> | null>(null);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [openOrgId, setOpenOrgId] = useState<number | null>(null);
  const [theme, setTheme] = useTheme();

  const refreshOrgs = useCallback(async () => {
    try {
      setOrgs(await api.listWatchlist());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [j, o] = await Promise.all([api.listJobs(), api.listWatchlist()]);
      setJobs(j);
      setOrgs(o);
      setError(null);
    } catch (e) {
      setError(`Can't reach the backend: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setView = useCallback((next: View) => {
    setViewState(next);
    save(VIEW_KEY, next);
  }, []);

  const setPage = useCallback((next: Page) => {
    setPageState(next);
    save(PAGE_KEY, next);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    return jobs.filter(
      (j) =>
        (!statusFilter || j.status === statusFilter) &&
        (!modeFilter || j.work_mode === modeFilter) &&
        (!typeFilter || j.job_type === typeFilter) &&
        matchesLocation(j, locationFilter) &&
        (!q ||
          [j.company, j.title, j.city, j.district].some((v) => v?.toLocaleLowerCase("tr").includes(q))),
    );
  }, [jobs, query, statusFilter, modeFilter, typeFilter, locationFilter]);

  const changeStatus = useCallback(
    async (id: number, status: Status) => {
      setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status } : j)));
      try {
        const updated = await api.updateJob(id, { status });
        setJobs((prev) => prev.map((j) => (j.id === id ? updated : j)));
      } catch (e) {
        setError((e as Error).message);
        refresh();
      }
    },
    [refresh],
  );

  const setOpenings = useCallback(async (id: number, openings: Openings) => {
    try {
      const updated = await api.updateCompany(id, { openings });
      setOrgs((prev) => prev.map((o) => (o.id === id ? updated : o)));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const upsertJob = (job: Job) => {
    setJobs((prev) => (prev.some((j) => j.id === job.id) ? prev.map((j) => (j.id === job.id ? job : j)) : [job, ...prev]));
    // A job can change its company's name or website, which the watchlist shows too.
    refreshOrgs();
  };

  const upsertOrg = (org: Company) => {
    setOrgs((prev) =>
      prev.some((o) => o.id === org.id) ? prev.map((o) => (o.id === org.id ? org : o)) : [...prev, org],
    );
    // Jobs show the company's name and logo.
    api.listJobs().then(setJobs).catch(() => {});
  };

  const addJobAt = (org: Company) => {
    setOpenOrgId(null);
    setNewJob({ company: org.name, company_website: org.website });
  };

  const applied = jobs.filter((j) => j.date_applied).length;
  const active = jobs.filter((j) => ["applied", "screening", "interview", "awaiting"].includes(j.status)).length;
  const openOrg = orgs.find((o) => o.id === openOrgId) ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            <BoardIcon />
          </span>
          <h1>Job Pilot</h1>
          <Segmented
            ariaLabel="Page"
            value={page}
            onChange={setPage}
            options={[
              { value: "jobs", label: `Jobs · ${jobs.length}`, icon: <BriefcaseIcon /> },
              { value: "watchlist", label: `Watchlist · ${orgs.length}`, icon: <EyeIcon /> },
            ]}
          />
          {page === "jobs" && (
            <div className="stats">
              <span className="chip">{applied} applied</span>
              <span className="chip accent">{active} in progress</span>
            </div>
          )}
        </div>
        <div className="topbar-actions">
          <Segmented
            ariaLabel="Theme"
            iconOnly
            value={theme}
            onChange={setTheme}
            options={[
              { value: "system", label: "Match system", icon: <AutoIcon /> },
              { value: "light", label: "Light", icon: <SunIcon /> },
              { value: "dark", label: "Night", icon: <MoonIcon /> },
            ]}
          />
          {page === "jobs" ? (
            <button className="primary" onClick={() => setNewJob({})}>
              <PlusIcon />
              Add job
            </button>
          ) : (
            <button className="primary" onClick={() => setCreatingOrg(true)}>
              <PlusIcon />
              Add organization
            </button>
          )}
        </div>
      </header>

      {page === "jobs" && (
        <div className="toolbar">
          <Segmented
            ariaLabel="View"
            value={view}
            onChange={setView}
            options={[
              { value: "table", label: "Table", icon: <TableIcon /> },
              { value: "board", label: "Board", icon: <BoardIcon /> },
            ]}
          />
          <label className="search">
            <SearchIcon />
            <input
              type="search"
              placeholder="Search company, title or district"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as Status | "")}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as JobType | "")}>
            <option value="">Any job type</option>
            {JOB_TYPES.map((t) => (
              <option key={t} value={t}>
                {JOB_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value as WorkMode | "")}>
            <option value="">Any work mode</option>
            {WORK_MODES.map((m) => (
              <option key={m} value={m}>
                {WORK_MODE_LABELS[m]}
              </option>
            ))}
          </select>
          <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value as LocationFilter)}>
            <option value="">Any location</option>
            <optgroup label="Istanbul">
              <option value="istanbul">All Istanbul</option>
              <option value="anadolu">{SIDE_LABELS.anadolu}</option>
              <option value="avrupa">{SIDE_LABELS.avrupa}</option>
            </optgroup>
            <option value="other">Other cities</option>
          </select>
        </div>
      )}

      {error && (
        <div className="error banner" role="alert">
          {error}
          <button className="link" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <main>
          <div className="empty">
            <span className="spinner" aria-label="Loading" />
          </div>
        </main>
      ) : page === "watchlist" ? (
        <Watchlist
          orgs={orgs}
          jobs={jobs}
          onOpen={setOpenOrgId}
          onAdd={() => setCreatingOrg(true)}
          onAddJob={addJobAt}
          onSetOpenings={setOpenings}
        />
      ) : (
        <main>
          {jobs.length === 0 ? (
            <div className="empty hero">
              <span className="logo big" aria-hidden>
                <BoardIcon />
              </span>
              <p>No jobs yet. Add the first one you are looking at.</p>
              <button className="primary" onClick={() => setNewJob({})}>
                Add your first job
              </button>
            </div>
          ) : view === "board" ? (
            <Board
              jobs={filtered}
              showInbox={jobs.some((j) => j.status === "inbox")}
              statusFilter={statusFilter}
              onOpen={setOpenId}
              onStatusChange={changeStatus}
            />
          ) : (
            <JobTable jobs={filtered} onOpen={setOpenId} onStatusChange={changeStatus} />
          )}
        </main>
      )}

      {newJob && (
        <JobForm
          initial={newJob}
          onCancel={() => setNewJob(null)}
          onSubmit={async (input) => {
            upsertJob(await api.createJob(input));
            setNewJob(null);
          }}
        />
      )}

      {creatingOrg && (
        <OrgForm
          onCancel={() => setCreatingOrg(false)}
          onSubmit={async (input) => {
            upsertOrg(await api.createCompany(input));
            setCreatingOrg(false);
          }}
        />
      )}

      {openOrg && (
        <OrgPanel
          key={openOrg.id}
          org={openOrg}
          jobs={jobs.filter((j) => j.company_id === openOrg.id)}
          onClose={() => setOpenOrgId(null)}
          onSaved={upsertOrg}
          onRemoved={(id) => {
            setOrgs((prev) => prev.filter((o) => o.id !== id));
            setOpenOrgId(null);
            api.listJobs().then(setJobs).catch(() => {});
          }}
          onOpenJob={(id) => {
            setOpenOrgId(null);
            setOpenId(id);
          }}
          onAddJob={addJobAt}
        />
      )}

      {openId !== null && (
        <JobPanel
          jobId={openId}
          onClose={() => setOpenId(null)}
          onSaved={upsertJob}
          onDeleted={(id) => {
            setJobs((prev) => prev.filter((j) => j.id !== id));
            setOpenId(null);
          }}
          onWatchChanged={refreshOrgs}
        />
      )}
    </div>
  );
}

