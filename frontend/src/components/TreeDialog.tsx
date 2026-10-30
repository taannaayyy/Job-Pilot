import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { descendants, flat } from "../tree";
import type { AIProvider, SkillGroupNode } from "../types";
import { useClosing } from "../useClosing";
import { ArrowDownIcon, ArrowUpIcon, CloseIcon, PlusIcon, SendIcon, SparkIcon } from "./Icons";

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
const FIRST_QUESTION = "Look at my tree and the requirements filed in it, and recommend how to improve it.";

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
  const [editing, setEditing] = useState<{ id: number | null; parent: number | null; name: string; description: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closing, close] = useClosing(onClose);

  const [provider, setProvider] = useState<AIProvider>("claude_code");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const chatEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getAISettings().then((s) => s.provider !== "none" && setProvider(s.provider), () => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !editing && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close, editing]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking]);

  const run = async (action: () => Promise<SkillGroupNode[]>) => {
    try {
      setTree(await action());
      setError(null);
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };

  const saveEdit = async () => {
    if (!editing || !editing.name.trim()) return;
    const ok =
      editing.id === null
        ? await run(() => api.createSkillGroup({ name: editing.name, parent_id: editing.parent, description: editing.description }))
        : await run(() =>
            api.updateSkillGroup(editing.id!, { name: editing.name, description: editing.description, parent_id: editing.parent }),
          );
    if (ok) setEditing(null);
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

  const editor = (key: string) =>
    editing && (
      <li key={key} className="tree-edit">
        <label>
          Name
          <input
            autoFocus
            value={editing.name}
            maxLength={100}
            onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveEdit();
              if (e.key === "Escape") setEditing(null);
            }}
          />
        </label>
        <label>
          Inside
          <select
            value={editing.parent ?? ""}
            onChange={(e) => setEditing({ ...editing, parent: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Top level</option>
            {flat(tree)
              .filter(({ group }) => editing.id === null || !descendants(tree, editing.id).includes(group.id))
              .map(({ group, depth }) => (
                <option key={group.id} value={group.id}>
                  {"   ".repeat(depth) + group.name}
                </option>
              ))}
          </select>
        </label>
        <label className="wide">
          What belongs here <span className="muted">(the AI reads this when it files new requirements)</span>
          <textarea
            rows={2}
            value={editing.description}
            maxLength={2000}
            placeholder="e.g. Elasticsearch, OpenSearch, vector search"
            onChange={(e) => setEditing({ ...editing, description: e.target.value })}
          />
        </label>
        <div className="row">
          {editing.id !== null && (
            <button
              type="button"
              className="danger"
              onClick={async () => {
                const g = tree.find((x) => x.id === editing.id)!;
                if (!confirm(`Delete ${g.name}? Its subgroups and requirements move up one level.`)) return;
                if (await run(() => api.deleteSkillGroup(g.id))) setEditing(null);
              }}
            >
              Delete
            </button>
          )}
          <span className="spacer" />
          <button type="button" onClick={() => setEditing(null)}>
            Cancel
          </button>
          <button type="button" className="primary" onClick={saveEdit} disabled={!editing.name.trim()}>
            {editing.id === null ? "Add" : "Save"}
          </button>
        </div>
      </li>
    );

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
              Requirements are filed in these groups. Rename, move or add groups any time; the AI files new requirements
              in this tree.
            </p>
            <ul className="tree-list">
              {flat(tree).map(({ group, depth }) =>
                editing?.id === group.id ? (
                  editor(`e${group.id}`)
                ) : (
                  <li key={group.id} className={`tree-node depth-${Math.min(depth, 2)}`} style={{ paddingLeft: 8 + depth * 18 }}>
                    <button
                      type="button"
                      className="tree-name"
                      title={group.description || "Edit"}
                      onClick={() =>
                        setEditing({ id: group.id, parent: group.parent_id, name: group.name, description: group.description })
                      }
                    >
                      {group.name}
                      {group.skill_count > 0 && <span className="picker-tag">{group.skill_count}</span>}
                    </button>
                    <span className="tree-actions">
                      <button type="button" className="icon" title="Move up" onClick={() => run(() => api.updateSkillGroup(group.id, { move: "up" }))}>
                        <ArrowUpIcon />
                      </button>
                      <button type="button" className="icon" title="Move down" onClick={() => run(() => api.updateSkillGroup(group.id, { move: "down" }))}>
                        <ArrowDownIcon />
                      </button>
                      <button
                        type="button"
                        className="icon"
                        title={`Add a group inside ${group.name}`}
                        onClick={() => setEditing({ id: null, parent: group.id, name: "", description: "" })}
                      >
                        <PlusIcon />
                      </button>
                    </span>
                  </li>
                ),
              )}
              {editing?.id === null && editor("new")}
            </ul>
            <button type="button" className="tree-add" onClick={() => setEditing({ id: null, parent: null, name: "", description: "" })}>
              <PlusIcon />
              Add a top-level group
            </button>
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
