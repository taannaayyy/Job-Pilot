import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { shortcut } from "../platform";
import { buildMap, findNode, lineage, UNSORTED, UNSORTED_TARGET, waitingMap, type MapNode, type MapSort } from "../skillmap";
import { children, descendants, moved } from "../tree";
import type { RoleGroup, SkillGap as Gap } from "../types";
import { CheckIcon, EyeIcon, PlusIcon, SearchIcon } from "./Icons";
import Popover from "./Popover";
import NodeDialog, { type NodeFields } from "./NodeDialog";
import Segmented from "./Segmented";
import { ColumnsView, DiagramView, MapDetails, OutlineView, useTreeDrag, type TreeEdit } from "./SkillMapViews";
import UnsortedPanel from "./UnsortedPanel";

export type GapView = "outline" | "columns" | "diagram";
export const GAP_VIEWS: readonly GapView[] = ["outline", "columns", "diagram"];

// Kept by the app, so they survive switching pages.
export interface GapFilters {
  groupId: number | null;
  query: string;
  view: GapView;
  sort: MapSort;
  /** Tree nodes not shown ("s12", "unsorted"); null until the user changes it: Soft skills are hidden. */
  hiddenTree: string[] | null;
  /** Leaves out what no posting asks for (the whole tree is shown otherwise, to edit it). */
  onlyAsked: boolean;
  /** The diagram's zoom, 1 = 100%. */
  zoom: number;
  /** Collapsed rows of the outline ("s12", "unsorted"). */
  collapsed: string[];
  /** The skill shown in the details ("s12", "unsorted"). */
  selected: string | null;
}

export const DEFAULT_GAP_FILTERS: GapFilters = {
  groupId: null,
  query: "",
  view: "diagram",
  sort: "tree",
  hiddenTree: null,
  onlyAsked: false,
  zoom: 1,
  collapsed: [],
  selected: null,
};
// Top-level nodes hidden until the user shows them: they rarely tell you what to learn next.
const HIDDEN_BY_DEFAULT = ["Soft skills"];

interface Props {
  groups: RoleGroup[];
  onGroupsChanged: () => void;
  filters: GapFilters;
  onFiltersChange: (filters: GapFilters) => void;
  onOpenJob: (id: number) => void;
  /** The AI settings, for writing descriptions. */
  onOpenAI: () => void;
  /** Changes whenever something outside this page may have changed the gap list. */
  refreshKey: number;
  /** Where the page puts its lists in the app sidebar. */
  sideSlot: HTMLElement | null;
}

export default function SkillGap({ groups, onGroupsChanged, filters, onFiltersChange, onOpenJob, onOpenAI, refreshKey, sideSlot }: Props) {
  const { groupId, query, view, sort, collapsed, selected: selectedKey } = filters;
  const set = (patch: Partial<GapFilters>) => onFiltersChange({ ...filters, ...patch });
  const [gap, setGap] = useState<Gap | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null: not editing; "" or a name: the new-group / rename field is open.
  const [naming, setNaming] = useState<{ id: number | null; name: string } | null>(null);
  // The skills waiting in Unsorted, in place of the details.
  const [unsortedOpen, setUnsortedOpen] = useState(false);
  // The pop-up that adds under a node (parent; null: the top level) or edits one.
  const [dialog, setDialog] = useState<{ add: MapNode | null } | { edit: MapNode } | null>(null);
  const nodes = useMemo(() => gap?.skills ?? [], [gap]);

  // The areas the user hid (Soft skills until they choose); a hidden node hides everything under it.
  const hiddenAreas = useMemo(
    () =>
      filters.hiddenTree ??
      nodes.filter((n) => n.placed && n.parent_id === null && HIDDEN_BY_DEFAULT.includes(n.name)).map((n) => `s${n.id}`),
    [filters.hiddenTree, nodes],
  );
  const hiddenTree = useMemo(
    () =>
      new Set(
        hiddenAreas.flatMap((key) => (key === UNSORTED ? [UNSORTED] : descendants(nodes, Number(key.slice(1))).map((id) => `s${id}`))),
      ),
    [hiddenAreas, nodes],
  );

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


  // A deleted group can't stay selected.
  useEffect(() => {
    if (groupId !== null && groups.length && !groups.some((g) => g.id === groupId)) set({ groupId: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, groupId]);

  const roots = useMemo(
    () => buildMap(nodes, hiddenTree, query, view === "diagram" ? "tree" : sort, filters.onlyAsked),
    [nodes, hiddenTree, query, view, sort, filters.onlyAsked],
  );
  const waiting = useMemo(() => waitingMap(nodes, query), [nodes, query]);
  // The details show a skill in Unsorted too; the views only what is in the tree.
  const selectedNode = findNode([...roots, ...waiting], selectedKey);
  const selectedInTree = findNode(roots, selectedKey);
  // One area of the tree at a time, picked in the sidebar; a search looks through all of them.
  const areaNode = lineage(selectedInTree)[0] ?? roots[0] ?? null;
  const shownRoots = query.trim() ? roots : areaNode ? [areaNode] : [];

  // Every view, and the pane beside it, fills the window down to the bottom (--view-h) and scrolls
  // inside itself, so the page keeps one height whichever view is shown.
  const area = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    const fit = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      el.style.setProperty("--view-h", `${Math.max(360, window.innerHeight - top - 20)}px`);
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  });

  /** Runs a change to the tree, then shows the tree as the server has it. */
  const change = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
    load();
  };
  const move = (id: number, parent: number | null, index: number) => {
    setGap((g) => g && { ...g, skills: moved(g.skills, id, parent, index) });
    if (parent !== null) set({ collapsed: collapsed.filter((c) => c !== `s${parent}`) });
    change(() => api.updateSkill(id, { parent_id: parent, index }, null));
  };
  const unsort = (id: number) => change(() => api.updateSkill(id, { placed: false }, null));
  // The last removed skill, offered back for a few seconds; Cmd+Z brings it back any time.
  const [removed, setRemoved] = useState<string | null>(null);
  useEffect(() => {
    if (!removed) return;
    const timer = window.setTimeout(() => setRemoved(null), 8000);
    return () => clearTimeout(timer);
  }, [removed]);
  const remove = (node: MapNode) => {
    const s = node.skill;
    if (!s) return false;
    const n = node.direct;
    const off = n ? ` It is taken off the ${n === 1 ? "posting that asks" : `${n} postings that ask`} for it.` : "";
    const under = s.placed && children(nodes, s.id).length ? " What is under it moves up one level." : "";
    if ((off || under) && !confirm(`Remove ${s.name}?${off}${under} ${shortcut("Z")} brings it back.`)) return false;
    if (selectedKey === node.key) set({ selected: null });
    change(async () => {
      await api.deleteSkill(s.id);
      setRemoved(s.name);
    });
    return true;
  };
  const undoRemove = useCallback(async () => {
    try {
      const { name } = await api.undoRemoveSkill();
      setRemoved(null);
      setError(null);
      const back = (await api.skillGap(groupId)).skills.find((n) => n.name === name);
      if (back) set({ selected: `s${back.id}` });
    } catch (e) {
      setRemoved(null);
      // Nothing removed in this session: Cmd+Z does nothing, as anywhere else.
      if (!(e as Error).message.includes("Nothing to undo")) setError((e as Error).message);
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, load, filters]);
  // Cmd+Z (Ctrl+Z elsewhere) outside a text field: a text field keeps its own undo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.key.toLowerCase() !== "z") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      if (document.querySelector(".overlay, .edit-pop-overlay")) return; // a pop-up is open
      e.preventDefault();
      undoRemove();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undoRemove]);
  const edit: TreeEdit = {
    onAdd: (parent) => setDialog({ add: parent }),
    onEdit: (node) => setDialog({ edit: node }),
    onRemove: remove,
    drag: useTreeDrag(nodes, move, unsort),
  };
  const saveDialog = ({ name, description, isGroup, isTool }: NodeFields) => {
    if (!dialog) return;
    if ("add" in dialog) {
      const parent = dialog.add?.skill?.id ?? null;
      if (dialog.add) set({ collapsed: collapsed.filter((c) => c !== dialog.add!.key) });
      change(() => api.createSkill({ name, description, is_group: isGroup, is_tool: isTool, parent_id: parent }));
    } else {
      const s = dialog.edit.skill!;
      const body: { name?: string; description?: string; is_tool?: boolean } = {};
      if (name.trim() !== s.name) body.name = name;
      if (description !== s.description) body.description = description;
      if (!isGroup && isTool !== s.is_tool) body.is_tool = isTool;
      if (Object.keys(body).length) change(() => api.updateSkill(s.id, body, null));
    }
    setDialog(null);
  };
  const total = gap?.targets ?? 0;
  const select = (key: string) => set({ selected: key });

  // The areas at the top of the tree, each with how many asked-for skills are in it.
  const treeOptions = useMemo(() => {
    const asked = (id: number) => {
      const ids = new Set(descendants(nodes, id));
      return nodes.filter((n) => ids.has(n.id) && n.job_ids?.length).length;
    };
    return nodes
      .filter((n) => n.placed && n.parent_id === null)
      .sort((x, y) => x.position - y.position)
      .map((n) => ({ value: `s${n.id}`, label: n.name, count: asked(n.id) }));
  }, [nodes]);

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

  const toggle = (key: string) =>
    set({ collapsed: collapsed.includes(key) ? collapsed.filter((c) => c !== key) : [...collapsed, key] });

  const selected = groups.find((g) => g.id === groupId) ?? null;
  const groupOptions = [
    { value: "all", label: `All targets · ${groups.reduce((n, g) => n + g.job_count, 0)}` },
    ...groups.map((g) => ({ value: String(g.id), label: `${g.name} · ${g.job_count}` })),
  ];
  const side = unsortedOpen ? (
    <UnsortedPanel
      waiting={waiting}
      total={total}
      tree={nodes}
      edit={edit}
      onPlace={(id, parent) => move(id, parent, children(nodes, parent).filter((n) => n.id !== id).length)}
      onSelect={(key) => {
        set({ selected: key });
        setUnsortedOpen(false);
      }}
      onClose={() => setUnsortedOpen(false)}
    />
  ) : (
    <MapDetails
      node={selectedNode}
      total={total}
      postings={gap?.postings ?? []}
      roleGroupId={groupId}
      onSelect={select}
      onOpenJob={onOpenJob}
      onChanged={load}
      tree={nodes}
    />
  );
  const unsortedCount = nodes.filter((n) => !n.placed).length;

  const showArea = (key: string) => {
    set({ selected: key, hiddenTree: hiddenAreas.filter((k) => k !== key) });
  };
  const toggleArea = (key: string) =>
    set({ hiddenTree: hiddenAreas.includes(key) ? hiddenAreas.filter((k) => k !== key) : [...hiddenAreas, key] });
  const deleteGroup = async () => {
    if (!selected || !confirm(`Delete the group ${selected.name}? Its jobs stay, they just stop being targets.`)) return;
    try {
      await api.deleteGroup(selected.id);
      set({ groupId: null });
      onGroupsChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      {sideSlot &&
        createPortal(
          <>
            {naming ? (
              <form
                className="side-naming"
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
                <div className="row">
                  <button type="submit" className="primary small">
                    {naming.id === null ? "Add group" : "Rename"}
                  </button>
                  <button type="button" className="small" onClick={() => setNaming(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div className="side-group">
                <select
                  aria-label="Role group"
                  value={groupId === null ? "all" : String(groupId)}
                  onChange={(e) => {
                    if (e.target.value === "new") return setNaming({ id: null, name: "" });
                    set({ groupId: e.target.value === "all" ? null : Number(e.target.value) });
                  }}
                >
                  {groupOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                  <option value="new">New group…</option>
                </select>
                {selected && (
                  <Popover className="icon" title={`Rename or delete ${selected.name}`} label="⋯">
                    {(close) => (
                      <>
                        <button
                          type="button"
                          className="menu-item"
                          onClick={() => {
                            close();
                            setNaming({ id: selected.id, name: selected.name });
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="menu-item danger"
                          onClick={() => {
                            close();
                            deleteGroup();
                          }}
                        >
                          Delete group
                        </button>
                      </>
                    )}
                  </Popover>
                )}
              </div>
            )}
            {treeOptions.map((o) => {
              const hidden = hiddenAreas.includes(o.value);
              const root = findNode(roots, o.value);
              return (
                <div key={o.value} className={`side-area${hidden ? " hidden" : ""}`}>
                  <button
                    type="button"
                    className={`side-item${!query.trim() && areaNode?.key === o.value ? " on" : ""}${root ? edit.drag.state(root).replace(" dragging", "") : ""}`}
                    onClick={() => showArea(o.value)}
                    {...(root ? edit.drag.props(root, { onHold: () => areaNode?.key !== o.value && select(o.value) }) : {})}
                  >
                    <span className="side-label">{o.label}</span>
                    <span className="side-count">{hidden ? "hidden" : o.count}</span>
                  </button>
                  <button
                    type="button"
                    className="icon side-eye"
                    title={hidden ? `Show ${o.label}` : `Hide ${o.label}`}
                    aria-label={hidden ? `Show ${o.label}` : `Hide ${o.label}`}
                    aria-pressed={!hidden}
                    onClick={() => toggleArea(o.value)}
                  >
                    <EyeIcon />
                  </button>
                </div>
              );
            })}
            <button
              type="button"
              className={`side-item unsorted-item${unsortedOpen ? " on" : ""}${unsortedCount ? " waiting" : ""}${edit.drag.state(UNSORTED_TARGET)}`}
              aria-pressed={unsortedOpen}
              onClick={() => setUnsortedOpen(!unsortedOpen)}
              title="Skills added on jobs that aren't in your tree yet. Drop a node here to take it out of the tree."
              {...edit.drag.props(UNSORTED_TARGET)}
            >
              <span className="side-label">Unsorted</span>
              <span className="unsorted-badge">{unsortedCount}</span>
            </button>
            <span className="kind-legend" aria-label="Kinds of node">
              <span>
                <span className="kind-dot skill" aria-hidden />
                Concept
              </span>
              <span>
                <span className="kind-dot tool" aria-hidden />
                Tool
              </span>
              <span>
                <span className="kind-dot group" aria-hidden />
                Group
              </span>
            </span>
          </>,
          sideSlot,
        )}

      <header className="page-head">
        <h2>{query.trim() ? "Search" : areaNode?.name ?? "Skill Gap"}</h2>
        {gap && (
          <span className="muted page-summary">
            {gap.targets === 0
              ? `No target jobs${selected ? ` in ${selected.name}` : ""} yet: choose a role group under Skill Gap on any job`
              : `${gap.targets} target posting${gap.targets === 1 ? "" : "s"}${areaNode && !query.trim() ? ` · ${areaNode.skills} skills` : ""}`}
          </span>
        )}
        <span className="spacer" />
        <label className="search compact">
          <SearchIcon />
          <input type="search" data-page-search placeholder="Search skills" value={query} onChange={(e) => set({ query: e.target.value })} />
        </label>
        <Segmented
          ariaLabel="View"
          value={view}
          onChange={(v) => set({ view: v })}
          options={[
            { value: "diagram", label: "Diagram" },
            { value: "outline", label: "Outline" },
            { value: "columns", label: "Columns" },
          ]}
        />
        <Popover className="icon" title="More: what to show, order, add" alignRight label="⋯">
          {(close) => (
            <>
              <button type="button" className="menu-item" onClick={() => set({ onlyAsked: !filters.onlyAsked })}>
                {filters.onlyAsked ? <CheckIcon /> : <span className="menu-gap" />}
                Only skills postings ask for
              </button>
              {view !== "diagram" && (
                <>
                  <div className="menu-label">Order</div>
                  {(
                    [
                      ["tree", "As in the tree"],
                      ["count", "Most asked for"],
                      ["name", "A–Z"],
                    ] as [MapSort, string][]
                  ).map(([v, label]) => (
                    <button key={v} type="button" className="menu-item" onClick={() => set({ sort: v })}>
                      {sort === v ? <CheckIcon /> : <span className="menu-gap" />}
                      {label}
                    </button>
                  ))}
                </>
              )}
              <div className="menu-sep" />
              <button
                type="button"
                className="menu-item"
                onClick={() => {
                  close();
                  setDialog({ add: null });
                }}
              >
                <PlusIcon />
                Add at the top level
              </button>
            </>
          )}
        </Popover>
      </header>

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
        ) : (
          <>
            <div className="map-area" ref={area}>
            {roots.length === 0 ? (
              <div className="empty">{nodes.length === 0 ? "Your tree is empty. Add a skill or group at the top level." : "Nothing matches these filters."}</div>
            ) : view === "columns" ? (
              <ColumnsView roots={shownRoots} total={total} selected={selectedInTree} onSelect={select} edit={edit} details={side} />
            ) : (
              <div className="map-layout">
                <div className="map-main">
                  {view === "outline" ? (
                    <OutlineView
                      roots={shownRoots}
                      total={total}
                      selected={selectedInTree}
                      onSelect={select}
                      edit={edit}
                      collapsed={new Set(collapsed)}
                      onToggle={toggle}
                    />
                  ) : (
                    <DiagramView
                      roots={shownRoots}
                      total={total}
                      selected={selectedInTree}
                      onSelect={select}
                      edit={edit}
                      zoom={filters.zoom}
                      onZoom={(zoom) => set({ zoom })}
                    />
                  )}
                </div>
                {side}
              </div>
            )}
            </div>
          </>
        )}
      </main>

      {removed && (
        <div className="toast" role="status">
          Removed {removed}
          <button type="button" className="link" onClick={undoRemove}>
            Undo
          </button>
          <kbd>{shortcut("Z")}</kbd>
        </div>
      )}

      {dialog && (
        <NodeDialog
          title={"add" in dialog ? (dialog.add ? `Add under ${dialog.add.name}` : "Add at the top level") : `Edit ${dialog.edit.kind === "group" ? "group" : dialog.edit.tool ? "tool" : "concept"}`}
          initial={
            "add" in dialog
              ? { name: "", description: "", isGroup: false, isTool: false }
              : { name: dialog.edit.name, description: dialog.edit.description, isGroup: dialog.edit.kind === "group", isTool: dialog.edit.tool }
          }
          pickKind={"add" in dialog}
          onSave={saveDialog}
          onRemove={"edit" in dialog ? () => remove(dialog.edit) : undefined}
          onClose={() => setDialog(null)}
          parentId={"add" in dialog ? dialog.add?.skill?.id ?? null : dialog.edit.skill?.placed ? dialog.edit.skill.parent_id : null}
          skillId={"edit" in dialog ? dialog.edit.skill?.id ?? null : null}
          onOpenAI={onOpenAI}
        />
      )}

    </>
  );
}
