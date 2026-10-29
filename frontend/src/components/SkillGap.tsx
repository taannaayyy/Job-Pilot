import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { SKILL_CATEGORY_LABELS, type RoleGroup, type SkillGap as Gap, type SkillMark, type SkillRow } from "../types";
import { PlusIcon, RefreshIcon, SearchIcon, SparkIcon, TargetIcon } from "./Icons";
import MarkPicker from "./MarkPicker";
import Segmented from "./Segmented";
import SkillPanel from "./SkillPanel";

type MarkFilter = "" | "open" | SkillMark | "unrated";

// Kept by the app, so they survive switching pages.
export interface GapFilters {
  groupId: number | null;
  query: string;
  mark: MarkFilter;
  category: string;
}

export const DEFAULT_GAP_FILTERS: GapFilters = { groupId: null, query: "", mark: "", category: "" };

interface Props {
  groups: RoleGroup[];
  onGroupsChanged: () => void;
  filters: GapFilters;
  onFiltersChange: (filters: GapFilters) => void;
  onOpenJob: (id: number) => void;
  onOpenAI: () => void;
  /** Changes whenever something outside this page may have changed the gap list. */
  refreshKey: number;
}

const matchesMark = (s: SkillRow, f: MarkFilter) =>
  !f ||
  (f === "open" ? s.mark === null || s.mark === "gap" || s.mark === "learning" : f === "unrated" ? s.mark === null : s.mark === f);

export default function SkillGap({ groups, onGroupsChanged, filters, onFiltersChange, onOpenJob, onOpenAI, refreshKey }: Props) {
  const { groupId, query, mark, category } = filters;
  const set = (patch: Partial<GapFilters>) => onFiltersChange({ ...filters, ...patch });
  const [gap, setGap] = useState<Gap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSkill, setOpenSkill] = useState<number | null>(null);
  // null: not editing; "" or a name: the new-group / rename field is open.
  const [naming, setNaming] = useState<{ id: number | null; name: string } | null>(null);

  const load = useCallback(
    () =>
      api.skillGap(groupId).then(
        (g) => {
          setGap(g);
          setError(null);
        },
        (e) => setError(e.message),
      ),
    [groupId],
  );

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // While descriptions are being read, the list fills in by itself.
  useEffect(() => {
    if (!gap?.pending) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [gap?.pending, load]);

  // A deleted group can't stay selected.
  useEffect(() => {
    if (groupId !== null && groups.length && !groups.some((g) => g.id === groupId)) set({ groupId: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, groupId]);

  const rows = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    return (gap?.skills ?? []).filter(
      (s) =>
        matchesMark(s, mark) &&
        (!category || s.category === category) &&
        (!q || s.name.toLocaleLowerCase("tr").includes(q)),
    );
  }, [gap, query, mark, category]);

  const categories = useMemo(
    () => [...new Set((gap?.skills ?? []).map((s) => s.category))].sort(),
    [gap],
  );

  const setMark = async (skill: SkillRow, next: SkillMark | null) => {
    setGap((g) => g && { ...g, skills: g.skills.map((s) => (s.id === skill.id ? { ...s, mark: next } : s)) });
    try {
      await api.updateSkill(skill.id, { mark: next }, groupId);
      load(); // coverage changes
    } catch (e) {
      setError((e as Error).message);
      load();
    }
  };

  const saveName = async () => {
    if (!naming || !naming.name.trim()) return setNaming(null);
    try {
      const g = naming.id === null ? await api.createGroup(naming.name) : await api.renameGroup(naming.id, naming.name);
      setNaming(null);
      onGroupsChanged();
      set({ groupId: g.id });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const selected = groups.find((g) => g.id === groupId) ?? null;
  const groupOptions = [
    { value: "all", label: `All targets · ${groups.reduce((n, g) => n + g.job_count, 0)}` },
    ...groups.map((g) => ({ value: String(g.id), label: `${g.name} · ${g.job_count}` })),
  ];
  const coverage = gap?.coverage ?? null;
  const open = (gap?.skills ?? []).filter((s) => matchesMark(s, "open")).length;

  return (
    <>
      <div className="toolbar">
        {groupOptions.length <= 4 ? (
          <Segmented
            ariaLabel="Role group"
            value={groupId === null ? "all" : String(groupId)}
            onChange={(v) => set({ groupId: v === "all" ? null : Number(v) })}
            options={groupOptions}
          />
        ) : (
          <select
            value={groupId === null ? "all" : String(groupId)}
            onChange={(e) => set({ groupId: e.target.value === "all" ? null : Number(e.target.value) })}
          >
            {groupOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        )}
        {naming ? (
          <form
            className="group-name"
            onSubmit={(e) => {
              e.preventDefault();
              saveName();
            }}
          >
            <input
              autoFocus
              value={naming.name}
              maxLength={100}
              placeholder="e.g. a role you want now or later"
              onChange={(e) => setNaming({ ...naming, name: e.target.value })}
              onKeyDown={(e) => e.key === "Escape" && setNaming(null)}
            />
            <button type="submit" className="primary">
              {naming.id === null ? "Add group" : "Rename"}
            </button>
            <button type="button" onClick={() => setNaming(null)}>
              Cancel
            </button>
          </form>
        ) : (
          <>
            <button onClick={() => setNaming({ id: null, name: "" })}>
              <PlusIcon />
              New group
            </button>
            {selected && (
              <>
                <button className="link quiet" onClick={() => setNaming({ id: selected.id, name: selected.name })}>
                  Rename
                </button>
                <button
                  className="link quiet"
                  onClick={async () => {
                    if (!confirm(`Delete the group ${selected.name}? Its jobs stay, they just stop being targets.`)) return;
                    try {
                      await api.deleteGroup(selected.id);
                      set({ groupId: null });
                      onGroupsChanged();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Delete
                </button>
              </>
            )}
          </>
        )}
        <span className="spacer" />
        <label className="search compact">
          <SearchIcon />
          <input type="search" placeholder="Search skills" value={query} onChange={(e) => set({ query: e.target.value })} />
        </label>
        <select value={mark} onChange={(e) => set({ mark: e.target.value as MarkFilter })}>
          <option value="">Any mark</option>
          <option value="open">To work on</option>
          <option value="unrated">No mark yet</option>
          <option value="gap">Gap</option>
          <option value="learning">Learning</option>
          <option value="have">Have</option>
          <option value="ignore">Ignored</option>
        </select>
        <select value={category} onChange={(e) => set({ category: e.target.value })}>
          <option value="">Any kind</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {SKILL_CATEGORY_LABELS[c] ?? c}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="error banner" role="alert">
          {error}
        </div>
      )}

      <main>
        {!gap ? (
          <div className="empty">
            <span className="spinner" aria-label="Loading" />
          </div>
        ) : gap.targets === 0 ? (
          <div className="empty hero">
            <span className="logo big" aria-hidden>
              <TargetIcon />
            </span>
            <p>
              <strong>No target jobs{selected ? ` in ${selected.name}` : ""} yet.</strong>
            </p>
            <p className="gap-help">
              Open any job, saved, applied or even rejected, and choose a role group under <b>Skill Gap</b>. Its
              description is read and its requirements are added up here, so you can see what to learn next.
            </p>
          </div>
        ) : (
          <>
            <section className="gap-summary">
              <div className="coverage">
                <div className="coverage-num">{coverage === null ? "–" : `${Math.round(coverage * 100)}%`}</div>
                <div className="coverage-text">
                  <strong>
                    of what {selected ? `your ${selected.name} targets` : "your targets"} ask for, that you have
                  </strong>
                  <span className="muted">
                    Must-haves count double. {open} requirement{open === 1 ? "" : "s"} to work on.
                  </span>
                  <div className="coverage-bar" aria-hidden>
                    <span style={{ width: `${(coverage ?? 0) * 100}%` }} />
                  </div>
                </div>
              </div>
              <div className="gap-status">
                <span className="chip">
                  {gap.targets} target{gap.targets === 1 ? "" : "s"}
                </span>
                {gap.pending > 0 && (
                  <span className="chip accent">
                    <span className="spinner tiny" /> Reading {gap.pending}…
                  </span>
                )}
                {gap.without_text > 0 && (
                  <span className="chip warn" title="Open the job and paste its description">
                    {gap.without_text} without a description
                  </span>
                )}
                {gap.failed > 0 && <span className="chip warn">{gap.failed} couldn't be read</span>}
                <span className="spacer" />
                <button className="small" onClick={onOpenAI} title="Choose the AI model that reads descriptions">
                  <SparkIcon />
                  AI model
                </button>
                <button
                  className="small"
                  title="Read every target's description again, e.g. after changing the model"
                  onClick={async () => {
                    try {
                      setGap(await api.extractAll(groupId));
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <RefreshIcon />
                  Read again
                </button>
              </div>
            </section>

            {rows.length === 0 ? (
              <div className="empty">
                {gap.skills.length === 0 ? "No requirements found yet." : "No requirements match these filters."}
              </div>
            ) : (
              <div className="table-wrap">
                <table className="gap-table">
                  <colgroup>
                    <col />
                    <col style={{ width: 150 }} />
                    <col style={{ width: 190 }} />
                    <col style={{ width: 120 }} />
                    <col style={{ width: 290 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Requirement</th>
                      <th>Kind</th>
                      <th>Asked for in</th>
                      <th>Must · Nice</th>
                      <th>You</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <tr key={s.id} onClick={() => setOpenSkill(s.id)} className={s.mark === "ignore" ? "ignored" : ""}>
                        <td className="strong">
                          {s.name}
                          {s.plan_note && <span className="plan-dot" title={s.plan_note} />}
                        </td>
                        <td className="muted">{SKILL_CATEGORY_LABELS[s.category] ?? s.category}</td>
                        <td>
                          <div className="demand">
                            <div className="demand-bar" aria-hidden>
                              <span style={{ width: `${(s.jobs / gap.targets) * 100}%` }} />
                            </div>
                            <span className="num">
                              {s.jobs} of {gap.targets}
                            </span>
                          </div>
                        </td>
                        <td className="num muted">
                          {s.must} · {s.nice}
                        </td>
                        <td>
                          <MarkPicker name={s.name} value={s.mark} onChange={(m) => setMark(s, m)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>

      {openSkill !== null && (
        <SkillPanel
          skillId={openSkill}
          groupId={groupId}
          onClose={() => setOpenSkill(null)}
          onChanged={load}
          onOpenJob={(id) => {
            setOpenSkill(null);
            onOpenJob(id);
          }}
        />
      )}
    </>
  );
}
