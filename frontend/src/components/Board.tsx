import { useState } from "react";
import { fmtDate } from "../format";
import { locationLabel } from "../locations";
import CompanyLogo from "./CompanyLogo";
import { CheckIcon } from "./Icons";
import { STATUSES, STATUS_LABELS, WORK_MODE_LABELS, type Job, type Status } from "../types";

interface Props {
  jobs: Job[];
  showInbox: boolean;
  statusFilter: Status | "";
  onOpen: (id: number) => void;
  onStatusChange: (id: number, status: Status) => void;
}

export default function Board({ jobs, showInbox, statusFilter, onOpen, onStatusChange }: Props) {
  const [dragOver, setDragOver] = useState<Status | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const columns = STATUSES.filter(
    (s) => (statusFilter ? s === statusFilter : s !== "inbox" || showInbox),
  );

  return (
    <div className="board">
      {columns.map((status) => {
        const items = jobs.filter((j) => j.status === status);
        return (
          <section
            key={status}
            className={`column ${dragOver === status ? "drag-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(status);
            }}
            onDragLeave={() => setDragOver((s) => (s === status ? null : s))}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(null);
              const id = Number(e.dataTransfer.getData("text/job-id"));
              const job = jobs.find((j) => j.id === id);
              if (job && job.status !== status) onStatusChange(id, status);
            }}
          >
            <header className="column-head">
              <span className={`dot status-${status}`} />
              {STATUS_LABELS[status]}
              <span className="count">{items.length}</span>
            </header>
            <div className="cards">
              {items.length === 0 && <div className="column-empty">Drop here</div>}
              {items.map((job, i) => (
                <article
                  key={job.id}
                  className={`card status-${job.status} ${dragging === job.id ? "dragging" : ""}`}
                  style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}
                  draggable
                  tabIndex={0}
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/job-id", String(job.id));
                    e.dataTransfer.effectAllowed = "move";
                    setDragging(job.id);
                  }}
                  onDragEnd={() => setDragging(null)}
                  onClick={() => onOpen(job.id)}
                  onKeyDown={(e) => e.key === "Enter" && onOpen(job.id)}
                >
                  <div className="card-company">
                    <CompanyLogo name={job.company} logoUrl={job.logo_url} size={18} />
                    <span>{job.company}</span>
                  </div>
                  <div className="card-title">{job.title}</div>
                  <div className="card-meta">
                    {[job.work_mode && WORK_MODE_LABELS[job.work_mode], locationLabel(job)].filter(Boolean).join(" · ")}
                  </div>
                  {job.next_action && <div className="card-next">→ {job.next_action}</div>}
                  <div className="card-foot">
                    <span>
                      {job.date_applied ? `Applied ${fmtDate(job.date_applied)}` : `Saved ${fmtDate(job.date_saved)}`}
                    </span>
                    {job.status === "saved" && (
                      <button
                        className="small success"
                        onClick={(e) => {
                          e.stopPropagation();
                          onStatusChange(job.id, "applied");
                        }}
                      >
                        <CheckIcon />
                        Mark applied
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
