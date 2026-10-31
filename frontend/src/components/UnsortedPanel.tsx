import { useState } from "react";
import { UNSORTED_TARGET, type MapNode } from "../skillmap";
import type { SkillRow } from "../types";
import { CloseIcon, EditIcon, TrashIcon } from "./Icons";
import SkillSearch from "./SkillSearch";
import type { TreeEdit } from "./SkillMapViews";

interface Props {
  /** The skills waiting in Unsorted, most asked first. */
  waiting: MapNode[];
  total: number;
  /** The whole tree, to search for where a skill belongs. */
  tree: SkillRow[];
  edit: TreeEdit;
  /** Puts a skill in the tree, under the node (null: the top level). */
  onPlace: (id: number, parent: number | null) => void;
  /** Shows a skill's details, with the postings that ask for it. */
  onSelect: (key: string) => void;
  onClose: () => void;
}

/** The skills postings ask for that aren't in the tree yet, in place of the details: place them one
 *  after another, with a search of the tree or by dragging. A node dropped here leaves the tree. */
export default function UnsortedPanel({ waiting, total, tree, edit, onPlace, onSelect, onClose }: Props) {
  const [placing, setPlacing] = useState<{ id: number; query: string } | null>(null);
  return (
    <aside
      className={`map-details unsorted-panel${edit.drag.state(UNSORTED_TARGET)}`}
      aria-label="Unsorted"
      {...edit.drag.props(UNSORTED_TARGET)}
    >
      <div className="unsorted-head">
        <h2>Unsorted · {waiting.length}</h2>
        <button type="button" className="icon" aria-label="Close Unsorted" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <p className="muted small-note">
        Skills you added on jobs that aren't in your tree yet. Place each one, or drag it onto a node in the tree. Drop a node here to take
        it out of the tree.
      </p>
      {waiting.length === 0 ? (
        <p className="unsorted-done muted">Everything is placed.</p>
      ) : (
        <ul className="unsorted-list">
          {waiting.map((n) => {
            const s = n.skill!;
            const quotes = s.quotes ?? [];
            return (
              <li key={n.key} className={`unsorted-row${edit.drag.state(n)}`} {...edit.drag.props(n)}>
                <div className="unsorted-top">
                  <button type="button" className="link unsorted-name" title="Show its details and postings" onClick={() => onSelect(n.key)}>
                    {n.name}
                  </button>
                  <span className="spacer" />
                  <button type="button" className="small primary" onClick={() => setPlacing(placing?.id === s.id ? null : { id: s.id, query: "" })}>
                    Place…
                  </button>
                  <button type="button" className="icon" title={`Edit ${n.name}`} onClick={() => edit.onEdit(n)}>
                    <EditIcon />
                  </button>
                  <button type="button" className="icon" title={`Remove ${n.name}`} onClick={() => edit.onRemove(n)}>
                    <TrashIcon />
                  </button>
                </div>
                <div className="unsorted-quotes muted">
                  <span className="unsorted-count">
                    In {n.jobs.size} of {total} posting{total === 1 ? "" : "s"}
                  </span>
                  {quotes.slice(0, 3).map((q) => (
                    <span key={q}>“{q}”</span>
                  ))}
                </div>
                {placing?.id === s.id && (
                  <div className="place-in-tree">
                    <SkillSearch
                      autoFocus
                      skills={tree}
                      query={placing.query}
                      onQuery={(query) => setPlacing({ id: s.id, query })}
                      mode="parent"
                      placeholder={`Where does ${n.name} belong? Search the tree`}
                      onCancel={() => setPlacing(null)}
                      onPick={(pick) => {
                        if ("name" in pick) return;
                        setPlacing(null);
                        onPlace(s.id, "top" in pick ? null : pick.skill.id);
                      }}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
