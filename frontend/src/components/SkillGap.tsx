import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { children, descendants, flat } from "../tree";
import type { RoleGroup, SkillGap as Gap, SkillGroupNode, SkillMark, SkillRow } from "../types";
import { ChevronIcon, PlusIcon, RefreshIcon, SearchIcon, SparkIcon, TargetIcon, TreeIcon } from "./Icons";
import MarkPicker from "./MarkPicker";
import MultiFilter from "./MultiFilter";
import Segmented from "./Segmented";
import SkillPanel from "./SkillPanel";
import TreeDialog from "./TreeDialog";

// "none": no mark yet.
const MARK_OPTIONS: { value: SkillMark | "none"; label: string }[] = [
  { value: "none", label: "No mark yet" },
  { value: "gap", label: "Gap" },
  { value: "learning", label: "Learning" },
  { value: "have", label: "Have" },
  { value: "ignore", label: "Ignore" },
];

// Kept by the app, so they survive switching pages.
export interface GapFilters {
  groupId: number | null;
  query: string;
  /** Marks not shown; the user can turn off any number of them. */
  hiddenMarks: string[];
  /** Tree groups not shown (ids, "unsorted"); null until the user changes it: Soft skills are hidden. */
  hiddenTree: string[] | null;
  /** Collapsed tree groups. */
  collapsed: string[];
}

export const DEFAULT_GAP_FILTERS: GapFilters = { groupId: null, query: "", hiddenMarks: [], hiddenTree: null, collapsed: [] };
// Groups of the starting tree hidden until the user shows them (taxonomy.HIDDEN_BY_DEFAULT).
const HIDDEN_BY_DEFAULT = ["soft"];
const UNSORTED = "unsorted";

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

const isOpen = (s: SkillRow) => s.mark === null || s.mark === "gap" || s.mark === "learning";

export default function SkillGap({ groups, onGroupsChanged, filters, onFiltersChange, onOpenJob, onOpenAI, refreshKey }: Props) {
  const { groupId, query, hiddenMarks, collapsed } = filters;
  const set = (patch: Partial<GapFilters>) => onFiltersChange({ ...filters, ...patch });
  const [gap, setGap] = useState<Gap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSkill, setOpenSkill] = useState<number | null>(null);
  // null: not editing; "" or a name: the new-group / rename field is open.
  const [naming, setNaming] = useState<{ id: number | null; name: string } | null>(null);
  const [treeOpen, setTreeOpen] = useState(false);
  const tree: SkillGroupNode[] = gap?.groups ?? [];

  // A hidden group hides everything under it.
  const hiddenTree = useMemo(() => {
    const chosen = filters.hiddenTree ?? tree.filter((g) => g.key && HIDDEN_BY_DEFAULT.includes(g.key)).map((g) => String(g.id));
    return new Set(chosen.flatMap((id) => (id === UNSORTED ? [UNSORTED] : descendants(tree, Number(id)).map(String))));
  }, [filters.hiddenTree, tree]);

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
        !hiddenMarks.includes(s.mark ?? "none") &&
        !hiddenTree.has(s.group_id === null ? UNSORTED : String(s.group_id)) &&
        (!q || s.name.toLocaleLowerCase("tr").includes(q)),
    );
  }, [gap, query, hiddenMarks, hiddenTree]);

  const treeOptions = useMemo(() => {
    const skillsIn = (id: number) => {
      const ids = new Set(descendants(tree, id));
      return (gap?.skills ?? []).filter((s) => s.group_id !== null && ids.has(s.group_id)).length;
    };
    const options = flat(tree).map(({ group, depth }) => ({
      value: String(group.id),
      label: `${"   ".repeat(depth)}${group.name}`,
      count: skillsIn(group.id),
    }));
    const unsorted = (gap?.skills ?? []).filter((s) => s.group_id === null).length;
    return unsorted ? [...options, { value: UNSORTED, label: "Unsorted", count: unsorted }] : options;
  }, [gap, tree]);

  const markOptions = useMemo(
    () => MARK_OPTIONS.map((o) => ({ ...o, count: (gap?.skills ?? []).filter((s) => (s.mark ?? "none") === o.value).length })),
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

  const toggle = (id: string) =>
    set({ collapsed: collapsed.includes(id) ? collapsed.filter((c) => c !== id) : [...collapsed, id] });

  /** Group headers with their skills; libraries under their language. */
  function renderTree(): ReactNode[] {
    if (!gap) return [];
    const out: ReactNode[] = [];

    const skillRow = (s: SkillRow, depth: number, parentName?: string) => (
      <tr key={s.id} onClick={() => setOpenSkill(s.id)} className={s.mark === "ignore" ? "ignored" : ""}>
        <td className="strong" style={{ paddingLeft: 12 + depth * 18 }}>
          {s.name}
          {parentName && <span className="muted parent-hint"> · {parentName}</span>}
          {s.plan_note && <span className="plan-dot" title={s.plan_note} />}
          {s.details.length > 0 && <div className="row-detail">{s.details.join(" · ")}</div>}
        </td>
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
          {s.years.map((y) => (
            <span key={y} className="years-tag">
              {y} yrs
            </span>
          ))}
        </td>
        <td>
          <MarkPicker name={s.name} value={s.mark} onChange={(m) => setMark(s, m)} />
        </td>
      </tr>
    );

    // A skill and, under it, the skills that belong to it (pandas under Python).
    const skillTree = (list: SkillRow[], depth: number) => {
      const here = new Set(list.map((s) => s.id));
      const byId = new Map(gap.skills.map((s) => [s.id, s]));
      const roots = list.filter((s) => s.parent_id === null || !here.has(s.parent_id));
      const walk = (s: SkillRow, d: number, parentName?: string) => {
        out.push(skillRow(s, d, parentName));
        list.filter((c) => c.parent_id === s.id).forEach((c) => walk(c, d + 1));
      };
      roots.forEach((s) => walk(s, depth, s.parent_id !== null ? byId.get(s.parent_id)?.name : undefined));
    };

    const header = (id: string, name: string, depth: number, list: SkillRow[]) => {
      const have = list.filter((s) => s.mark === "have").length;
      const closed = collapsed.includes(id);
      out.push(
        <tr key={`g${id}`} className={`group-row depth-${Math.min(depth, 2)}`} onClick={() => toggle(id)}>
          <td colSpan={5} style={{ paddingLeft: 10 + depth * 18 }}>
            <span className={`group-chevron ${closed ? "closed" : ""}`}>
              <ChevronIcon />
            </span>
            {name}
            <span className="group-count">
              {list.length} · you have {have}
            </span>
          </td>
        </tr>,
      );
      return closed;
    };

    const group = (g: SkillGroupNode, depth: number) => {
      const ids = new Set(descendants(tree, g.id));
      const inside = rows.filter((s) => s.group_id !== null && ids.has(s.group_id));
      if (!inside.length) return;
      if (header(String(g.id), g.name, depth, inside)) return;
      skillTree(rows.filter((s) => s.group_id === g.id), depth + 1);
      children(tree, g.id).forEach((c) => group(c, depth + 1));
    };

    children(tree, null).forEach((g) => group(g, 0));
    const unsorted = rows.filter((s) => s.group_id === null || !tree.some((g) => g.id === s.group_id));
    if (unsorted.length && !header(UNSORTED, "Unsorted", 0, unsorted)) skillTree(unsorted, 1);
    return out;
  }

  const selected = groups.find((g) => g.id === groupId) ?? null;
  const groupOptions = [
    { value: "all", label: `All targets · ${groups.reduce((n, g) => n + g.job_count, 0)}` },
    ...groups.map((g) => ({ value: String(g.id), label: `${g.name} · ${g.job_count}` })),
  ];
  const coverage = gap?.coverage ?? null;
  const open = (gap?.skills ?? []).filter(isOpen).length;

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
        <button onClick={onOpenAI} title="Choose the AI model that reads job descriptions">
          <SparkIcon />
          AI model
        </button>
        <label className="search compact">
          <SearchIcon />
          <input type="search" placeholder="Search skills" value={query} onChange={(e) => set({ query: e.target.value })} />
        </label>
        <MultiFilter label="Mark" options={markOptions} hidden={hiddenMarks} onChange={(h) => set({ hiddenMarks: h })} />
        <MultiFilter
          label="Show"
          options={treeOptions}
          hidden={treeOptions.map((o) => o.value).filter((v) => hiddenTree.has(v))}
          onChange={(h) => set({ hiddenTree: h })}
        />
        <button onClick={() => setTreeOpen(true)} title="Rename, move and add groups, or ask the AI for recommendations">
          <TreeIcon />
          Edit tree
        </button>
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
                <button
                  className="small"
                  title="Read every target's description again, e.g. after changing the model. Uses one model call per target."
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
                    <col style={{ width: 190 }} />
                    <col style={{ width: 120 }} />
                    <col style={{ width: 110 }} />
                    <col style={{ width: 290 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Requirement</th>
                      <th>Asked for in</th>
                      <th>Must · Nice</th>
                      <th>Years</th>
                      <th>You</th>
                    </tr>
                  </thead>
                  <tbody>{renderTree()}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>

      {treeOpen && <TreeDialog tree={tree} onChanged={load} onClose={() => setTreeOpen(false)} />}

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
