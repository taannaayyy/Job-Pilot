import { useEffect, useState } from "react";
import { api, type JobChanges } from "../api";
import { fmtDateTime } from "../format";
import type { Importance, JobDetail, Requirement, RoleGroup } from "../types";
import { CloseIcon, PlusIcon, RefreshIcon } from "./Icons";

interface Props {
  job: JobDetail;
  groups: RoleGroup[];
  onChange: (job: JobDetail) => void;
  onGroupsChanged: () => void;
  onError: (message: string | null) => void;
}

const NEW_GROUP = "new";

/** The job's part in Skill Gap: which role group it is a target of, and what it requires. */
export default function JobSkills({ job, groups, onChange, onGroupsChanged, onError }: Props) {
  const [newGroup, setNewGroup] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null); // the description being edited
  const [adding, setAdding] = useState("");
  const [addImportance, setAddImportance] = useState<Importance>("must");
  const reading = job.extraction_status === "pending" || job.extraction_status === "running";

  // The requirements appear by themselves once the description has been read.
  useEffect(() => {
    if (!reading) return;
    const timer = setInterval(() => api.getJob(job.id).then(onChange, () => {}), 2500);
    return () => clearInterval(timer);
  }, [reading, job.id, onChange]);

  const run = async (action: () => Promise<JobDetail>) => {
    try {
      onChange(await action());
      onError(null);
      return true;
    } catch (e) {
      onError((e as Error).message);
      return false;
    }
  };

  const update = (body: JobChanges) => run(() => api.updateJob(job.id, body));

  const createGroup = async () => {
    const name = newGroup?.trim();
    if (!name) return setNewGroup(null);
    try {
      const g = await api.createGroup(name);
      setNewGroup(null);
      onGroupsChanged();
      await update({ target_group_id: g.id });
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const must = job.requirements.filter((r) => r.importance === "must");
  const nice = job.requirements.filter((r) => r.importance === "nice");

  const chip = (r: Requirement) => (
    <li key={r.id} className={`req-chip ${r.mark ?? "none"}`} title={r.evidence ?? undefined}>
      <button
        type="button"
        className="req-name"
        title={`${r.evidence ? `"${r.evidence}"\n` : ""}Click to make it ${r.importance === "must" ? "nice to have" : "a must-have"}`}
        onClick={() => run(() => api.setRequirementImportance(job.id, r.id, r.importance === "must" ? "nice" : "must"))}
      >
        {r.name}
        {r.min_years ? <span className="req-years">{r.min_years}{r.max_years ? `–${r.max_years}` : "+"}y</span> : null}
      </button>
      <button
        type="button"
        className="req-remove"
        aria-label={`Remove ${r.name}`}
        onClick={() => run(() => api.removeRequirement(job.id, r.id))}
      >
        <CloseIcon />
      </button>
    </li>
  );

  return (
    <section className="job-skills">
      <h3>Skill Gap</h3>
      <div className="target-row">
        <label className="inline target-select">
          Target of
          {newGroup !== null ? (
            <span className="row">
              <input
                autoFocus
                value={newGroup}
                maxLength={100}
                placeholder="Role group name"
                onChange={(e) => setNewGroup(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    createGroup();
                  }
                  if (e.key === "Escape") {
                    e.stopPropagation();
                    setNewGroup(null);
                  }
                }}
              />
              <button type="button" className="primary" onClick={createGroup}>
                Add
              </button>
            </span>
          ) : (
            <select
              value={job.target_group_id ?? ""}
              onChange={(e) => {
                if (e.target.value === NEW_GROUP) return setNewGroup("");
                update({ target_group_id: e.target.value ? Number(e.target.value) : null });
              }}
            >
              <option value="">Not a target</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
              <option value={NEW_GROUP}>New group…</option>
            </select>
          )}
        </label>
        <label className="check" title="Keep this job only to study the role: it disappears from the job board">
          <input type="checkbox" checked={job.study_only} onChange={(e) => update({ study_only: e.target.checked })} />
          Study only
        </label>
      </div>

      {job.target_group_id !== null && (
        <>
          {!job.raw_text || text !== null ? (
            <div className="paste">
              <textarea
                rows={6}
                value={text ?? ""}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the job description here. The requirements are read from it."
              />
              <div className="actions">
                {text !== null && job.raw_text && (
                  <button type="button" onClick={() => setText(null)}>
                    Cancel
                  </button>
                )}
                <button
                  type="button"
                  className="primary"
                  disabled={!text?.trim()}
                  onClick={async () => {
                    if (await update({ raw_text: text })) setText(null);
                  }}
                >
                  Save description
                </button>
              </div>
            </div>
          ) : (
            <div className="extract-status">
              {reading ? (
                <>
                  <span className="spinner tiny dark" /> Reading the description…
                </>
              ) : job.extraction_status === "failed" ? (
                <span className="err">{job.extraction_error ?? "Couldn't read the description."}</span>
              ) : job.extracted_at ? (
                <span className="muted">
                  Read with {job.extracted_with} · {fmtDateTime(job.extracted_at)}
                  {job.extraction_error && <span className="warn-text"> · {job.extraction_error}</span>}
                </span>
              ) : null}
              <span className="spacer" />
              <button type="button" className="link quiet" onClick={() => setText(job.raw_text ?? "")}>
                Edit description
              </button>
              <button
                type="button"
                className="link quiet"
                disabled={reading}
                onClick={() => run(() => api.extractJob(job.id))}
              >
                <RefreshIcon /> Read again
              </button>
            </div>
          )}

          {job.requirements.length > 0 && (
            <div className="reqs">
              {must.length > 0 && (
                <>
                  <div className="req-head">Must have · {must.length}</div>
                  <ul className="req-list">{must.map(chip)}</ul>
                </>
              )}
              {nice.length > 0 && (
                <>
                  <div className="req-head">Nice to have · {nice.length}</div>
                  <ul className="req-list">{nice.map(chip)}</ul>
                </>
              )}
            </div>
          )}

          {job.raw_text && (
            <div className="req-add">
              <input
                value={adding}
                maxLength={200}
                placeholder="Add a requirement it missed"
                onChange={(e) => setAdding(e.target.value)}
                onKeyDown={async (e) => {
                  if (e.key === "Enter" && adding.trim()) {
                    e.preventDefault();
                    if (await run(() => api.addRequirement(job.id, adding.trim(), addImportance))) setAdding("");
                  }
                }}
              />
              <select value={addImportance} onChange={(e) => setAddImportance(e.target.value as Importance)}>
                <option value="must">Must</option>
                <option value="nice">Nice</option>
              </select>
              <button
                type="button"
                disabled={!adding.trim()}
                onClick={async () => {
                  if (await run(() => api.addRequirement(job.id, adding.trim(), addImportance))) setAdding("");
                }}
              >
                <PlusIcon />
                Add
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
