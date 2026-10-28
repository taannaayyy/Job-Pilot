import { useMemo, useState } from "react";
import { fmtDate } from "../format";
import { STATUSES, WORK_MODE_LABELS, type Job, type Status } from "../types";
import StatusSelect from "./StatusSelect";

type SortKey = "company" | "title" | "status" | "date_saved" | "date_applied";

const COLUMNS: { key: SortKey | null; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "title", label: "Role" },
  { key: "status", label: "Status" },
  { key: null, label: "Mode" },
  { key: null, label: "Location" },
  { key: null, label: "Source" },
  { key: "date_saved", label: "Saved" },
  { key: "date_applied", label: "Applied" },
  { key: null, label: "Next action" },
];

interface Props {
  jobs: Job[];
  onOpen: (id: number) => void;
  onStatusChange: (id: number, status: Status) => void;
}

export default function JobTable({ jobs, onOpen, onStatusChange }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "date_saved", dir: -1 });

  const sorted = useMemo(() => {
    const value = (j: Job) =>
      sort.key === "status" ? STATUSES.indexOf(j.status) : (j[sort.key] ?? "").toString().toLowerCase();
    return [...jobs].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      return va < vb ? -sort.dir : va > vb ? sort.dir : 0;
    });
  }, [jobs, sort]);

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {COLUMNS.map(({ key, label }) => (
              <th
                key={label}
                className={key ? "sortable" : undefined}
                aria-sort={key === sort.key ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                onClick={() =>
                  key && setSort((s) => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : key.startsWith("date") ? -1 : 1 }))
                }
              >
                {label}
                {key === sort.key && <span className="arrow">{sort.dir === 1 ? "▲" : "▼"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((job) => (
            <tr key={job.id} onClick={() => onOpen(job.id)}>
              <td className="strong">{job.company}</td>
              <td>{job.title}</td>
              <td>
                <StatusSelect value={job.status} onChange={(s) => onStatusChange(job.id, s)} />
              </td>
              <td>{job.work_mode ? WORK_MODE_LABELS[job.work_mode] : "—"}</td>
              <td>{job.location || "—"}</td>
              <td>{job.source || "—"}</td>
              <td className="num">{fmtDate(job.date_saved)}</td>
              <td className="num">{fmtDate(job.date_applied)}</td>
              <td className="muted">{job.next_action || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && <p className="empty">No jobs match these filters.</p>}
    </div>
  );
}
