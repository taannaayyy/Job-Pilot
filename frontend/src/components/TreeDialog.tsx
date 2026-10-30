import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { api } from "../api";
import { children, descendants } from "../tree";
import type { AIProvider, SkillGroupNode, SkillRow } from "../types";
import { useClosing } from "../useClosing";
import { ChevronIcon, CloseIcon, FolderIcon, FolderPlusIcon, GripIcon, PlusIcon, SendIcon, SparkIcon, TrashIcon } from "./Icons";

interface Props {
  tree: SkillGroupNode[];
  onChanged: () => void;
  onClose: () => void;
}

type Message = { role: "user" | "assistant"; content: string };

const PROVIDERS: { value: AIProvider; label: string }[] = [
  { value: "claude_code", label: "Claude Code" },
  { value: "anthropic", label: "Claude API" },
  { value: "openai", label: "OpenAI-compatible" },
  { value: "ollama", label: "Ollama" },
];
type Zone = "before" | "after" | "inside";
/** A group or a skill of the tree. */
type Item = { kind: "group" | "skill"; id: number };
type Dragged = Item;
/** Where a dragged item would land: on a group, a skill, Unsorted, or (root) the end of the top level. */
type Drop = { kind: "group" | "skill" | "unsorted" | "root"; id: number | null; zone: Zone };
const FIRST_QUESTION = "Look at my tree and the requirements filed in it, and recommend how to improve it.";

const byName = (a: SkillRow, b: SkillRow) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" });

/** The tree with one group moved, before the server answers, so the drop shows at once. */
function moved(tree: SkillGroupNode[], id: number, parent: number | null, index: number): SkillGroupNode[] {
  const node = tree.find((g) => g.id === id)!;
  const siblings = children(tree, parent).filter((g) => g.id !== id);
  siblings.splice(index, 0, node);
  const position = new Map(siblings.map((g, i) => [g.id, i]));
  return tree.map((g) =>
    position.has(g.id) ? { ...g, parent_id: g.id === id ? parent : g.parent_id, position: position.get(g.id)! } : g,
  );
}

/** Bold, inline code, headings and lists; enough for the model's answers. */
function Markdown({ text }: { text: string }) {
  const inline = (line: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : part.startsWith("`") && part.endsWith("`") ? (
        <code key={i}>{part.slice(1, -1)}</code>
      ) : (
        part
      ),
    );
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; start: number; items: ReactNode[] } | null = null;
  const flush = () => {
    if (list)
      blocks.push(
        list.ordered ? (
          <ol key={blocks.length} start={list.start}>
            {list.items}
          </ol>
        ) : (
          <ul key={blocks.length}>{list.items}</ul>
        ),
      );
    list = null;
  };
  let table: string[][] | null = null;
  const flushTable = () => {
    if (table) {
      const [head, ...body] = table;
      blocks.push(
        <table key={blocks.length}>
          <thead>
            <tr>{head.map((c, i) => <th key={i}>{inline(c)}</th>)}</tr>
          </thead>
          <tbody>
            {body.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>,
      );
    }
    table = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flush();
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue; // the |---|---| line
      (table ??= []).push(line.trim().slice(1, -1).split("|").map((c) => c.trim()));
      continue;
    }
    flushTable();
    const bullet = line.match(/^\s*[-*•]\s+(.*)/);
    const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)/);
    const heading = line.match(/^#{1,4}\s+(.*)/);
    if (bullet || numbered) {
      const ordered = !!numbered;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, start: numbered ? Number(numbered[1]) : 1, items: [] };
      }
      list.items.push(<li key={list.items.length}>{inline(bullet ? bullet[1] : numbered![2])}</li>);
      continue;
    }
    if (!line.trim()) continue; // a blank line between points keeps the list going
    flush();
    if (heading) blocks.push(<h4 key={blocks.length}>{inline(heading[1])}</h4>);
    else if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  flushTable();
  return <div className="md">{blocks}</div>;
}

export default function TreeDialog({ tree: initial, onChanged, onClose }: Props) {
  const [tree, setTree] = useState(initial);
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [renaming, setRenaming] = useState<(Item & { name: string }) | null>(null);
  const [selected, setSelected] = useState<Item | null>(null);
  const [details, setDetails] = useState({ name: "", description: "" });
  const [adding, setAdding] = useState<{ parent: number | null; kind: "group" | "skill"; name: string } | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set()); // "g3" for a group, "s7" for a skill
  const [dragging, setDragging] = useState<Dragged | null>(null);
  const [drop, setDrop] = useState<Drop | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closing, close] = useClosing(onClose);
  const cancelInput = useRef(false); // Escape: the input's blur that follows mustn't save

  const [provider, setProvider] = useState<AIProvider>("claude_code");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const chatEnd = useRef<HTMLDivElement>(null);

  const reloadSkills = () => api.listSkills().then(setSkills, () => {});

  useEffect(() => {
    reloadSkills();
    api.getAISettings().then((s) => s.provider !== "none" && setProvider(s.provider), () => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !renaming && !adding && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close, renaming, adding]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking]);

  // Skills a target asks for, and the ones the user placed or added.
  const shown = skills.filter((s) => s.jobs > 0 || s.placed);
  const byId = new Map(shown.map((s) => [s.id, s]));
  /** A group's skills that aren't under another skill of the same group. */
  const topSkills = (groupId: number | null) =>
    shown.filter((s) => s.group_id === groupId && byId.get(s.parent_id ?? -1)?.group_id !== groupId).sort(byName);
  const subSkills = (s: SkillRow) => shown.filter((c) => c.parent_id === s.id && c.group_id === s.group_id).sort(byName);
  const skillAndBelow = (id: number): number[] => [id, ...shown.filter((c) => c.parent_id === id).flatMap((c) => skillAndBelow(c.id))];

  const find = (item: Item | null): { name: string; description: string } | undefined =>
    item?.kind === "group" ? tree.find((g) => g.id === item.id) : item ? skills.find((s) => s.id === item.id) : undefined;
  const current = find(selected);

  // The card below the tree edits the selected group or skill.
  useEffect(() => {
    if (current) setDetails({ name: current.name, description: current.description });
  }, [selected?.kind, selected?.id, current?.name, current?.description]); // eslint-disable-line react-hooks/exhaustive-deps

  const runGroups = async (action: () => Promise<SkillGroupNode[]>) => {
    try {
      setTree(await action());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      api.listSkillGroups().then(setTree, () => {}); // undo a move the server refused
    }
    reloadSkills(); // a deleted group's skills moved up
    onChanged();
  };

  const runSkills = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
    reloadSkills();
    onChanged();
  };

  const send = async (text: string) => {
    if (!text.trim() || thinking) return;
    const next: Message[] = [...messages, { role: "user", content: text.trim() }];
    setMessages(next);
    setDraft("");
    setThinking(true);
    setChatError(null);
    try {
      const { reply } = await api.chat(next, provider);
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (e) {
      setChatError((e as Error).message);
      setMessages(messages); // let the user send it again
      setDraft(text);
    } finally {
      setThinking(false);
    }
  };

  const toggle = (key: string, open?: boolean) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (open ?? next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const startAdd = (parent: number | null, kind: "group" | "skill") => {
    if (parent !== null) toggle(`g${parent}`, true);
    setAdding({ parent, kind, name: "" });
  };

  const submitAdd = () => {
    if (!adding) return;
    const { parent, kind, name } = adding;
    setAdding(null);
    if (!name.trim()) return;
    if (kind === "group") runGroups(() => api.createSkillGroup({ name, parent_id: parent }));
    else runSkills(() => api.createSkill({ name, group_id: parent }));
  };

  /** Saves what changed of a name and description. */
  const save = (item: Item, changes: { name?: string; description?: string }) => {
    const now = find(item);
    const body: { name?: string; description?: string } = {};
    if (changes.name?.trim() && changes.name.trim() !== now?.name) body.name = changes.name;
    if (changes.description !== undefined && changes.description !== now?.description) body.description = changes.description;
    if (!Object.keys(body).length) return;
    if (item.kind === "group") runGroups(() => api.updateSkillGroup(item.id, body));
    else runSkills(() => api.updateSkill(item.id, body, null));
  };

  const rename = () => {
    if (!renaming) return;
    const { kind, id, name } = renaming;
    setRenaming(null);
    save({ kind, id }, { name });
  };

  const isRenaming = (item: Item) => renaming?.kind === item.kind && renaming.id === item.id;
  const nameOrInput = (item: Item, name: string) =>
    isRenaming(item) ? (
      textInput(renaming!.name, name, (value) => setRenaming({ ...item, name: value }), rename, () => setRenaming(null))
    ) : (
      <span className="tname">{name}</span>
    );

  const endDrag = () => {
    setDragging(null);
    setDrop(null);
  };

  const moveGroup = (id: number, parent: number | null, index: number) => {
    if (parent !== null) toggle(`g${parent}`, true);
    setTree((t) => moved(t, id, parent, index));
    runGroups(() => api.updateSkillGroup(id, { parent_id: parent, index }));
  };

  const moveSkill = (id: number, groupId: number | null, parentId: number | null) => {
    if (groupId !== null) toggle(`g${groupId}`, true);
    if (parentId !== null) toggle(`s${parentId}`, true);
    setSkills((all) => all.map((s) => (s.id === id ? { ...s, group_id: groupId, parent_id: parentId, placed: true } : s)));
    runSkills(() => api.updateSkill(id, { group_id: groupId, parent_id: parentId }, null));
  };

  const removeSkill = (s: SkillRow) => {
    const asked = s.jobs === 1 ? "the target that asks for it" : `the ${s.jobs} targets that ask for it`;
    if (s.jobs && !confirm(`Remove ${s.name}? It is taken off ${asked}, and reading them again won't add it back.`)) return;
    runSkills(() => api.deleteSkill(s.id));
  };

  const dropGroupOn = (id: number, target: SkillGroupNode, zone: Zone) => {
    const open = !collapsed.has(`g${target.id}`) && children(tree, target.id).length > 0;
    // Just below an open group is the top of its list.
    if (zone === "inside" || (zone === "after" && open))
      return moveGroup(id, target.id, zone === "inside" ? children(tree, target.id).filter((g) => g.id !== id).length : 0);
    const siblings = children(tree, target.parent_id).filter((g) => g.id !== id);
    moveGroup(id, target.parent_id, siblings.findIndex((g) => g.id === target.id) + (zone === "after" ? 1 : 0));
  };

  /** Marks where the dragged item would land; edges: the top and bottom of the row mean before and after. */
  const over = (e: DragEvent<HTMLElement>, target: Omit<Drop, "zone">, allowed: boolean, edges: boolean) => {
    e.stopPropagation();
    if (!allowed) {
      if (drop) setDrop(null);
      return;
    }
    e.preventDefault();
    const r = e.currentTarget.getBoundingClientRect();
    const y = (e.clientY - r.top) / r.height;
    const zone: Zone = !edges ? "inside" : y < 0.28 ? "before" : y > 0.72 ? "after" : "inside";
    if (drop?.kind !== target.kind || drop.id !== target.id || drop.zone !== zone) setDrop({ ...target, zone });
  };

  const zoneAt = (kind: Drop["kind"], id: number | null) => (drop?.kind === kind && drop.id === id ? drop.zone : null);

  const same = (a: Item | null, b: Item | null) => !!a && !!b && a.kind === b.kind && a.id === b.id;
  const rowClass = (kind: string, d: Item | null, zone: Zone | null) =>
    `trow ${kind}${same(d, selected) ? " selected" : ""}${same(d, dragging) ? " dragging" : ""}${zone ? ` drop-${zone}` : ""}`;

  /** Click selects, double-click renames; a row being renamed can't be dragged. */
  const rowEvents = (item: Item, name: string) => ({
    ...dragFrom(item),
    draggable: !isRenaming(item),
    onClick: () => setSelected(item),
    onDoubleClick: () => setRenaming({ ...item, name }),
  });

  const dragFrom = (d: Dragged) => ({
    onDragStart: (e: DragEvent<HTMLElement>) => {
      e.stopPropagation();
      e.dataTransfer.setData("text/plain", String(d.id));
      e.dataTransfer.effectAllowed = "move";
      setDragging(d);
    },
    onDragEnd: endDrag,
  });

  const chevron = (key: string, has: boolean, name: string) => (
    <button
      type="button"
      className={`icon tchev${collapsed.has(key) ? " closed" : ""}`}
      style={{ visibility: has ? "visible" : "hidden" }}
      aria-label={collapsed.has(key) ? `Expand ${name}` : `Collapse ${name}`}
      onClick={(e) => {
        e.stopPropagation();
        toggle(key);
      }}
    >
      <ChevronIcon />
    </button>
  );

  const textInput = (value: string, placeholder: string, onChange: (v: string) => void, onDone: () => void, onCancel: () => void) => (
    <input
      className="trename"
      autoFocus
      value={value}
      placeholder={placeholder}
      maxLength={100}
      onChange={(e) => onChange(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onFocus={(e) => e.currentTarget.select()}
      onBlur={() => {
        if (!cancelInput.current) onDone();
        cancelInput.current = false;
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          e.stopPropagation(); // only the input, not the dialog
          cancelInput.current = true;
          onCancel();
        }
      }}
    />
  );

  const addRow = () =>
    adding && (
      <li key="adding" className="tnode leaf">
        <div className="trow">
          <span className="tchev-space" />
          {textInput(
            adding.name,
            adding.kind === "group" ? "New group" : "New skill",
            (name) => setAdding({ ...adding, name }),
            submitAdd,
            () => setAdding(null),
          )}
        </div>
      </li>
    );

  const skillNode = (s: SkillRow): ReactNode => {
    const subs = subSkills(s);
    const zone = zoneAt("skill", s.id);
    const parent = s.parent_id ? byId.get(s.parent_id) : undefined;
    return (
      <li key={`s${s.id}`} className={`tnode${subs.length ? "" : " leaf"}`}>
        <div
          className={rowClass("skill", { kind: "skill", id: s.id }, zone)}
          {...rowEvents({ kind: "skill", id: s.id }, s.name)}
          title={s.description || (s.jobs ? `Asked for in ${s.jobs} target${s.jobs === 1 ? "" : "s"}` : "Added by you")}
          onDragOver={(e) => over(e, { kind: "skill", id: s.id }, dragging?.kind === "skill" && !skillAndBelow(dragging.id).includes(s.id), true)}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (zone && dragging) moveSkill(dragging.id, s.group_id, zone === "inside" ? s.id : s.parent_id);
            endDrag();
          }}
        >
          {chevron(`s${s.id}`, subs.length > 0, s.name)}
          <span className="tgrip" aria-hidden>
            <GripIcon />
          </span>
          <span className={`dot mark-dot ${s.mark ?? "none"}`} />
          {isRenaming({ kind: "skill", id: s.id }) ? (
            nameOrInput({ kind: "skill", id: s.id }, s.name)
          ) : (
            <span className="tname">
              {s.name}
              {parent && parent.group_id !== s.group_id && <span className="muted"> · {parent.name}</span>}
            </span>
          )}
          {s.jobs > 0 && <span className="picker-tag">{s.jobs}</span>}
          <span className="tree-actions">
            <button
              type="button"
              className="icon"
              title={`Remove ${s.name}`}
              onClick={(e) => {
                e.stopPropagation();
                removeSkill(s);
              }}
            >
              <TrashIcon />
            </button>
          </span>
        </div>
        {subs.length > 0 && !collapsed.has(`s${s.id}`) && <ul className="tchildren">{subs.map(skillNode)}</ul>}
      </li>
    );
  };

  const groupNode = (g: SkillGroupNode): ReactNode => {
    const subgroups = children(tree, g.id);
    const items = topSkills(g.id);
    const addingHere = adding?.parent === g.id;
    const has = subgroups.length + items.length > 0 || addingHere;
    const zone = zoneAt("group", g.id);
    return (
      <li key={`g${g.id}`} className={`tnode${has ? "" : " leaf"}`}>
        <div
          className={rowClass("group", { kind: "group", id: g.id }, zone)}
          {...rowEvents({ kind: "group", id: g.id }, g.name)}
          title={g.description || undefined}
          onDragOver={(e) =>
            over(
              e,
              { kind: "group", id: g.id },
              !!dragging && (dragging.kind === "skill" || !descendants(tree, dragging.id).includes(g.id)),
              dragging?.kind === "group",
            )
          }
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (zone && dragging?.kind === "group") dropGroupOn(dragging.id, g, zone);
            else if (zone && dragging) moveSkill(dragging.id, g.id, null);
            endDrag();
          }}
        >
          {chevron(`g${g.id}`, has, g.name)}
          <span className="tgrip" aria-hidden>
            <GripIcon />
          </span>
          <span className="ticon" aria-hidden>
            <FolderIcon />
          </span>
          {nameOrInput({ kind: "group", id: g.id }, g.name)}
          <span className="tree-actions">
            <button
              type="button"
              className="icon"
              title={`Add a skill to ${g.name}`}
              onClick={(e) => {
                e.stopPropagation();
                startAdd(g.id, "skill");
              }}
            >
              <PlusIcon />
            </button>
            <button
              type="button"
              className="icon"
              title={`Add a group inside ${g.name}`}
              onClick={(e) => {
                e.stopPropagation();
                startAdd(g.id, "group");
              }}
            >
              <FolderPlusIcon />
            </button>
            <button
              type="button"
              className="icon"
              title={`Delete ${g.name}`}
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete ${g.name}? Its groups and skills move up one level.`)) runGroups(() => api.deleteSkillGroup(g.id));
              }}
            >
              <TrashIcon />
            </button>
          </span>
        </div>
        {has && !collapsed.has(`g${g.id}`) && (
          <ul className="tchildren">
            {subgroups.map(groupNode)}
            {items.map(skillNode)}
            {addingHere && addRow()}
          </ul>
        )}
      </li>
    );
  };

  const unsorted = topSkills(null);

  return (
    <div className={`overlay ${closing ? "closing" : ""}`} onMouseDown={close}>
      <div className="modal tree-modal" role="dialog" aria-labelledby="tree-title" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 id="tree-title">Skill tree</h2>
          <button type="button" className="icon" aria-label="Close" onClick={close}>
            <CloseIcon />
          </button>
        </div>
        <div className="tree-layout">
          <section className="tree-side">
            <p className="modal-hint">
              Drag groups and skills to move them. Drop a skill onto another to put it under it, like a library under
              its language. Double-click to rename; click to add a description.
            </p>
            <ul
              className={`tree-view${drop?.kind === "root" ? " drop-root" : ""}`}
              onDragOver={(e) => {
                if (dragging?.kind !== "group") return;
                e.preventDefault();
                if (drop?.kind !== "root") setDrop({ kind: "root", id: null, zone: "after" });
              }}
              onClick={(e) => e.target === e.currentTarget && setSelected(null)}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDrop(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                if (drop?.kind === "root" && dragging?.kind === "group")
                  moveGroup(dragging.id, null, children(tree, null).filter((g) => g.id !== dragging.id).length);
                endDrag();
              }}
            >
              {children(tree, null).map(groupNode)}
              {adding?.parent === null && addRow()}
              {unsorted.length > 0 && (
                <li className="tnode">
                  <div
                    className={rowClass("unsorted", null, zoneAt("unsorted", null))}
                    onDragOver={(e) => over(e, { kind: "unsorted", id: null }, dragging?.kind === "skill", false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (dragging?.kind === "skill") moveSkill(dragging.id, null, null);
                      endDrag();
                    }}
                  >
                    {chevron("u", true, "Unsorted")}
                    <span className="tgrip" />
                    <span className="tname">Unsorted</span>
                  </div>
                  {!collapsed.has("u") && <ul className="tchildren">{unsorted.map(skillNode)}</ul>}
                </li>
              )}
            </ul>
            <div className="row tree-add-row">
              <button type="button" onClick={() => startAdd(null, "group")}>
                <FolderPlusIcon />
                Add a top-level group
              </button>
            </div>
            {/* Always there, so selecting doesn't shift the tree under the pointer. */}
            <fieldset className="tree-edit" disabled={!current}>
              <label>
                Name
                <input
                  value={current ? details.name : ""}
                  placeholder={current ? "" : "Click a group or skill to edit it"}
                  maxLength={selected?.kind === "skill" ? 200 : 100}
                  onChange={(e) => setDetails({ ...details, name: e.target.value })}
                />
              </label>
              <label>
                Description
                <textarea
                  rows={2}
                  value={current ? details.description : ""}
                  maxLength={2000}
                  placeholder={current ? (selected?.kind === "group" ? "What this group is for" : "What it means") : ""}
                  onChange={(e) => setDetails({ ...details, description: e.target.value })}
                />
              </label>
              <div className="row">
                <span className="spacer" />
                <button
                  type="button"
                  className="primary"
                  disabled={
                    !current ||
                    !details.name.trim() ||
                    (details.name === current.name && details.description === current.description)
                  }
                  onClick={() => selected && save(selected, details)}
                >
                  Save
                </button>
              </div>
            </fieldset>
            {error && <div className="error">{error}</div>}
          </section>

          <section className="chat-side">
            <div className="chat-head">
              <strong>Recommendations</strong>
              <select value={provider} onChange={(e) => setProvider(e.target.value as AIProvider)} title="Which AI answers">
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="chat-body">
              {messages.length === 0 && !thinking ? (
                <div className="chat-empty">
                  <p className="muted">
                    The whole tree, with every requirement filed in it, is sent to the AI. Ask for recommendations, then
                    keep asking. You make the changes on the left.
                  </p>
                  <button type="button" className="primary" onClick={() => send(FIRST_QUESTION)}>
                    <SparkIcon />
                    Get recommendation
                  </button>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className={`chat-msg ${m.role}`}>
                    {m.role === "assistant" ? <Markdown text={m.content} /> : m.content}
                  </div>
                ))
              )}
              {thinking && (
                <div className="chat-msg assistant thinking">
                  <span className="spinner tiny dark" /> Thinking… this can take a minute.
                </div>
              )}
              {chatError && <div className="error">{chatError}</div>}
              <div ref={chatEnd} />
            </div>
            <form
              className="chat-input"
              onSubmit={(e) => {
                e.preventDefault();
                send(draft);
              }}
            >
              <textarea
                rows={2}
                value={draft}
                placeholder={messages.length ? "Ask a follow-up" : "Or ask your own question about the tree"}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(draft);
                  }
                }}
              />
              <button type="submit" className="primary" disabled={!draft.trim() || thinking} aria-label="Send">
                <SendIcon />
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
