import { useMemo, useState } from "react";
import type { SkillRow } from "../types";
import { SEP } from "../tree";

export type SearchPick = { skill: SkillRow } | { name: string } | { top: true };

interface Props {
  /** Every skill and group (placed or in Unsorted). */
  skills: SkillRow[];
  query: string;
  onQuery: (query: string) => void;
  onPick: (pick: SearchPick) => void;
  onCancel?: () => void;
  placeholder: string;
  /** "skill": skills to add to a job (groups only organize, so not those), plus a new one.
   *  "parent": places in the tree to put a skill under (groups too), plus the top level. */
  mode: "skill" | "parent";
  /** Left out of the list (the skill being placed, and what is under it). */
  exclude?: Set<number>;
  autoFocus?: boolean;
}

const MAX = 8;

/** Searches the user's tree; each result says where it sits ("Computer vision › Object detection"). */
export default function SkillSearch({ skills, query, onQuery, onPick, onCancel, placeholder, mode, exclude, autoFocus }: Props) {
  const [active, setActive] = useState(0);
  const byId = useMemo(() => new Map(skills.map((s) => [s.id, s])), [skills]);
  const where = (s: SkillRow) => {
    const names: string[] = [];
    for (let p = s.parent_id !== null ? byId.get(s.parent_id) : undefined; p; p = p.parent_id !== null ? byId.get(p.parent_id) : undefined)
      names.unshift(p.name);
    return s.placed ? names.join(SEP) || "Top level" : "Unsorted";
  };

  const q = query.trim().toLocaleLowerCase("tr");
  const options: SearchPick[] = useMemo(() => {
    const fits = skills
      .filter((s) => (mode === "skill" ? !s.is_group : s.placed) && !exclude?.has(s.id))
      // Names with the words in them, and names the words have in them as a word: "YOLOv8 models" finds
      // YOLO, "Python's" finds Python, "good" doesn't find Go.
      .filter((s) => {
        const n = s.name.toLocaleLowerCase("tr");
        return !q || n.includes(q) || (n.length > 1 && new RegExp(`(^|[^\\p{L}\\p{N}])${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\p{L}{2})`, "u").test(q));
      })
      // The exact name first, then names that start with the words, then the rest; the tree's before Unsorted.
      .sort((a, b) => {
        const rank = (s: SkillRow) => {
          const n = s.name.toLocaleLowerCase("tr");
          return (n === q ? 0 : n.startsWith(q) || q.startsWith(n) ? 1 : 2) * 2 + (s.placed ? 0 : 1);
        };
        return rank(a) - rank(b) || a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      })
      .slice(0, MAX)
      .map((skill) => ({ skill }));
    const exact = fits.some((o) => o.skill.name.toLocaleLowerCase("tr") === q);
    if (mode === "skill") return q && !exact ? [...fits, { name: query.trim() }] : fits;
    // Searching, the matches come first; Enter takes the best one, not the top level.
    return q ? [...fits, { top: true as const }] : [{ top: true as const }, ...fits];
  }, [skills, q, query, mode, exclude]);

  const at = Math.min(active, options.length - 1);
  return (
    <div className="skill-search">
      <input
        autoFocus={autoFocus}
        type="search"
        value={query}
        placeholder={placeholder}
        onChange={(e) => {
          onQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((at + 1) % options.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((at - 1 + options.length) % options.length);
          } else if (e.key === "Enter") {
            e.preventDefault();
            if (options[at] && (q || mode === "parent")) onPick(options[at]);
          } else if (e.key === "Escape" && onCancel && (query || mode === "parent")) {
            // An empty search lets Escape through, to close what it is in.
            e.stopPropagation();
            onCancel();
          }
        }}
      />
      {(q || mode === "parent") && options.length > 0 && (
        <ul className="skill-search-list" role="listbox">
          {options.map((o, i) => (
            <li key={"skill" in o ? o.skill.id : "top" in o ? "top" : "new"}>
              <button
                type="button"
                role="option"
                aria-selected={i === at}
                className={i === at ? "active" : ""}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()} // keep the input's focus
                onClick={() => onPick(o)}
              >
                {"skill" in o ? (
                  <>
                    <span className="ss-name">{o.skill.name}</span>
                    <span className="ss-where">{o.skill.is_group ? `Group · ${where(o.skill)}` : where(o.skill)}</span>
                  </>
                ) : "top" in o ? (
                  <span className="ss-name">Top level of the tree</span>
                ) : (
                  <>
                    <span className="ss-name">Add “{o.name}” as a new skill</span>
                    <span className="ss-where">Goes to Unsorted</span>
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
