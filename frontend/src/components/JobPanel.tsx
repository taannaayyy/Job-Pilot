import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { fmtDateTime } from "../format";
import { STATUS_LABELS, type Job, type JobDetail, type JobInput, type RoleGroup, type Status } from "../types";
import { useClosing } from "../useClosing";
import { CheckIcon, CloseIcon, ExternalIcon } from "./Icons";
import FavoriteButton from "./FavoriteButton";
import CompanyLogo from "./CompanyLogo";
import JobDescription from "./JobDescription";
import JobFields from "./JobFields";
import JobSkills from "./JobSkills";
import StatusSelect from "./StatusSelect";

interface Props {
  jobId: number;
  onClose: () => void;
  onSaved: (job: Job) => void;
  onDeleted: (id: number) => void;
  /** The job's company was added to or removed from favorites. */
  onWatchChanged: () => void;
  groups: RoleGroup[];
  onGroupsChanged: () => void;
}

function toInput(job: JobDetail): JobInput {
  const { company, company_website, title, url, city, side, district, job_type, work_mode, source, next_action, notes } = job;
  return { company, company_website, title, url, city, side, district, job_type, work_mode, source, next_action, notes };
}

export default function JobPanel({ jobId, onClose, onSaved, onDeleted, onWatchChanged, groups, onGroupsChanged }: Props) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [input, setInput] = useState<JobInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [closing, close] = useClosing(onClose, 220);
  // Words selected in the description, on their way to the skill search.
  const [words, setWords] = useState<{ text: string } | null>(null);

  useEffect(() => {
    api
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setInput(toInput(j));
      })
      // Deleted somewhere else, or still listed on a page that hadn't caught up: drop it everywhere.
      .catch((e) => (e.message === "Job not found" ? onDeleted(jobId) : setError(e.message)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const dirty = job && input && JSON.stringify(toInput(job)) !== JSON.stringify(input);

  const apply = (updated: JobDetail, resetInput: boolean) => {
    setJob(updated);
    if (resetInput) setInput(toInput(updated));
    onSaved(updated);
    setError(null);
  };

  // Skill Gap changes save right away and leave the fields being edited alone.
  const applySkills = useCallback(
    (updated: JobDetail) => {
      setJob(updated);
      onSaved(updated);
    },
    [onSaved],
  );

  const changeStatus = async (status: Status) => {
    try {
      apply(await api.updateJob(jobId, { status }), false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className={`overlay ${closing ? "closing" : ""}`} onMouseDown={close}>
      <aside className="panel job-pop" role="dialog" aria-label="Job" onMouseDown={(e) => e.stopPropagation()}>
        {!job || !input ? (
          <div className="empty">{error ?? <span className="spinner" aria-label="Loading" />}</div>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                apply(await api.updateJob(jobId, input), true);
                setSaved(true);
                setTimeout(() => setSaved(false), 1600);
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <header className="panel-head">
              <CompanyLogo name={job.company} logoUrl={job.logo_url} size={44} />
              <div className="panel-title">
                <div className="card-company">{job.company}</div>
                <h2>{job.title}</h2>
                {(job.url || job.company_website) && (
                  <div className="external-links">
                    {job.url && (
                      <a className="external" href={job.url} target="_blank" rel="noreferrer">
                        Open posting <ExternalIcon />
                      </a>
                    )}
                    {job.company_website && (
                      <a className="external" href={job.company_website} target="_blank" rel="noreferrer">
                        Company website <ExternalIcon />
                      </a>
                    )}
                  </div>
                )}
              </div>
              <FavoriteButton
                name={job.company}
                favorite={job.company_watching}
                onToggle={async () => {
                  try {
                    await api.updateCompany(job.company_id, { watching: !job.company_watching });
                    apply(await api.getJob(jobId), false);
                    onWatchChanged();
                  } catch (err) {
                    setError((err as Error).message);
                  }
                }}
              />
              <button type="button" className="icon" aria-label="Close" onClick={close}>
                <CloseIcon />
              </button>
            </header>

            <div className="panel-status">
              <StatusSelect value={job.status} onChange={changeStatus} />
              {job.status === "saved" && (
                <button type="button" className="success" onClick={() => changeStatus("applied")}>
                  <CheckIcon />
                  Mark applied
                </button>
              )}
            </div>

            {error && <div className="error">{error}</div>}

            {/* The job's own fields, out of the way of reading and adding skills. */}
            <details className="job-details">
              <summary>Details · company, link, location, notes, history</summary>
              <JobFields value={input} onChange={setInput} />
              <div className="actions">
                <button
                  type="button"
                  className="danger"
                  onClick={async () => {
                    if (!confirm(`Delete ${job.title} at ${job.company}?`)) return;
                    try {
                      await api.deleteJob(jobId);
                      onDeleted(jobId);
                    } catch (err) {
                      setError((err as Error).message);
                    }
                  }}
                >
                  Delete
                </button>
                <span className="spacer" />
                <button type="button" disabled={!dirty} onClick={() => setInput(toInput(job))}>
                  Revert
                </button>
                <button type="submit" className={`primary ${saved ? "saved" : ""}`} disabled={(!dirty || busy) && !saved}>
                  {busy ? <span className="spinner small" /> : saved ? <><CheckIcon /> Saved</> : "Save changes"}
                </button>
              </div>

              <h3>Status history</h3>
              <ol className="history">
                {[...job.events].reverse().map((ev) => (
                  <li key={ev.id}>
                    <span className={`dot status-${ev.to_status}`} />
                    <span>
                      {ev.from_status ? `${STATUS_LABELS[ev.from_status]} → ` : "Added as "}
                      <strong>{STATUS_LABELS[ev.to_status]}</strong>
                    </span>
                    <time className="muted">{fmtDateTime(ev.timestamp)}</time>
                  </li>
                ))}
              </ol>
            </details>

            {/* Read on the left, add the skills it asks for on the right. */}
            <div className="job-pop-body">
              <div className="job-pop-col">
                <JobDescription
                  text={job.raw_text}
                  requirements={job.requirements}
                  onSave={async (text) => {
                    try {
                      applySkills(await api.updateJob(jobId, { raw_text: text }));
                      return true;
                    } catch (err) {
                      setError((err as Error).message);
                      return false;
                    }
                  }}
                  onAddWords={job.target_group_id !== null ? (text) => setWords({ text }) : null}
                  onRemove={async (ids) => {
                    try {
                      let updated = job;
                      for (const id of ids) updated = await api.removeRequirement(jobId, id);
                      applySkills(updated);
                    } catch (err) {
                      setError((err as Error).message);
                    }
                  }}
                />
              </div>

              <div className="job-pop-col">
                <JobSkills
                  job={job}
                  groups={groups}
                  onChange={applySkills}
                  onGroupsChanged={onGroupsChanged}
                  onError={setError}
                  words={words}
                  onWordsUsed={() => setWords(null)}
                />
              </div>
            </div>
          </form>
        )}
      </aside>
    </div>
  );
}
