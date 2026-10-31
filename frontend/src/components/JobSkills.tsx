import { useEffect, useState } from "react";
import { api, type JobChanges } from "../api";
import type { Importance, JobDetail, Requirement, RoleGroup, SkillRow } from "../types";
import { CloseIcon } from "./Icons";
import Segmented from "./Segmented";
import SkillSearch, { type SearchPick } from "./SkillSearch";

interface Props {
  job: JobDetail;
  groups: RoleGroup[];
  onChange: (job: JobDetail) => void;
  onGroupsChanged: () => void;
  onError: (message: string | null) => void;
  /** Words selected in the description to add as a skill: searched for, and kept with the skill. */
  words: { text: string } | null;
  onWordsUsed: () => void;
}

const NEW_GROUP = "new";

/** The job's part in Skill Gap: which role group it is a target of, and the skills it asks for,
 *  connected by hand (here, or from a skill on the Skill Gap page). */
export default function JobSkills({ job, groups, onChange, onGroupsChanged, onError, words, onWordsUsed }: Props) {
  const [newGroup, setNewGroup] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [addImportance, setAddImportance] = useState<Importance>("must");
  // The whole tree, to search when adding a skill.
  const [tree, setTree] = useState<SkillRow[]>([]);
  const loadTree = () => api.listSkills().then(setTree, () => {});
  useEffect(() => {
    loadTree();
  }, []);

  // Words selected in the description: searched for at once, the user picks the skill they name.
  useEffect(() => {
    if (words) setQuery(words.text);
  }, [words]);

  const add = async (pick: SearchPick) => {
    if ("top" in pick) return;
    const name = "skill" in pick ? pick.skill.name : pick.name;
    const evidence = words?.text ?? "";
    if (await run(() => api.addRequirement(job.id, name, addImportance, evidence))) {
      setQuery("");
      onWordsUsed();
      if (!("skill" in pick)) loadTree(); // a new one, in Unsorted
    }
  };

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
          <div className="req-add">
            <SkillSearch
              skills={tree}
              query={query}
              onQuery={setQuery}
              onPick={add}
              onCancel={() => {
                setQuery("");
                onWordsUsed();
              }}
              placeholder="Add a skill it asks for: search your tree"
              mode="skill"
              autoFocus={words !== null}
              key={words ? `w${words.text}` : "search"}
            />
            <Segmented
              ariaLabel="Must or nice to have"
              value={addImportance}
              onChange={setAddImportance}
              options={[
                { value: "must", label: "Must" },
                { value: "nice", label: "Nice" },
              ]}
            />
          </div>
          {words && <p className="muted small-note">Pick the skill “{words.text}” names, or add it as a new one.</p>}

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
        </>
      )}
    </section>
  );
}
