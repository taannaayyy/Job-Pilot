import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Highlight, Requirement } from "../types";
import { CloseIcon, HighlightIcon, PlusIcon } from "./Icons";

interface Props {
  text: string | null;
  requirements: Requirement[];
  /** Words highlighted to read again, not skills. */
  highlights: Highlight[];
  onHighlightsChange: (highlights: Highlight[]) => void;
  /** Saves the pasted or edited description; false when it couldn't. */
  onSave: (text: string) => Promise<boolean>;
  /** The user selected words to add as a skill, starting at `at` in the description; null when the job isn't a target yet. */
  onAddWords: ((words: string, at: number) => void) | null;
  /** Writes the note on the skills picked from the same words; an empty note removes it. */
  onNote: (requirementIds: number[], note: string) => void;
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

/** Where words are in the description: where the user selected them, or, when that isn't known
 *  (or the description changed since), the first place they stand as whole words. */
function findWords(text: string, words: string | null, at: number | null): [number, number] | null {
  const w = words?.trim();
  if (!w || w.length < 2) return null;
  if (at !== null && at < text.length) {
    const here = new RegExp(wordsPattern(w), "iy");
    here.lastIndex = at;
    const m = here.exec(text);
    if (m) return [m.index, m.index + m[0].length];
  }
  const m = new RegExp(`(?<![\\p{L}\\p{N}])${wordsPattern(w)}(?![\\p{L}\\p{N}])`, "iu").exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

/** Where each highlight is now, in order, leaving out ones no longer found or overlapping an earlier one. */
function notedPlaces(text: string, highlights: Highlight[]) {
  const found = highlights
    .map((h, i) => ({ i, at: findWords(text, h.words, h.at) }))
    .filter((h): h is { i: number; at: [number, number] } => h.at !== null)
    .map(({ i, at }) => ({ i, start: at[0], end: at[1] }))
    .sort((a, b) => a.start - b.start || b.end - a.end);
  const kept: typeof found = [];
  for (const h of found) if (!kept.length || h.start >= kept[kept.length - 1].end) kept.push(h);
  return kept;
}

/** Where each skill's words are: one place per words, shared by the skills picked from them. */
function skillPlaces(text: string, requirements: Requirement[]) {
  const places = new Map<string, { start: number; end: number; skills: Requirement[] }>();
  for (const r of requirements) {
    const found = findWords(text, r.evidence, r.evidence_at);
    if (!found) continue;
    const key = found.join(":");
    const place = places.get(key) ?? { start: found[0], end: found[1], skills: [] };
    place.skills.push(r);
    places.set(key, place);
  }
  // In order; where two overlap, the first (the longer, when they start together) wins.
  const shown = [...places.values()].sort((a, b) => a.start - b.start || b.end - a.end);
  const kept: typeof shown = [];
  for (const p of shown) if (!kept.length || p.start >= kept[kept.length - 1].end) kept.push(p);
  return kept;
}

/** A highlight a note is written on: the skills picked from the same words, or a highlight. */
type NoteTarget = { skills: number[] } | { highlight: number };

interface Marks {
  onRemove: (ids: number[]) => void;
  onUnnote: (i: number) => void;
  /** A highlight clicked: its note is opened under it. */
  onOpen: (target: NoteTarget, el: HTMLElement) => void;
  hovered: Hovered | null;
  onHover: (hovered: Hovered | null) => void;
  noteHovered: number | null;
  onNoteHover: (i: number | null) => void;
}

// A click that ends a selection isn't one on the highlight.
const clicked = (open: () => void) => () => window.getSelection()?.isCollapsed !== false && open();

/** The description with the words each skill was picked from highlighted, the skill's name and note on
 *  hover and a small × that takes the skill off the job; and, between them, the words highlighted only
 *  to read again, in a lighter marker with their own note and ×. */
function highlighted(text: string, requirements: Requirement[], highlights: Highlight[], m: Marks): ReactNode[] {
  const skills = skillPlaces(text, requirements);
  const noted = notedPlaces(text, highlights);

  // The text outside the skills' words, cut where highlights start and end.
  const pieces: { start: number; end: number; note: number | null }[] = [];
  const plain = (from: number, to: number) => {
    let p = from;
    for (const h of noted) {
      if (h.end <= p || h.start >= to) continue;
      if (h.start > p) pieces.push({ start: p, end: h.start, note: null });
      p = Math.min(h.end, to);
      pieces.push({ start: Math.max(h.start, from), end: p, note: h.i });
    }
    if (p < to) pieces.push({ start: p, end: to, note: null });
  };
  let pos = 0;
  for (const { start, end } of skills) {
    plain(pos, start);
    pos = end;
  }
  plain(pos, text.length);
  // A highlight's × and note mark go on its last piece, at the end of the words.
  const last = new Map(pieces.map((piece, k) => [piece.note, k]));

  const out: ReactNode[] = [];
  const pushPlain = (from: number, to: number) => {
    pieces.forEach((piece, k) => {
      if (piece.start < from || piece.end > to || piece.start === piece.end) return;
      if (piece.note === null) return void out.push(text.slice(piece.start, piece.end));
      const i = piece.note;
      const note = highlights[i].note?.trim() ?? "";
      const isLast = last.get(i) === k;
      out.push(
        <mark
          key={`n${piece.start}`}
          className={`noted${m.noteHovered === i ? " lit" : ""}${note && isLast ? " has-note" : ""}`}
          data-note={note || undefined}
          onMouseEnter={() => m.onNoteHover(i)}
          onMouseLeave={() => m.onNoteHover(null)}
          onClick={(e) => clicked(() => m.onOpen({ highlight: i }, e.currentTarget))()}
        >
          {text.slice(piece.start, piece.end)}
          {isLast && (
            <button
              type="button"
              className="unpick"
              aria-label="Remove this highlight"
              title="Remove this highlight"
              onMouseDown={(e) => e.preventDefault()}
              onMouseUp={(e) => e.stopPropagation()} // not a selection
              onClick={(e) => {
                e.stopPropagation(); // not a click on the highlight
                m.onUnnote(i);
              }}
            >
              <CloseIcon />
            </button>
          )}
        </mark>,
      );
    });
  };

  pos = 0;
  for (const { start, end, skills: picked } of skills) {
    pushPlain(pos, start);
    const ids = picked.map((r) => r.id);
    const names = picked.map((r) => r.name).join(", ");
    const notes = [...new Set(picked.map((r) => r.note?.trim()).filter(Boolean))].join("\n");
    out.push(
      <mark
        key={start}
        className={`picked${picked.some((r) => m.hovered?.ids.includes(r.id)) ? " lit" : ""}${notes ? " has-note" : ""}`}
        data-skills={notes ? `${names}\n${notes}` : names}
        onMouseEnter={() => m.onHover({ ids, from: "text" })}
        onMouseLeave={() => m.onHover(null)}
        onClick={(e) => clicked(() => m.onOpen({ skills: ids }, e.currentTarget))()}
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
          onClick={(e) => {
            e.stopPropagation(); // not a click on the highlight
            m.onRemove(ids);
          }}
        >
          <CloseIcon />
        </button>
      </mark>,
    );
    pos = end;
  }
  pushPlain(pos, text.length);
  return out;
}

/** The job description, to read while adding the skills it asks for: select words to add them. */
export default function JobDescription({
  text,
  requirements,
  highlights,
  onHighlightsChange,
  onSave,
  onAddWords,
  onNote,
  onRemove,
  hovered,
  onHover,
}: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [picked, setPicked] = useState<{ words: string; at: number; end: number; x: number; y: number; below: boolean } | null>(null);
  const [noteHovered, setNoteHovered] = useState<number | null>(null);
  const [editing, setEditing] = useState<{ target: NoteTarget; x: number; y: number; draft: string } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const addButton = useRef<HTMLDivElement>(null);

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

  // A selection inside the description offers "Highlight" and "Add as skill" just above it, or below
  // it when the words are at the top of what can be seen.
  const onSelect = () => {
    setEditing(null);
    const sel = window.getSelection();
    const words = sel?.toString().replace(/\s+/g, " ").trim() ?? "";
    if (!sel || !words || words.length > 5000 || !box.current || !box.current.contains(sel.anchorNode)) return setPicked(null);
    const range = sel.getRangeAt(0);
    // Where the words start in the description: the text before them (the × buttons hold none).
    const before = document.createRange();
    before.setStart(box.current, 0);
    before.setEnd(range.startContainer, range.startOffset);
    const at = before.toString().length + (range.toString().length - range.toString().trimStart().length);
    const end = at + range.toString().trim().length;
    const r = range.getBoundingClientRect();
    const b = box.current.getBoundingClientRect();
    const seen = (box.current.closest(".job-pop-col") ?? box.current).getBoundingClientRect();
    const below = r.top - seen.top < 44;
    setPicked({ words, at, end, x: r.left + r.width / 2 - b.left, y: (below ? r.bottom : r.top) - b.top, below });
  };

  // The selected words highlighted, joined with the highlights they touch.
  const note = (start: number, end: number) => {
    if (!text) return;
    const kept: Highlight[] = [];
    const notes: string[] = [];
    for (const h of highlights) {
      const found = findWords(text, h.words, h.at);
      if (found && found[0] <= end && found[1] >= start) {
        start = Math.min(start, found[0]);
        end = Math.max(end, found[1]);
        if (h.note?.trim()) notes.push(h.note.trim());
      } else kept.push(h);
    }
    onHighlightsChange([...kept, { words: text.slice(start, end), at: start, note: notes.join("\n") }]);
  };

  // A highlight's note, opened just under the words it's written on.
  const openNote = (target: NoteTarget, el: HTMLElement) => {
    if (!box.current) return;
    const r = el.getBoundingClientRect();
    const b = box.current.getBoundingClientRect();
    const draft =
      "highlight" in target
        ? (highlights[target.highlight]?.note ?? "")
        : [...new Set(requirements.filter((q) => target.skills.includes(q.id)).map((q) => q.note?.trim()).filter(Boolean))].join("\n");
    setPicked(null);
    setEditing({ target, x: Math.max(0, Math.min(r.left - b.left, b.width - 300)), y: r.bottom - b.top + 6, draft });
  };
  const saveNote = () => {
    if (!editing) return;
    const note = editing.draft.trim();
    const t = editing.target;
    if ("highlight" in t) onHighlightsChange(highlights.map((h, k) => (k === t.highlight ? { ...h, note } : h)));
    else onNote(t.skills, note);
    setEditing(null);
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
          ? "Select words to highlight them, or to add the skill they name. Click a highlight to write a note on it."
          : "Select words to highlight them; click one to write a note on it. Choose a role group on the right to add the skills it asks for."}
      </p>
      <div ref={box} className="raw-text selectable" onMouseUp={onSelect} onKeyUp={onSelect}>
        {highlighted(text, requirements, highlights, {
          onRemove,
          onUnnote: (i) => {
            setNoteHovered(null);
            setEditing(null);
            onHighlightsChange(highlights.filter((_, k) => k !== i));
          },
          onOpen: openNote,
          hovered,
          onHover,
          noteHovered,
          onNoteHover: setNoteHovered,
        })}
        {editing && (
          <div
            className="mark-note"
            style={{ left: editing.x, top: editing.y }}
            onMouseUp={(e) => e.stopPropagation()} // not a selection in the description
            onKeyUp={(e) => e.stopPropagation()}
          >
            <textarea
              autoFocus
              rows={3}
              value={editing.draft}
              placeholder="Write a note on these words"
              onChange={(e) => setEditing({ ...editing, draft: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation(); // closes the note, not the job
                  setEditing(null);
                } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveNote();
              }}
            />
            <div className="actions">
              <button type="button" onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button type="button" className="primary" onClick={saveNote}>
                Save note
              </button>
            </div>
          </div>
        )}
        {picked && (
          <div
            ref={addButton}
            className={`add-words${picked.below ? " below" : ""}`}
            style={{ left: picked.x, top: picked.y }}
            onMouseDown={(e) => e.preventDefault()} // keep the selection
          >
            <button
              type="button"
              onClick={() => {
                note(picked.at, picked.end);
                setPicked(null);
                window.getSelection()?.removeAllRanges();
              }}
            >
              <HighlightIcon />
              Highlight
            </button>
            {onAddWords && picked.words.length <= 200 && (
              <button
                type="button"
                className="primary"
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
        )}
      </div>
    </div>
  );
}
