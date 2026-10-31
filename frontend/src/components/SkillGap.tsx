import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { buildMap, findNode, UNSORTED, UNSORTED_TARGET, waitingMap, type MapNode, type MapSort } from "../skillmap";
import { children, descendants, flat, moved } from "../tree";
import type { RoleGroup, SkillGap as Gap } from "../types";
import { PlusIcon, SearchIcon } from "./Icons";
import MultiFilter from "./MultiFilter";
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
}

export default function SkillGap({ groups, onGroupsChanged, filters, onFiltersChange, onOpenJob, onOpenAI, refreshKey }: Props) {
  const { groupId, query, view, sort, collapsed, selected: selectedKey } = filters;
  const set = (patch: Partial<GapFilters>) => onFiltersChange({ ...filters, ...patch });
  const [gap, setGap] = useState<Gap | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null: not editing; "" or a name: the new-group / rename field is open.
  const [naming, setNaming] = useState<{ id: number | null; name: string } | null>(null);
  // The skills waiting in Unsorted, in place of the details.
  const [unsortedOpen, setUnsortedOpen] = useState(false);
  const layout = useRef<HTMLDivElement>(null);
  // The pop-up that adds under a node (parent; null: the top level) or edits one.
  const [dialog, setDialog] = useState<{ add: MapNode | null } | { edit: MapNode } | null>(null);
  const nodes = useMemo(() => gap?.skills ?? [], [gap]);

  // A hidden node hides everything under it.
  const hiddenTree = useMemo(() => {
    const chosen =
      filters.hiddenTree ??
      nodes.filter((n) => n.placed && n.parent_id === null && HIDDEN_BY_DEFAULT.includes(n.name)).map((n) => `s${n.id}`);
    return new Set(
      chosen.flatMap((key) => (key === UNSORTED ? [UNSORTED] : descendants(nodes, Number(key.slice(1))).map((id) => `s${id}`))),
    );
  }, [filters.hiddenTree, nodes]);

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

  // The pane beside the tree is never taller than the tree (--map-h): a long one scrolls on its own
  // instead of making the page longer. Below the tree (a narrow window) only the screen limits it.
  const mapShown = !!gap && roots.length > 0 && view !== "columns";
  useEffect(() => {
    const box = layout.current;
    const main = box?.firstElementChild as HTMLElement | null;
    if (!box || !main) return;
    const fit = () => {
      if (main.offsetWidth > box.clientWidth - 300) box.style.removeProperty("--map-h");
      else box.style.setProperty("--map-h", `${main.offsetHeight}px`);
    };
    // Only the tree: the pane's own size changes the layout's, which would loop.
    const observer = new ResizeObserver(fit);
    observer.observe(main);
    window.addEventListener("resize", fit);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [mapShown]);

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
  const remove = (node: MapNode) => {
    const s = node.skill;
    if (!s) return false;
    const n = node.direct;
    const off = n ? ` It is taken off the ${n === 1 ? "posting that asks" : `${n} postings that ask`} for it, and reading them again won't add it back.` : "";
    const under = s.placed && children(nodes, s.id).length ? " What is under it moves up one level." : "";
    if ((off || under) && !confirm(`Remove ${s.name}?${off}${under}`)) return false;
    if (selectedKey === node.key) set({ selected: null });
    change(() => api.deleteSkill(s.id));
    return true;
  };
  const edit: TreeEdit = {
    onAdd: (parent) => setDialog({ add: parent }),
    onEdit: (node) => setDialog({ edit: node }),
    onRemove: remove,
    drag: useTreeDrag(nodes, move, unsort),
  };
  const saveDialog = ({ name, description, isGroup }: NodeFields) => {
    if (!dialog) return;
    if ("add" in dialog) {
      const parent = dialog.add?.skill?.id ?? null;
      if (dialog.add) set({ collapsed: collapsed.filter((c) => c !== dialog.add!.key) });
      change(() => api.createSkill({ name, description, is_group: isGroup, parent_id: parent }));
    } else {
      const s = dialog.edit.skill!;
      const body: { name?: string; description?: string } = {};
      if (name.trim() !== s.name) body.name = name;
      if (description !== s.description) body.description = description;
      if (Object.keys(body).length) change(() => api.updateSkill(s.id, body, null));
    }
    setDialog(null);
  };
  const total = gap?.targets ?? 0;
  const select = (key: string) => set({ selected: key });

  // The top two levels of the tree, each with how many asked-for skills are in it.
  const treeOptions = useMemo(() => {
    const asked = (id: number) => {
      const ids = new Set(descendants(nodes, id));
      return nodes.filter((n) => ids.has(n.id) && n.job_ids?.length).length;
    };
    const options = flat(nodes)
      .filter(({ depth }) => depth <= 1)
      .map(({ node, depth }) => ({ value: `s${node.id}`, label: `${"   ".repeat(depth)}${node.name}`, count: asked(node.id) }));
    return options;
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
        <MultiFilter
          label="Show"
          options={treeOptions}
          hidden={treeOptions.map((o) => o.value).filter((v) => hiddenTree.has(v))}
          onChange={(h) => set({ hiddenTree: h })}
        />
        <button
          className={`unsorted-button${unsortedOpen ? " active" : ""}${unsortedCount ? " waiting" : ""}${edit.drag.state(UNSORTED_TARGET)}`}
          aria-pressed={unsortedOpen}
          onClick={() => setUnsortedOpen(!unsortedOpen)}
          title="Skills added on jobs that aren't in your tree yet. Drop a node here to take it out of the tree."
          {...edit.drag.props(UNSORTED_TARGET)}
        >
          Unsorted
          <span className="unsorted-badge">{unsortedCount}</span>
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
        ) : (
          <>
            <div className="map-toolbar">
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
              {view !== "diagram" && (
                <Segmented
                  ariaLabel="Order"
                  value={sort}
                  onChange={(v) => set({ sort: v })}
                  options={[
                    { value: "tree", label: "Tree order" },
                    { value: "count", label: "Most asked" },
                    { value: "name", label: "A–Z" },
                  ]}
                />
              )}
              <label className="check-chip" title="Leave out the skills no posting asks for">
                <input type="checkbox" checked={filters.onlyAsked} onChange={(e) => set({ onlyAsked: e.target.checked })} />
                Only asked for
              </label>
              <button className="small" onClick={() => setDialog({ add: null })} title="Add a skill or group at the top level">
                <PlusIcon />
                Add at the top level
              </button>
              <span className="spacer" />
              <span className="muted map-status">
                {gap.targets === 0
                  ? `No target jobs${selected ? ` in ${selected.name}` : ""} yet: choose a role group under Skill Gap on any job`
                  : `${gap.targets} target posting${gap.targets === 1 ? "" : "s"}`}
              </span>
            </div>

            {roots.length === 0 ? (
              <div className="empty">{nodes.length === 0 ? "Your tree is empty. Add a skill or group at the top level." : "Nothing matches these filters."}</div>
            ) : view === "columns" ? (
              <ColumnsView roots={roots} total={total} selected={selectedInTree} onSelect={select} edit={edit} details={side} />
            ) : (
              <div className="map-layout" ref={layout}>
                <div className="map-main">
                  {view === "outline" ? (
                    <OutlineView
                      roots={roots}
                      total={total}
                      selected={selectedInTree}
                      onSelect={select}
                      edit={edit}
                      collapsed={new Set(collapsed)}
                      onToggle={toggle}
                    />
                  ) : (
                    <DiagramView
                      roots={roots}
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
          </>
        )}
      </main>

      {dialog && (
        <NodeDialog
          title={"add" in dialog ? (dialog.add ? `Add under ${dialog.add.name}` : "Add at the top level") : `Edit ${dialog.edit.kind}`}
          initial={
            "add" in dialog
              ? { name: "", description: "", isGroup: false }
              : { name: dialog.edit.name, description: dialog.edit.description, isGroup: dialog.edit.kind === "group" }
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
