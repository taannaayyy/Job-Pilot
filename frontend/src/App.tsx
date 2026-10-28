import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import Board from "./components/Board";
import JobForm from "./components/JobForm";
import JobPanel from "./components/JobPanel";
import JobTable from "./components/JobTable";
import { AutoIcon, BoardIcon, MoonIcon, PlusIcon, SearchIcon, SunIcon, TableIcon } from "./components/Icons";
import Segmented from "./components/Segmented";
import { useTheme } from "./theme";
import { STATUSES, STATUS_LABELS, WORK_MODES, WORK_MODE_LABELS, type Job, type Status, type WorkMode } from "./types";

type View = "board" | "table";

const VIEW_KEY = "jobpilot.view";

function loadView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "board";
  } catch {
    return "board";
  }
}

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>(loadView);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [modeFilter, setModeFilter] = useState<WorkMode | "">("");
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [theme, setTheme] = useTheme();

  const refresh = useCallback(async () => {
    try {
      setJobs(await api.listJobs());
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

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch {
      // per-viewer convenience only
    }
  }, [view]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return jobs.filter(
      (j) =>
        (!statusFilter || j.status === statusFilter) &&
        (!modeFilter || j.work_mode === modeFilter) &&
        (!q || j.company.toLowerCase().includes(q) || j.title.toLowerCase().includes(q)),
    );
  }, [jobs, query, statusFilter, modeFilter]);

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

  const upsert = (job: Job) =>
    setJobs((prev) => (prev.some((j) => j.id === job.id) ? prev.map((j) => (j.id === job.id ? job : j)) : [job, ...prev]));

  const applied = jobs.filter((j) => j.date_applied).length;
  const active = jobs.filter((j) => ["applied", "screening", "interview"].includes(j.status)).length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            <BoardIcon />
          </span>
          <h1>Job Pilot</h1>
          <div className="stats">
            <span className="chip">{jobs.length} tracked</span>
            <span className="chip">{applied} applied</span>
            <span className="chip accent">{active} in progress</span>
          </div>
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
          <button className="primary" onClick={() => setCreating(true)}>
            <PlusIcon />
            Add job
          </button>
        </div>
      </header>

      <div className="toolbar">
        <Segmented
          ariaLabel="View"
          value={view}
          onChange={setView}
          options={[
            { value: "board", label: "Board", icon: <BoardIcon /> },
            { value: "table", label: "Table", icon: <TableIcon /> },
          ]}
        />
        <label className="search">
          <SearchIcon />
          <input
            type="search"
            placeholder="Search company or title"
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
        <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value as WorkMode | "")}>
          <option value="">Any work mode</option>
          {WORK_MODES.map((m) => (
            <option key={m} value={m}>
              {WORK_MODE_LABELS[m]}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="error banner" role="alert">
          {error}
          <button className="link" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <main>
        {loading ? (
          <div className="empty">
            <span className="spinner" aria-label="Loading" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="empty hero">
            <span className="logo big" aria-hidden>
              <BoardIcon />
            </span>
            <p>No jobs yet. Add the first one you are looking at.</p>
            <button className="primary" onClick={() => setCreating(true)}>
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

      {creating && (
        <JobForm
          onCancel={() => setCreating(false)}
          onSubmit={async (input) => {
            upsert(await api.createJob(input));
            setCreating(false);
          }}
        />
      )}

      {openId !== null && (
        <JobPanel
          jobId={openId}
          onClose={() => setOpenId(null)}
          onSaved={upsert}
          onDeleted={(id) => {
            setJobs((prev) => prev.filter((j) => j.id !== id));
            setOpenId(null);
          }}
        />
      )}
    </div>
  );
}
