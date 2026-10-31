import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type DragEvent, type MouseEvent } from "react";
import { api } from "../api";
import { lineage, UNSORTED, type MapNode } from "../skillmap";
import { children, descendants } from "../tree";
import type { SkillDetail, SkillGap, SkillRow } from "../types";
import SkillSearch from "./SkillSearch";
import { ChevronIcon, CloseIcon, EditIcon, MinusIcon, PlusIcon, TrashIcon } from "./Icons";

type Zone = "before" | "after" | "inside";

/** Editing the tree on the page: the hover buttons and dragging. */
export interface TreeEdit {
  onAdd: (parent: MapNode) => void;
  onEdit: (node: MapNode) => void;
  onRemove: (node: MapNode) => void;
  drag: TreeDrag;
}

interface TreeDrag {
  /** Handlers for a node that can be dragged and dropped on. As a tab (an area of the diagram), a
   *  drop puts it at the end of that area, and holding it there calls onHold (shows the area). */
  props: (node: MapNode, tab?: { onHold: () => void }) => Record<string, unknown>;
  /** " dragging", " drop-inside"... for a node's class. */
  state: (node: MapNode) => string;
  /** A node is being dragged. */
  active: boolean;
}

/** Drag a node onto another to put it under it, onto its top or bottom edge to put it before or
 *  after, or onto Unsorted (its button or panel) to take it out of the tree. Indexes are counted in the whole tree
 *  (all), not in what the view shows. */
export function useTreeDrag(all: SkillRow[], move: (id: number, parent: number | null, index: number) => void, unsort: (id: number) => void): TreeDrag {
  const [dragging, setDragging] = useState<MapNode | null>(null);
  const [drop, setDrop] = useState<{ key: string; zone: Zone } | null>(null);
  const hold = useRef<{ key: string; timer: number } | null>(null);
  const stopHold = () => {
    if (hold.current) clearTimeout(hold.current.timer);
    hold.current = null;
  };
  const end = () => {
    stopHold();
    setDragging(null);
    setDrop(null);
  };
  // Showing another area takes the dragged node off the page, and with it its dragend: the first
  // mouse move after the drag (none come during one) ends it instead.
  useEffect(() => {
    if (!dragging) return;
    const done = () => end();
    document.addEventListener("mousemove", done);
    return () => document.removeEventListener("mousemove", done);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragging]);
  const allowed = (target: MapNode) => {
    const id = dragging?.skill?.id;
    if (id === undefined || target.key === dragging?.key) return false;
    if (target.key === UNSORTED) return !!dragging?.skill?.placed;
    return !!target.skill?.placed && !descendants(all, id).includes(target.skill.id);
  };
  const apply = (id: number, target: MapNode, zone: Zone) => {
    const t = target.skill;
    if (!t) return unsort(id);
    if (zone === "inside") return move(id, t.id, children(all, t.id).filter((n) => n.id !== id).length);
    const siblings = children(all, t.parent_id).filter((n) => n.id !== id);
    move(id, t.parent_id, siblings.findIndex((n) => n.id === t.id) + (zone === "after" ? 1 : 0));
  };
  return {
    props: (node, tab) => ({
      draggable: !tab && node.key !== UNSORTED,
      onDragStart: (e: DragEvent<HTMLElement>) => {
        e.stopPropagation();
        e.dataTransfer.setData("text/plain", node.name);
        e.dataTransfer.effectAllowed = "move";
        setDragging(node);
      },
      onDragEnd: end,
      onDragOver: (e: DragEvent<HTMLElement>) => {
        if (!allowed(node)) return;
        e.preventDefault();
        e.stopPropagation();
        const r = e.currentTarget.getBoundingClientRect();
        const y = (e.clientY - r.top) / r.height;
        const zone: Zone = tab || node.key === UNSORTED ? "inside" : y < 0.28 ? "before" : y > 0.72 ? "after" : "inside";
        if (drop?.key !== node.key || drop.zone !== zone) setDrop({ key: node.key, zone });
        if (tab && hold.current?.key !== node.key) {
          stopHold();
          hold.current = { key: node.key, timer: window.setTimeout(tab.onHold, 500) };
        }
      },
      onDragLeave: (e: DragEvent<HTMLElement>) => {
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
        if (drop?.key === node.key) setDrop(null);
        if (tab && hold.current?.key === node.key) stopHold();
      },
      onDrop: (e: DragEvent<HTMLElement>) => {
        e.preventDefault();
        e.stopPropagation();
        if (dragging?.skill && drop?.key === node.key) apply(dragging.skill.id, node, drop.zone);
        end();
      },
    }),
    state: (node) =>
      `${dragging?.key === node.key ? " dragging" : ""}${drop?.key === node.key ? ` drop-${drop.zone}` : ""}`,
    active: dragging !== null,
  };
}

/** Add under it, edit, remove; shown on hover. */
function NodeActions({ node, edit }: { node: MapNode; edit: TreeEdit }) {
  const skill = node.skill;
  if (!skill) return null;
  const run = (f: () => void) => (e: MouseEvent) => {
    e.stopPropagation();
    f();
  };
  return (
    <span className="node-actions" onDoubleClick={(e) => e.stopPropagation()}>
      {skill.placed && (
        <button type="button" className="icon" title={`Add a skill or group under ${node.name}`} onClick={run(() => edit.onAdd(node))}>
          <PlusIcon />
        </button>
      )}
      <button type="button" className="icon" title={`Edit ${node.name}`} onClick={run(() => edit.onEdit(node))}>
        <EditIcon />
      </button>
      <button type="button" className="icon" title={`Remove ${node.name}`} onClick={run(() => edit.onRemove(node))}>
        <TrashIcon />
      </button>
    </span>
  );
}

/** Nothing under it is asked for: drawn faint. */
const faint = (n: MapNode) => (n.jobs.size === 0 ? " unasked" : "");

interface ViewProps {
  roots: MapNode[];
  /** The postings the counts are out of. */
  total: number;
  selected: MapNode | null;
  onSelect: (key: string) => void;
  edit: TreeEdit;
}

/** "group", "skill" (a concept) or "tool": its color on the tree. */
const kindClass = (n: MapNode) => (n.kind === "group" ? "group" : n.tool ? "tool" : "skill");
/** The mark before a skill's name: a dot for a concept, a square for a tool. */
const KindDot = ({ node }: { node: MapNode }) => (node.kind === "skill" ? <span className={`kind-dot ${kindClass(node)}`} aria-hidden /> : null);
const share = (n: MapNode, total: number) => (total ? n.jobs.size / total : 0);
const meta = (n: MapNode) => (n.skills ? `${n.skills} under it` : "");

function Bar({ node, total, thin }: { node: MapNode; total: number; thin?: boolean }) {
  return (
    <span className={`map-bar ${kindClass(node)} ${thin ? "thin" : ""}`} aria-hidden>
      <span style={{ width: `${share(node, total) * 100}%` }} />
    </span>
  );
}

// Outline geometry, matching .outline-row and .o-chev in styles.css.
const ROW_PAD = 10;
const INDENT = 20;
const CHEVRON = 22;

/** An expandable outline: each row with a bar for the postings that ask for it. */
export function OutlineView({ roots, total, selected, onSelect, edit, collapsed, onToggle }: ViewProps & { collapsed: Set<string>; onToggle: (key: string) => void }) {
  // Each row draws its own piece of the branch lines: a line through every level above it whose
  // branch goes on below it, and an elbow into itself that goes on down if more siblings follow.
  const rows: { node: MapNode; depth: number; last: boolean; through: number[] }[] = [];
  const walk = (list: MapNode[], depth: number, through: number[]) =>
    list.forEach((node, i) => {
      const last = i === list.length - 1;
      rows.push({ node, depth, last, through });
      if (!collapsed.has(node.key)) walk(node.children, depth + 1, depth > 0 && !last ? [...through, depth] : through);
    });
  walk(roots, 0, []);
  /** Under the collapse arrow of the parent one level up. */
  const lineX = (level: number) => ROW_PAD + (level - 1) * INDENT + CHEVRON / 2;

  return (
    <div className="outline" role="tree" aria-label="Skills">
      <div className="outline-row outline-head" aria-hidden>
        <span>Skill</span>
        <span>Postings asking for it</span>
        <span className="num">of {total}</span>
      </div>
      {rows.map(({ node, depth, last, through }) => (
        <div
          key={node.key}
          role="treeitem"
          aria-expanded={node.children.length ? !collapsed.has(node.key) : undefined}
          aria-selected={selected?.key === node.key}
          className={`outline-row ${kindClass(node)}${node.kind === "skill" ? " skill" : ""} depth-${Math.min(depth, 1)} ${selected?.key === node.key ? "selected" : ""}${faint(node)}${edit.drag.state(node)}`}
          onClick={() => onSelect(node.key)}
          onDoubleClick={() => node.skill && edit.onEdit(node)}
          {...edit.drag.props(node)}
        >
          {through.map((level) => (
            <span key={level} className="o-line" style={{ left: lineX(level) }} aria-hidden />
          ))}
          {depth > 0 && (
            <>
              <span className={`o-line ${last ? "end" : ""}`} style={{ left: lineX(depth) }} aria-hidden />
              <span
                className="o-elbow"
                style={{ left: lineX(depth), width: INDENT - CHEVRON / 2 + (node.children.length ? 0 : CHEVRON - 4) }}
                aria-hidden
              />
            </>
          )}
          <span className="o-name" style={{ paddingLeft: depth * INDENT }}>
            {node.children.length ? (
              <button
                type="button"
                className={`icon o-chev ${collapsed.has(node.key) ? "closed" : ""}`}
                aria-label={`${collapsed.has(node.key) ? "Expand" : "Collapse"} ${node.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggle(node.key);
                }}
              >
                <ChevronIcon />
              </button>
            ) : (
              <span className="o-chev-space" />
            )}
            <span className="o-label">
              <KindDot node={node} />
              {node.name}
            </span>
            <span className="o-meta">{meta(node)}</span>
            <NodeActions node={node} edit={edit} />
          </span>
          <Bar node={node} total={total} />
          <span className="num">{node.jobs.size}</span>
        </div>
      ))}
    </div>
  );
}

/** Finder-style columns: each pick opens what is under it in the next column. */
export function ColumnsView({ roots, total, selected, onSelect, edit, details }: ViewProps & { details: React.ReactNode }) {
  const path = lineage(selected);
  const columns: { label: string; items: MapNode[] }[] = [{ label: "Areas", items: roots }];
  path.forEach((n) => n.children.length && columns.push({ label: `In ${n.name}`, items: n.children }));

  return (
    <div className="map-columns">
      {columns.map((col, i) => (
        <div key={i} className="map-col" role="listbox" aria-label={col.label}>
          <span className="map-col-label">{col.label}</span>
          {col.items.map((n) => {
            const onPath = path[i]?.key === n.key;
            return (
              <div key={n.key} className="map-col-row">
              <button
                type="button"
                role="option"
                aria-selected={onPath}
                className={`map-col-item ${kindClass(n)}${n.kind === "skill" ? " skill" : ""} ${onPath ? (n.key === selected?.key ? "current" : "on-path") : ""}${faint(n)}`}
                onClick={() => onSelect(n.key)}
                onDoubleClick={() => n.skill && edit.onEdit(n)}
              >
                <span className="map-col-text">
                  <span className="map-col-top">
                    <span className="map-col-name">
                      <KindDot node={n} />
                      {n.name}
                    </span>
                    <span className="map-col-count">{n.jobs.size}</span>
                  </span>
                  <Bar node={n} total={total} thin />
                </span>
                <span className="map-col-arrow" style={{ visibility: n.children.length ? "visible" : "hidden" }} aria-hidden>
                  ›
                </span>
              </button>
              <NodeActions node={n} edit={edit} />
              </div>
            );
          })}
        </div>
      ))}
      <div className="map-col map-col-details">{details}</div>
    </div>
  );
}

/** One area as a left-to-right tree; nodes get bolder the more postings ask for them. */
export const ZOOM_MIN = 0.3;
export const ZOOM_MAX = 2;
const clampZoom = (z: number) => Math.round(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z)) * 100) / 100;

export function DiagramView({ roots, total, selected, onSelect, edit, zoom, onZoom }: ViewProps & { zoom: number; onZoom: (zoom: number) => void }) {
  const area = lineage(selected)[0] ?? roots[0];
  const box = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;

  // Pinch on a trackpad (or ⌘/Ctrl + scroll) zooms the diagram, not the page.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      onZoom(clampZoom(zoomRef.current * Math.exp(-e.deltaY * 0.01)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onZoom]);

  // Dragging the empty background moves around a zoomed-in diagram.
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const startPan = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    const el = e.currentTarget;
    drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop };
    el.setPointerCapture(e.pointerId);
  };
  const pan = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    e.currentTarget.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
    e.currentTarget.scrollTop = drag.current.top - (e.clientY - drag.current.y);
  };
  const endPan = () => {
    drag.current = null;
  };

  const fit = () => {
    const el = box.current;
    const inner = content.current;
    if (!el || !inner) return;
    const style = getComputedStyle(el);
    const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    // Its size at 100%: all that scrolls, not only the tree, which can be narrower.
    const width = Math.max(inner.getBoundingClientRect().width, el.scrollWidth - padding) / zoom;
    // Rounded down, so it fits rather than overflowing by a few pixels; then shown from the left.
    onZoom(clampZoom(Math.min(1, Math.floor(((el.clientWidth - padding) / width) * 100) / 100)));
    requestAnimationFrame(() => el.scrollTo({ left: 0 }));
  };

  // Every level is a column: each node sits in a cell as wide as the widest node of its depth.
  // Widths are measured after drawing (offsetWidth is in the diagram's own, unzoomed units).
  const [columns, setColumns] = useState<number[]>([]);
  useLayoutEffect(() => {
    const widths: number[] = [];
    content.current?.querySelectorAll<HTMLElement>("[data-depth]").forEach((el) => {
      const d = Number(el.dataset.depth);
      widths[d] = Math.max(widths[d] ?? 0, el.offsetWidth);
    });
    setColumns((old) => (old.length === widths.length && old.every((w, i) => w === widths[i]) ? old : widths));
  }, [area, roots, total, selected]);


  const node = (n: MapNode, depth: number) => {
    const r = share(n, total);
    const style: CSSProperties | undefined =
      n.kind === "skill"
        ? {
            background: `color-mix(in srgb, var(${n.tool ? "--tool" : "--accent"}) ${Math.round(12 + r * 70)}%, transparent)`,
            color: r > 0.6 ? `var(${n.tool ? "--tool-text" : "--accent-text"})` : "var(--text)",
            fontWeight: r > 0.5 ? 700 : r > 0.25 ? 600 : 450,
            fontSize: 12.5 + r * 3,
          }
        : undefined;
    return (
      <div className="d-row">
        <span className="d-cell" style={{ width: columns[depth] }}>
          <span className="d-wrap" data-depth={depth}>
            <button
              type="button"
              className={`d-node ${depth === 0 ? "root" : kindClass(n)} ${selected?.key === n.key ? "selected" : ""}${faint(n)}${edit.drag.state(n)}`}
              style={style}
              onClick={() => onSelect(n.key)}
              onDoubleClick={() => n.skill && edit.onEdit(n)}
              {...edit.drag.props(n)}
            >
              {depth > 0 && <KindDot node={n} />}
              {n.name}
              <span className="d-count">{n.jobs.size}</span>
            </button>
            <NodeActions node={n} edit={edit} />
          </span>
          {n.children.length > 0 && <span className="d-fill" aria-hidden />}
        </span>
        {n.children.length > 0 && (
          <>
            <span className="d-stub" aria-hidden />
            <div className="d-kids">
              {n.children.map((c) => (
                <div key={c.key} className="d-item">
                  {node(c, depth + 1)}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="diagram-wrap">
      {/* The areas of the tree, one shown at a time: one row, scrolling sideways when there are many. */}
      <div className="area-tabs" role="tablist" aria-label="Area">
        {roots.map((n) => (
          <button
            key={n.key}
            type="button"
            role="tab"
            aria-selected={area?.key === n.key}
            className={`${area?.key === n.key ? "active" : ""}${edit.drag.state(n).replace(" dragging", "")}`}
            onClick={() => onSelect(n.key)}
            {...edit.drag.props(n, { onHold: () => area?.key !== n.key && onSelect(n.key) })}
          >
            {n.name}
            {n.jobs.size > 0 && <span className="area-count">{n.jobs.size}</span>}
          </button>
        ))}
      </div>
      <div
        ref={box}
        className="diagram"
        onPointerDown={startPan}
        onPointerMove={pan}
        onPointerUp={endPan}
        onPointerCancel={endPan}
      >
        {/* Stays in the corner while the diagram scrolls. */}
        <div className="diagram-bar">
          <div className="zoom-controls" role="group" aria-label="Zoom">
            <button type="button" className="icon" aria-label="Zoom out" disabled={zoom <= ZOOM_MIN} onClick={() => onZoom(clampZoom(zoom - 0.1))}>
              <MinusIcon />
            </button>
            <button type="button" className="zoom-level" title="Back to 100%" onClick={() => onZoom(1)}>
              {Math.round(zoom * 100)}%
            </button>
            <button type="button" className="icon" aria-label="Zoom in" disabled={zoom >= ZOOM_MAX} onClick={() => onZoom(clampZoom(zoom + 0.1))}>
              <PlusIcon />
            </button>
            <button type="button" className="zoom-fit" onClick={fit}>
              Fit
            </button>
          </div>
        </div>
        <div ref={content} className="diagram-content" style={{ zoom }}>
          {area && node(area, 0)}
        </div>
      </div>
    </div>
  );
}

/** What is selected: where it sits, what it means, what is under it and which postings ask for it. */
export function MapDetails({
  node,
  total,
  postings,
  roleGroupId,
  onSelect,
  onOpenJob,
  onChanged,
  tree,
}: {
  node: MapNode | null;
  total: number;
  /** The target postings: the ones a skill can be connected to. */
  postings: SkillGap["postings"];
  roleGroupId: number | null;
  onSelect: (key: string) => void;
  onOpenJob: (id: number) => void;
  /** A posting was connected or disconnected, or a skill placed: the counts change. */
  onChanged: () => void;
  /** The whole tree, to place a skill from Unsorted in. */
  tree: SkillRow[];
}) {
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [note, setNote] = useState<{ jobId: number; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [placing, setPlacing] = useState<string | null>(null); // the search for where it belongs
  const skillId = node?.skill?.id ?? null;

  // A skill's postings come with the line each one asks for it in.
  useEffect(() => {
    setDetail(null);
    setNote(null);
    setPlacing(null);
    setError(null);
    if (skillId !== null) api.getSkill(skillId, roleGroupId).then(setDetail, () => {});
  }, [skillId, roleGroupId]);

  const change = async (action: () => Promise<SkillDetail>) => {
    try {
      setDetail(await action());
      setError(null);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!node)
    return (
      <div className="map-details empty-details muted">
        Click a skill to see where it sits and which postings ask for it. Hover one to add under it, edit or remove it;
        drag it to move it.
      </div>
    );

  const path = lineage(node).slice(0, -1);
  const quotes = new Map((detail?.jobs ?? []).map((j) => [j.job_id, j]));
  const asking = postings.filter((p) => node.jobs.has(p.id));
  const skill = node.skill;
  // Postings are connected to skills, never to a group, which only organizes.
  const connectable = node.kind === "skill" && skill !== undefined;
  const named = (jobId: number) => quotes.has(jobId) || (skill?.job_ids?.includes(jobId) ?? false);
  const saveNote = () => {
    if (!note || !skill) return;
    const old = quotes.get(note.jobId)?.evidence ?? "";
    setNote(null);
    if (note.text.trim() !== old) change(() => api.updateConnection(skill.id, note.jobId, { evidence: note.text }, roleGroupId));
  };
  /** For a posting that doesn't name it: the skills under it that the posting names. */
  const via = (jobId: number): string[] => {
    const names: string[] = [];
    const walk = (n: MapNode) =>
      n.children.forEach((c) => {
        if (c.skill?.job_ids?.includes(jobId)) names.push(c.name);
        walk(c);
      });
    walk(node);
    return names;
  };

  return (
    <aside className="map-details" aria-label="Selected">
      <div className="details-head">
        {path.length > 0 && (
          <nav className="crumbs" aria-label="Where it sits">
            {path.map((p) => (
              <button key={p.key} type="button" className="link quiet" onClick={() => onSelect(p.key)}>
                {p.name}
              </button>
            ))}
          </nav>
        )}
        <h2>{node.name}</h2>
        <span className="muted">
          {node.kind === "group"
            ? `${node.skill ? "Group · " : ""}${node.jobs.size} of ${total} posting${total === 1 ? "" : "s"} ask for something in it`
            : `${node.tool ? "Tool" : "Concept"} · Asked for in ${node.jobs.size} of ${total} posting${total === 1 ? "" : "s"}`}
          {node.skills > 0 && ` · ${meta(node)}`}
        </span>
        {skill && !skill.placed && (
          <div className="place-in-tree">
            {placing === null ? (
              <button type="button" className="small primary" onClick={() => setPlacing("")}>
                Place in tree…
              </button>
            ) : (
              <SkillSearch
                autoFocus
                skills={tree}
                query={placing}
                onQuery={setPlacing}
                mode="parent"
                placeholder={`Where does ${skill.name} belong? Search the tree`}
                onCancel={() => setPlacing(null)}
                onPick={async (pick) => {
                  if ("name" in pick) return;
                  try {
                    await api.updateSkill(skill.id, { parent_id: "top" in pick ? null : pick.skill.id }, roleGroupId);
                    setPlacing(null);
                    onChanged();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              />
            )}
          </div>
        )}
        {node.kind === "skill" && node.children.length > 0 && node.jobs.size > 0 && (
          <span className="muted">
            {node.direct} name it, {node.jobs.size - node.direct} name something under it
          </span>
        )}
      </div>

      {node.description ? (
        <p className="details-description">{node.description}</p>
      ) : (
        <p className="muted small-note">No description yet. Double-click it, or use the pencil, to add one.</p>
      )}

      {skill && (skill.years.length > 0 || skill.details.length > 0) && (
        <div className="details-tags">
          {skill.years.map((y) => (
            <span key={y} className="years-tag">
              {y} yrs
            </span>
          ))}
          {skill.details.map((d) => (
            <span key={d} className="muted">
              Fields: {d}
            </span>
          ))}
        </div>
      )}

      {node.children.length > 0 && (
        <section>
          <h3>Under it</h3>
          <ul className="details-kids">
            {node.children.map((c) => (
              <li key={c.key}>
                <button type="button" onClick={() => onSelect(c.key)}>
                  <span className="kid-name">{c.name}</span>
                  <Bar node={c} total={total} thin />
                  <span className="num muted">{c.jobs.size}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>Postings that ask for it</h3>
        {error && <div className="error">{error}</div>}
        {asking.length === 0 && (
          <p className="muted small-note">
            {connectable ? "None yet. Open a job and select the words that name it." : "None yet. Add the skills in it on a job."}
          </p>
        )}
        <ul className="details-postings">
          {asking.map((p) => {
            const quote = quotes.get(p.id)?.evidence;
            const direct = named(p.id);
            return (
              <li key={p.id} className={direct && skill ? "connected" : ""}>
                <button type="button" onClick={() => onOpenJob(p.id)}>
                  <span>
                    <strong>{p.title}</strong>
                    <span className="muted"> · {p.company}</span>
                  </span>
                  {direct && quote && note?.jobId !== p.id && <q>{quote}</q>}
                  {!direct && <span className="muted via">via {via(p.id).join(", ")}</span>}
                </button>
                {direct && skill && note?.jobId === p.id && (
                  <input
                    autoFocus
                    className="connection-note"
                    value={note.text}
                    maxLength={500}
                    placeholder="The line in the posting, e.g. 3+ years with Docker"
                    onChange={(e) => setNote({ jobId: p.id, text: e.target.value })}
                    onBlur={saveNote}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") e.currentTarget.blur();
                      if (e.key === "Escape") {
                        e.stopPropagation();
                        setNote(null);
                      }
                    }}
                  />
                )}
                {direct && skill && (
                  <span className="posting-actions">
                    <button
                      type="button"
                      className="icon"
                      title={quote ? "Edit the note" : "Add the line it asks for it in"}
                      onClick={() => setNote({ jobId: p.id, text: quote ?? "" })}
                    >
                      <EditIcon />
                    </button>
                    <button
                      type="button"
                      className="icon"
                      title={`Disconnect ${p.title}`}
                      onClick={() => change(() => api.disconnectJob(skill.id, p.id, roleGroupId))}
                    >
                      <CloseIcon />
                    </button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
