import { useRef, useState, type ReactNode } from "react";
import type { Requirement } from "../types";
import { CloseIcon, PlusIcon } from "./Icons";

interface Props {
  text: string | null;
  requirements: Requirement[];
  /** Saves the pasted or edited description; false when it couldn't. */
  onSave: (text: string) => Promise<boolean>;
  /** The user selected words to add as a skill; null when the job isn't a target yet. */
  onAddWords: ((words: string) => void) | null;
  /** Takes the skills picked from a highlight off the job. */
  onRemove: (requirementIds: number[]) => void;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The description with the words each skill was picked from highlighted, the skill's name on hover
 *  and a small × that takes the skill off the job. */
function highlighted(text: string, requirements: Requirement[], onRemove: (ids: number[]) => void): ReactNode[] {
  const words = new Map<string, Requirement[]>(); // the words (lower case) -> the skills picked from them
  for (const r of requirements) {
    const w = r.evidence?.trim();
    if (!w || w.length < 2) continue;
    words.set(w.toLowerCase(), [...(words.get(w.toLowerCase()) ?? []), r]);
  }
  if (!words.size) return [text];
  // Longest first, so "YOLOv8 models" wins over "YOLOv8"; any run of spaces or line breaks matches a space.
  const parts = [...words.keys()].sort((a, b) => b.length - a.length).map((w) => w.split(/\s+/).map(escape).join("\\s+"));
  const pattern = new RegExp(`(${parts.join("|")})`, "gi");
  return text.split(pattern).map((piece, i) => {
    if (i % 2 === 0) return piece;
    const skills = words.get(piece.replace(/\s+/g, " ").toLowerCase()) ?? [];
    const names = skills.map((r) => r.name).join(", ");
    return (
      <mark key={i} className="picked" title={names}>
        {piece}
        {skills.length > 0 && (
          // At the end of the words, so the pointer stays on the highlight on its way to it.
          <button
            type="button"
            className="unpick"
            aria-label={`Remove ${names} from this job`}
            title={`Remove ${names} from this job`}
            onMouseDown={(e) => e.preventDefault()}
            onMouseUp={(e) => e.stopPropagation()} // not a selection
            onClick={() => onRemove(skills.map((r) => r.id))}
          >
            <CloseIcon />
          </button>
        )}
      </mark>
    );
  });
}

/** The job description, to read while adding the skills it asks for: select words to add them. */
export default function JobDescription({ text, requirements, onSave, onAddWords, onRemove }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [picked, setPicked] = useState<{ words: string; x: number; y: number; below: boolean } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  // A selection inside the description offers "Add as skill" just above it, or below it when the
  // words are at the top of what can be seen.
  const onSelect = () => {
    const sel = window.getSelection();
    const words = sel?.toString().replace(/\s+/g, " ").trim() ?? "";
    if (!sel || !words || words.length > 200 || !box.current || !box.current.contains(sel.anchorNode)) return setPicked(null);
    const r = sel.getRangeAt(0).getBoundingClientRect();
    const b = box.current.getBoundingClientRect();
    const seen = (box.current.closest(".job-pop-col") ?? box.current).getBoundingClientRect();
    const below = r.top - seen.top < 44;
    setPicked({ words, x: r.left + r.width / 2 - b.left, y: (below ? r.bottom : r.top) - b.top, below });
  };

  if (!text || draft !== null)
    return (
      <div className="paste">
        <textarea
          rows={14}
          value={draft ?? ""}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Paste the job description here, then select the words that name a skill to add it."
        />
        <div className="actions">
          {draft !== null && text && (
            <button type="button" onClick={() => setDraft(null)}>
              Cancel
            </button>
          )}
          <button
            type="button"
            className="primary"
            disabled={!draft?.trim()}
            onClick={async () => {
              if (draft && (await onSave(draft))) setDraft(null);
            }}
          >
            Save description
          </button>
        </div>
      </div>
    );

  return (
    <div className="job-description">
      <div className="job-description-head">
        <h3>Job description</h3>
        <button type="button" className="link quiet" onClick={() => setDraft(text)}>
          Edit
        </button>
      </div>
      <p className="muted small-note">
        {onAddWords
          ? "Select the words that name a skill to add it. They stay highlighted."
          : "Choose a role group on the right to add the skills it asks for."}
      </p>
      <div ref={box} className="raw-text selectable" onMouseUp={onSelect} onKeyUp={onSelect}>
        {highlighted(text, requirements, onRemove)}
        {picked && onAddWords && (
          <button
            type="button"
            className={`primary add-words${picked.below ? " below" : ""}`}
            style={{ left: picked.x, top: picked.y }}
            onMouseDown={(e) => e.preventDefault()} // keep the selection
            onClick={() => {
              onAddWords(picked.words);
              setPicked(null);
            }}
          >
            <PlusIcon />
            Add as skill
          </button>
        )}
      </div>
    </div>
  );
}
