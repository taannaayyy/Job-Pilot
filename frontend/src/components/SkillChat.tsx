import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import type { AIProvider } from "../types";
import { CloseIcon, SendIcon, SettingsIcon, SparkIcon } from "./Icons";

type Message = { role: "user" | "assistant"; content: string };

const PROVIDERS: { value: AIProvider; label: string }[] = [
  { value: "claude_code", label: "Claude Code" },
  { value: "anthropic", label: "Claude API" },
  { value: "openai", label: "OpenAI-compatible" },
  { value: "ollama", label: "Ollama" },
];
const FIRST_QUESTION =
  "Look at my tree and how many postings ask for each skill, and recommend how to improve it, including where the skills in Unsorted belong.";

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

/** The recommendation chat about the tree; kept mounted while hidden, so the conversation stays. */
export default function SkillChat({ hidden, onClose, onOpenSettings }: { hidden: boolean; onClose: () => void; onOpenSettings: () => void }) {
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
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking]);

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

  return (
    <aside className="map-details chat-panel" aria-label="Recommendations" hidden={hidden}>
      <div className="chat-head">
        <strong>Recommendations</strong>
        <span className="spacer" />
        <select value={provider} onChange={(e) => setProvider(e.target.value as AIProvider)} title="Which AI answers">
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <button type="button" className="icon" title="AI settings: models, keys" aria-label="AI settings" onClick={onOpenSettings}>
          <SettingsIcon />
        </button>
        <button type="button" className="icon" aria-label="Close recommendations" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="chat-body">
        {messages.length === 0 && !thinking ? (
          <div className="chat-empty">
            <p className="muted">
              The whole tree, with how many postings ask for each skill, and Unsorted are sent to the AI. Ask for recommendations, then
              keep asking. You make the changes in the tree.
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
    </aside>
  );
}
