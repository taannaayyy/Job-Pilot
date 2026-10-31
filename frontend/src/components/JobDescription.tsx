import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Requirement } from "../types";
import { CloseIcon, PlusIcon } from "./Icons";

interface Props {
  text: string | null;
  requirements: Requirement[];
  /** Saves the pasted or edited description; false when it couldn't. */
  onSave: (text: string) => Promise<boolean>;
  /** The user selected words to add as a skill, starting at `at` in the description; null when the job isn't a target yet. */
  onAddWords: ((words: string, at: number) => void) | null;
  /** Takes the skills picked from a highlight off the job. */
  onRemove: (requirementIds: number[]) => void;
  /** The skills under the pointer, here or in the list of skills: their words light up. */
  hovered: Hovered | null;
  onHover: (hovered: Hovered | null) => void;
}

/** Skills under the pointer, and where the pointer is. */
export interface Hovered {
  ids: number[];
  from: "text" | "list";
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// Any run of spaces or line breaks in the description matches a space in the words.
const wordsPattern = (w: string) => w.split(/\s+/).map(escape).join("\\s+");

/** Where a skill's words are in the description: where the user selected them, or, when that isn't
 *  known (or the description changed since), the first place they stand as whole words. */
function findWords(text: string, r: Requirement): [number, number] | null {
  const w = r.evidence?.trim();
  if (!w || w.length < 2) return null;
  if (r.evidence_at !== null && r.evidence_at < text.length) {
    const here = new RegExp(wordsPattern(w), "iy");
    here.lastIndex = r.evidence_at;
    const m = here.exec(text);
    if (m) return [m.index, m.index + m[0].length];
  }
  const m = new RegExp(`(?<![\\p{L}\\p{N}])${wordsPattern(w)}(?![\\p{L}\\p{N}])`, "iu").exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

/** The description with the words each skill was picked from highlighted, the skill's name on hover
 *  and a small × that takes the skill off the job. */
function highlighted(
  text: string,
  requirements: Requirement[],
  onRemove: (ids: number[]) => void,
  hovered: Hovered | null,
  onHover: (hovered: Hovered | null) => void,
): ReactNode[] {
  // One highlight per place; skills picked from the same words share it.
  const places = new Map<string, { start: number; end: number; skills: Requirement[] }>();
  for (const r of requirements) {
    const found = findWords(text, r);
    if (!found) continue;
    const key = found.join(":");
    const place = places.get(key) ?? { start: found[0], end: found[1], skills: [] };
    place.skills.push(r);
    places.set(key, place);
  }
  // In order; where two overlap, the first (the longer, when they start together) wins.
  const shown = [...places.values()].sort((a, b) => a.start - b.start || b.end - a.end);
  const out: ReactNode[] = [];
  let pos = 0;
  for (const { start, end, skills } of shown) {
    if (start < pos) continue;
    if (start > pos) out.push(text.slice(pos, start));
    const names = skills.map((r) => r.name).join(", ");
    out.push(
      <mark
        key={start}
        className={`picked${skills.some((r) => hovered?.ids.includes(r.id)) ? " lit" : ""}`}
        data-skills={names}
        onMouseEnter={() => onHover({ ids: skills.map((r) => r.id), from: "text" })}
        onMouseLeave={() => onHover(null)}
      >
        {text.slice(start, end)}
        {/* At the end of the words, so the pointer stays on the highlight on its way to it. */}
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
      </mark>,
    );
    pos = end;
  }
  out.push(text.slice(pos));
  return out;
}

/** The job description, to read while adding the skills it asks for: select words to add them. */
export default function JobDescription({ text, requirements, onSave, onAddWords, onRemove, hovered, onHover }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [picked, setPicked] = useState<{ words: string; at: number; x: number; y: number; below: boolean } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const addButton = useRef<HTMLButtonElement>(null);

  // Centered over the words, but never past the description's edges.
  useLayoutEffect(() => {
    const button = addButton.current;
    if (!picked || !button || !box.current) return;
    const half = button.offsetWidth / 2 + 4;
    const max = box.current.clientWidth - half;
    button.style.left = `${Math.max(half, Math.min(picked.x, max))}px`;
  }, [picked]);

  // A skill hovered in the list: its words are brought into view.
  useEffect(() => {
    if (hovered?.from === "list") box.current?.querySelector("mark.lit")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [hovered]);

  // A selection inside the description offers "Add as skill" just above it, or below it when the
  // words are at the top of what can be seen.
  const onSelect = () => {
    const sel = window.getSelection();
    const words = sel?.toString().replace(/\s+/g, " ").trim() ?? "";
    if (!sel || !words || words.length > 200 || !box.current || !box.current.contains(sel.anchorNode)) return setPicked(null);
    const range = sel.getRangeAt(0);
    // Where the words start in the description: the text before them (the × buttons hold none).
    const before = document.createRange();
    before.setStart(box.current, 0);
    before.setEnd(range.startContainer, range.startOffset);
    const at = before.toString().length + (range.toString().length - range.toString().trimStart().length);
    const r = range.getBoundingClientRect();
    const b = box.current.getBoundingClientRect();
    const seen = (box.current.closest(".job-pop-col") ?? box.current).getBoundingClientRect();
    const below = r.top - seen.top < 44;
    setPicked({ words, at, x: r.left + r.width / 2 - b.left, y: (below ? r.bottom : r.top) - b.top, below });
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
        {highlighted(text, requirements, onRemove, hovered, onHover)}
        {picked && onAddWords && (
          <button
            ref={addButton}
            type="button"
            className={`primary add-words${picked.below ? " below" : ""}`}
            style={{ left: picked.x, top: picked.y }}
            onMouseDown={(e) => e.preventDefault()} // keep the selection
            onClick={() => {
              onAddWords(picked.words, picked.at);
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
