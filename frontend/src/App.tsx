import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import Board from "./components/Board";
import JobForm from "./components/JobForm";
import JobPanel from "./components/JobPanel";
import JobTable from "./components/JobTable";
import ExtensionDialog from "./components/ExtensionDialog";
import AISettingsDialog from "./components/AISettingsDialog";
import SkillGap, { DEFAULT_GAP_FILTERS, GAP_VIEWS, type GapFilters } from "./components/SkillGap";
import {
  AutoIcon,
  BoardIcon,
  BriefcaseIcon,
  BuildingIcon,
  MoonIcon,
  PlusIcon,
  PuzzleIcon,
  SearchIcon,
  SunIcon,
  TableIcon,
  TargetIcon,
} from "./components/Icons";
import OrgForm from "./components/OrgForm";
import OrgPanel from "./components/OrgPanel";
import Segmented from "./components/Segmented";
import Watchlist, { type CompanyFilters, DEFAULT_COMPANY_FILTERS, GROUPS } from "./components/Watchlist";
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
  type RoleGroup,
  type Status,
  type WorkMode,
} from "./types";

type View = "board" | "table";
type Page = "jobs" | "watchlist" | "skills";
const PAGES: readonly Page[] = ["jobs", "watchlist", "skills"];

// Saved only when the user picks a view. (Renamed from "jobpilot.view", which older builds wrote on every launch.)
const VIEW_KEY = "jobpilot.ui.view";
const PAGE_KEY = "jobpilot.ui.page";
const COMPANY_GROUP_KEY = "jobpilot.ui.companyGroup";
const ROLE_GROUP_KEY = "jobpilot.ui.roleGroup";
// Renamed from "jobpilot.ui.gapHidden", which held the flat kinds before the tree.
const GAP_VIEW_KEY = "jobpilot.ui.gapView";

function load<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function loadGroupId(): number | null {
  try {
    const id = Number(localStorage.getItem(ROLE_GROUP_KEY) || NaN);
    return Number.isInteger(id) ? id : null;
  } catch {
    return null;
  }
}

type GapLook = Pick<GapFilters, "view" | "sort" | "hiddenTree" | "onlyAsked" | "zoom" | "collapsed">;
// 2: the default view became the diagram. 3: the tree became skills only, so hidden and collapsed
// nodes saved before (group ids) mean nothing now.
const GAP_LOOK_VERSION = 3;

/** How Skill Gap shows the tree (view, order, hidden groups, collapsed rows), remembered between launches. */
function loadGapView(): GapLook {
  try {
    const v = JSON.parse(localStorage.getItem(GAP_VIEW_KEY) || "{}");
    const list = (x: unknown) => (Array.isArray(x) ? x.filter((i): i is string => typeof i === "string") : []);
    const current = v.v === GAP_LOOK_VERSION;
    return {
      view: (v.v ?? 0) >= 2 && GAP_VIEWS.includes(v.view) ? v.view : DEFAULT_GAP_FILTERS.view,
      sort: ["tree", "count", "name"].includes(v.sort) && current ? v.sort : DEFAULT_GAP_FILTERS.sort,
      hiddenTree: current && Array.isArray(v.hiddenTree) ? list(v.hiddenTree) : null,
      onlyAsked: v.onlyAsked === true,
      zoom: typeof v.zoom === "number" && v.zoom >= 0.3 && v.zoom <= 2 ? v.zoom : 1,
      collapsed: current ? list(v.collapsed).filter((c) => /^s\d+$|^unsorted$/.test(c)) : [],
    };
  } catch {
    return { view: DEFAULT_GAP_FILTERS.view, sort: DEFAULT_GAP_FILTERS.sort, hiddenTree: null, onlyAsked: false, zoom: 1, collapsed: [] };
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
  const [page, setPageState] = useState<Page>(() => load(PAGE_KEY, PAGES, "jobs"));
  // All or Favorites is remembered between launches; the other company filters until the app closes.
  const [orgFilters, setOrgFiltersState] = useState<CompanyFilters>(() => ({
    ...DEFAULT_COMPANY_FILTERS,
    group: load(COMPANY_GROUP_KEY, GROUPS, "all"),
  }));
  const setOrgFilters = (filters: CompanyFilters) => {
    if (filters.group !== orgFilters.group) save(COMPANY_GROUP_KEY, filters.group);
    setOrgFiltersState(filters);
  };
  const [groups, setGroups] = useState<RoleGroup[]>([]);
  // The role group shown on Skill Gap is remembered between launches, like All or Favorites.
  const [gapFilters, setGapFiltersState] = useState<GapFilters>(() => ({
    ...DEFAULT_GAP_FILTERS,
    ...loadGapView(),
    groupId: loadGroupId(),
  }));
  const setGapFilters = (filters: GapFilters) => {
    if (filters.groupId !== gapFilters.groupId) save(ROLE_GROUP_KEY, filters.groupId === null ? "" : String(filters.groupId));
    if (
      filters.view !== gapFilters.view ||
      filters.sort !== gapFilters.sort ||
      filters.hiddenTree !== gapFilters.hiddenTree ||
      filters.onlyAsked !== gapFilters.onlyAsked ||
      filters.zoom !== gapFilters.zoom ||
      filters.collapsed !== gapFilters.collapsed
    ) {
      const look: GapLook = {
        view: filters.view,
        sort: filters.sort,
        hiddenTree: filters.hiddenTree,
        onlyAsked: filters.onlyAsked,
        zoom: filters.zoom,
        collapsed: filters.collapsed,
      };
      save(GAP_VIEW_KEY, JSON.stringify({ ...look, v: GAP_LOOK_VERSION }));
    }
    setGapFiltersState(filters);
  };
  // Bumped when a job changes, so Skill Gap reloads its list.
  const [gapVersion, setGapVersion] = useState(0);
  const [aiOpen, setAiOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [modeFilter, setModeFilter] = useState<WorkMode | "">("");
  const [typeFilter, setTypeFilter] = useState<JobType | "">("");
  const [locationFilter, setLocationFilter] = useState<LocationFilter>("");
  // Shows the jobs kept only to study a role, which the board leaves out.
  const [studyOnly, setStudyOnly] = useState(false);
  // null: closed; otherwise the job form is open, prefilled with these fields.
  const [newJob, setNewJob] = useState<Partial<JobInput> | null>(null);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [openOrgId, setOpenOrgId] = useState<number | null>(null);
  const [theme, setTheme] = useTheme();
  const [extensionOpen, setExtensionOpen] = useState(false);
  // Program holding the extension's port, if the app had to open on another one.
  const [portBlockedBy, setPortBlockedBy] = useState<string | null>(null);

  const refreshOrgs = useCallback(async () => {
    try {
      setOrgs(await api.listCompanies());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refreshGroups = useCallback(() => {
    api.listGroups().then(setGroups, (e) => setError((e as Error).message));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [j, o] = await Promise.all([api.listJobs(), api.listCompanies()]);
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
    refreshGroups();
    api
      .getExtension()
      .then((info) => setPortBlockedBy(info.port_blocked_by))
      .catch(() => {});
  }, [refresh, refreshGroups]);

  // Jobs saved from LinkedIn arrive while the window is open; show them when it is focused again.
  useEffect(() => {
    const onFocus = () => {
      api.listJobs().then(setJobs).catch(() => {});
      refreshOrgs();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshOrgs]);

  const setView = useCallback((next: View) => {
    setViewState(next);
    save(VIEW_KEY, next);
  }, []);

  const setPage = useCallback((next: Page) => {
    setPageState(next);
    save(PAGE_KEY, next);
  }, []);

  // Jobs kept only to study a role stay off the job board.
  const boardJobs = useMemo(() => jobs.filter((j) => !j.study_only), [jobs]);
  const studyJobs = useMemo(() => jobs.filter((j) => j.study_only), [jobs]);
  const shownJobs = studyOnly ? studyJobs : boardJobs;

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    return shownJobs.filter(
      (j) =>
        (!statusFilter || j.status === statusFilter) &&
        (!modeFilter || j.work_mode === modeFilter) &&
        (!typeFilter || j.job_type === typeFilter) &&
        matchesLocation(j, locationFilter) &&
        (!q ||
          [j.company, j.title, j.city, j.district].some((v) => v?.toLocaleLowerCase("tr").includes(q))),
    );
  }, [shownJobs, query, statusFilter, modeFilter, typeFilter, locationFilter]);

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

  const toggleFavorite = useCallback(
    async (org: Company) => {
      try {
        await api.updateCompany(org.id, { watching: !org.watching });
        await refreshOrgs();
        // Jobs show whether their company is a favorite.
        setJobs(await api.listJobs());
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [refreshOrgs],
  );

  const setOpenings = useCallback(async (id: number, openings: Openings) => {
    try {
      const updated = await api.updateCompany(id, { openings });
      setOrgs((prev) => prev.map((o) => (o.id === id ? updated : o)));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const upsertJob = useCallback(
    (job: Job) => {
      setJobs((prev) => (prev.some((j) => j.id === job.id) ? prev.map((j) => (j.id === job.id ? job : j)) : [job, ...prev]));
      // A new job can add a company, and a job can change its company's name or website.
      refreshOrgs();
      // ...or become a target, which changes the role groups' counts and the gap list.
      refreshGroups();
      setGapVersion((v) => v + 1);
    },
    [refreshOrgs, refreshGroups],
  );

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

  const applied = boardJobs.filter((j) => j.date_applied).length;
  const active = boardJobs.filter((j) => ["applied", "screening", "interview", "awaiting"].includes(j.status)).length;
  const targetCount = groups.reduce((n, g) => n + g.job_count, 0);
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
              { value: "jobs", label: `Jobs · ${boardJobs.length}`, icon: <BriefcaseIcon /> },
              { value: "watchlist", label: `Companies · ${orgs.length}`, icon: <BuildingIcon /> },
              { value: "skills", label: `Skill Gap · ${targetCount}`, icon: <TargetIcon /> },
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
          <button onClick={() => setExtensionOpen(true)} title="Save jobs from LinkedIn with the Chrome extension">
            <PuzzleIcon />
            Extension
          </button>
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
          {page === "skills" ? null : page === "jobs" ? (
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
          {(studyOnly || studyJobs.length > 0) && (
            <label className="check-chip" title="Show only the jobs kept to study a role, which the board leaves out">
              <input type="checkbox" checked={studyOnly} onChange={(e) => setStudyOnly(e.target.checked)} />
              Study only · {studyJobs.length}
            </label>
          )}
        </div>
      )}

      {portBlockedBy && (
        <div className="warn banner" role="status">
          Saving from LinkedIn is off: {portBlockedBy} is using the extension's port. Quit it and reopen Job Pilot.
          <span className="spacer" />
          <button className="link" onClick={() => setPortBlockedBy(null)}>
            Dismiss
          </button>
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
      ) : page === "skills" ? (
        <SkillGap
          groups={groups}
          onGroupsChanged={() => {
            refreshGroups();
            api.listJobs().then(setJobs).catch(() => {});
          }}
          filters={gapFilters}
          onFiltersChange={setGapFilters}
          onOpenJob={setOpenId}
          onOpenAI={() => setAiOpen(true)}
          refreshKey={gapVersion}
        />
      ) : page === "watchlist" ? (
        <Watchlist
          orgs={orgs}
          jobs={jobs}
          onOpen={setOpenOrgId}
          onAdd={() => setCreatingOrg(true)}
          onAddJob={addJobAt}
          onSetOpenings={setOpenings}
          onToggleFavorite={toggleFavorite}
          filters={orgFilters}
          onFiltersChange={setOrgFilters}
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
              showInbox={shownJobs.some((j) => j.status === "inbox")}
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
          onRemoved={() => {
            refreshOrgs();
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

      {extensionOpen && <ExtensionDialog onClose={() => setExtensionOpen(false)} />}

      {aiOpen && <AISettingsDialog onClose={() => setAiOpen(false)} onSaved={() => setGapVersion((v) => v + 1)} />}

      {openId !== null && (
        <JobPanel
          jobId={openId}
          onClose={() => setOpenId(null)}
          onSaved={upsertJob}
          onDeleted={(id) => {
            // Companies, role groups and Skill Gap each hold their own copy of the job.
            setJobs((prev) => prev.filter((j) => j.id !== id));
            setOpenId(null);
            refreshOrgs();
            refreshGroups();
            setGapVersion((v) => v + 1);
          }}
          onWatchChanged={refreshOrgs}
          groups={groups}
          onGroupsChanged={refreshGroups}
        />
      )}
    </div>
  );
}

