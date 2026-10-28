import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtAgo, fmtDate } from "../format";
import { linkedinJobsUrl } from "../orgs";
import { useClosing } from "../useClosing";
import { ORG_KIND_LABELS, STATUS_LABELS, type Company, type CompanyInput, type Job } from "../types";
import CompanyLogo from "./CompanyLogo";
import HiringButtons from "./HiringButtons";
import { CheckIcon, CloseIcon, ExternalIcon, PlusIcon } from "./Icons";
import OrgFields from "./OrgFields";

interface Props {
  org: Company;
  jobs: Job[];
  onClose: () => void;
  onSaved: (org: Company) => void;
  onRemoved: (id: number) => void;
  onOpenJob: (id: number) => void;
  onAddJob: (org: Company) => void;
}

function toInput(o: Company): CompanyInput {
  const { name, kind, website, careers_url, linkedin_url, notes } = o;
  return { name, kind, website, careers_url, linkedin_url, notes };
}

export default function OrgPanel({ org, jobs, onClose, onSaved, onRemoved, onOpenJob, onAddJob }: Props) {
  const [input, setInput] = useState(() => toInput(org));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [closing, close] = useClosing(onClose, 220);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const dirty = JSON.stringify(toInput(org)) !== JSON.stringify(input);

  const update = async (body: Parameters<typeof api.updateCompany>[1], resetInput = false) => {
    try {
      const next = await api.updateCompany(org.id, body);
      onSaved(next);
      if (resetInput) setInput(toInput(next));
      setError(null);
      return next;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  };

  return (
    <div className={`overlay side ${closing ? "closing" : ""}`} onMouseDown={close}>
      <aside className="panel" onMouseDown={(e) => e.stopPropagation()}>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            if (await update(input, true)) {
              setSaved(true);
              setTimeout(() => setSaved(false), 1600);
            }
            setBusy(false);
          }}
        >
          <header className="panel-head">
            <CompanyLogo name={org.name} logoUrl={org.logo_url} size={44} />
            <div className="panel-title">
              <div className="card-company">{ORG_KIND_LABELS[org.kind]}</div>
              <h2>{org.name}</h2>
              <div className="external-links">
                {org.careers_url && (
                  <a className="external" href={org.careers_url} target="_blank" rel="noreferrer">
                    Careers page <ExternalIcon />
                  </a>
                )}
                <a className="external" href={linkedinJobsUrl(org)} target="_blank" rel="noreferrer">
                  LinkedIn jobs <ExternalIcon />
                </a>
                {org.website && (
                  <a className="external" href={org.website} target="_blank" rel="noreferrer">
                    Website <ExternalIcon />
                  </a>
                )}
              </div>
            </div>
            <button type="button" className="icon" aria-label="Close" onClick={close}>
              <CloseIcon />
            </button>
          </header>

          <div className="panel-status">
            <HiringButtons value={org.openings} onChange={(openings) => update({ openings })} />
            <span className="muted check-note">
              {org.last_checked_at ? `Checked ${fmtAgo(org.last_checked_at)}` : "Not checked yet"}
            </span>
          </div>

          <OrgFields value={input} onChange={setInput} />
          {error && <div className="error">{error}</div>}

          <div className="actions">
            <button
              type="button"
              className="danger"
              onClick={async () => {
                if (jobs.length === 0) {
                  if (!confirm(`Delete ${org.name}? Its notes and links are removed too.`)) return;
                  try {
                    await api.deleteCompany(org.id);
                    onRemoved(org.id);
                  } catch (err) {
                    setError((err as Error).message);
                  }
                } else if (await update({ watching: false })) {
                  onRemoved(org.id);
                }
              }}
              title={jobs.length ? "Its tracked jobs stay as they are" : undefined}
            >
              {jobs.length ? "Remove from watchlist" : "Delete"}
            </button>
            <span className="spacer" />
            <button type="button" disabled={!dirty} onClick={() => setInput(toInput(org))}>
              Revert
            </button>
            <button type="submit" className={`primary ${saved ? "saved" : ""}`} disabled={(!dirty || busy) && !saved}>
              {busy ? <span className="spinner small" /> : saved ? <><CheckIcon /> Saved</> : "Save changes"}
            </button>
          </div>

          <div className="panel-section-head">
            <h3>Tracked jobs here</h3>
            <button type="button" className="small" onClick={() => onAddJob(org)}>
              <PlusIcon /> Add job
            </button>
          </div>
          {jobs.length === 0 ? (
            <p className="muted panel-empty">No jobs tracked here yet.</p>
          ) : (
            <ul className="org-jobs">
              {jobs.map((j) => (
                <li key={j.id}>
                  <button type="button" className={`org-job status-${j.status}`} onClick={() => onOpenJob(j.id)}>
                    <span className="dot" />
                    <span className="org-job-title">{j.title}</span>
                    <span className="muted">{STATUS_LABELS[j.status]}</span>
                    <span className="muted">{fmtDate(j.date_saved)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>
      </aside>
    </div>
  );
}
