import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDateTime } from "../format";
import { flat, path } from "../tree";
import { SKILL_MARK_LABELS, type SkillDetail, type SkillGroupNode, type SkillMark, type SkillRow } from "../types";
import { useClosing } from "../useClosing";
import { CheckIcon, CloseIcon } from "./Icons";
import MarkPicker from "./MarkPicker";

interface Props {
  skillId: number;
  groupId: number | null;
  onClose: () => void;
  onChanged: () => void;
  onOpenJob: (id: number) => void;
}

const markText = (m: SkillMark | null) => (m ? SKILL_MARK_LABELS[m] : "No mark");

export default function SkillPanel({ skillId, groupId, onClose, onChanged, onOpenJob }: Props) {
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tree, setTree] = useState<SkillGroupNode[]>([]);
  const [allSkills, setAllSkills] = useState<SkillRow[]>([]);
  const [closing, close] = useClosing(onClose, 220);

  useEffect(() => {
    api.listSkillGroups().then(setTree, () => {});
    api.listSkills().then(setAllSkills, () => {});
  }, []);

  useEffect(() => {
    api.getSkill(skillId, groupId).then(
      (s) => {
        setSkill(s);
        setNote(s.plan_note);
      },
      (e) => setError(e.message),
    );
  }, [skillId, groupId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const update = async (body: { mark?: SkillMark | null; plan_note?: string; group_id?: number | null; parent_id?: number | null }) => {
    try {
      const s = await api.updateSkill(skillId, body, groupId);
      setSkill(s);
      setError(null);
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };

  return (
    <div className={`overlay side ${closing ? "closing" : ""}`} onMouseDown={close}>
      <aside className="panel" onMouseDown={(e) => e.stopPropagation()}>
        {!skill ? (
          <div className="empty">{error ?? <span className="spinner" aria-label="Loading" />}</div>
        ) : (
          <>
            <header className="panel-head">
              <div className="panel-title">
                <div className="card-company">{skill.group_id ? path(tree, skill.group_id) : "Unsorted"}</div>
                <h2>{skill.name}</h2>
                <div className="muted">
                  Asked for in {skill.jobs.length} target{skill.jobs.length === 1 ? "" : "s"}
                </div>
              </div>
              <button type="button" className="icon" aria-label="Close" onClick={close}>
                <CloseIcon />
              </button>
            </header>

            <h3>Your level</h3>
            <MarkPicker name={skill.name} value={skill.mark} onChange={(mark) => update({ mark })} />

            <h3>Place in the tree</h3>
            <div className="fields place">
              <label>
                Group
                <select
                  value={skill.group_id ?? ""}
                  onChange={(e) => update({ group_id: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">Unsorted</option>
                  {flat(tree).map(({ group, depth }) => (
                    <option key={group.id} value={group.id}>
                      {"\u00a0\u00a0\u00a0".repeat(depth) + group.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Belongs to
                <select
                  value={skill.parent_id ?? ""}
                  onChange={(e) => update({ parent_id: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">Nothing</option>
                  {allSkills
                    .filter((s) => s.id !== skill.id)
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            {skill.group_locked && (
              <p className="field-note">Placed by you: reading postings again won't move it.</p>
            )}

            <h3>Your plan</h3>
            <textarea
              className="plan-note"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What will you do about it? A course, a book, a project idea…"
            />
            <div className="actions">
              <button
                type="button"
                className={`primary ${saved ? "saved" : ""}`}
                disabled={note === skill.plan_note && !saved}
                onClick={async () => {
                  if (await update({ plan_note: note })) {
                    setSaved(true);
                    setTimeout(() => setSaved(false), 1600);
                  }
                }}
              >
                {saved ? <><CheckIcon /> Saved</> : "Save plan"}
              </button>
            </div>
            {error && <div className="error">{error}</div>}

            <h3>Where it's asked for</h3>
            <ul className="evidence">
              {skill.jobs.map((j) => (
                <li key={j.job_id}>
                  <button type="button" className="evidence-job" onClick={() => onOpenJob(j.job_id)}>
                    <span className="evidence-title">
                      <strong>{j.title}</strong>
                      <span className="muted"> at {j.company}</span>
                    </span>
                    <span className={`imp-tag ${j.importance}`}>{j.importance === "must" ? "Must" : "Nice"}</span>
                  </button>
                  {(j.years || j.detail) && (
                    <span className="evidence-meta">
                      {j.years && <span className="years-tag">{j.years} yrs</span>}
                      {j.detail && <span className="muted">Fields: {j.detail}</span>}
                    </span>
                  )}
                  {j.evidence && <q>{j.evidence}</q>}
                </li>
              ))}
            </ul>

            {skill.history.length > 0 && (
              <>
                <h3>History</h3>
                <ol className="history">
                  {[...skill.history].reverse().map((h, i) => (
                    <li key={i}>
                      <span className={`dot mark-dot ${h.to_mark ?? "none"}`} />
                      <span>
                        {markText(h.from_mark)} → <strong>{markText(h.to_mark)}</strong>
                      </span>
                      <time className="muted">{fmtDateTime(h.timestamp)}</time>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
