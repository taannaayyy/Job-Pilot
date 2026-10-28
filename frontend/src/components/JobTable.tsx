import { useMemo, useState } from "react";
import { fmtDate } from "../format";
import { STATUSES, WORK_MODE_LABELS, type Job, type Status } from "../types";
import { locationLabel } from "../locations";
import CompanyLogo from "./CompanyLogo";
import StatusSelect from "./StatusSelect";

type SortKey = "company" | "title" | "status" | "date_saved" | "date_applied";

// Fixed column widths: long text is cut off with "…" instead of widening the table,
// so the layout stays the same at any window size. The last column takes the rest.
const COLUMNS: { key: SortKey | null; label: string; width?: string }[] = [
  { key: "company", label: "Company", width: "14%" },
  { key: "title", label: "Role", width: "17%" },
  { key: "status", label: "Status", width: "128px" },
  { key: null, label: "Mode", width: "80px" },
  { key: null, label: "Location", width: "12%" },
  { key: null, label: "Source", width: "8%" },
  { key: "date_saved", label: "Saved", width: "90px" },
  { key: "date_applied", label: "Applied", width: "92px" },
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
        <colgroup>
          {COLUMNS.map(({ label, width }) => (
            <col key={label} style={width ? { width } : undefined} />
          ))}
        </colgroup>
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
              <td className="strong">
                <span className="company-cell" title={job.company}>
                  <CompanyLogo name={job.company} logoUrl={job.logo_url} size={22} />
                  <span className="truncate">{job.company}</span>
                </span>
              </td>
              <td title={job.title}>{job.title}</td>
              <td>
                <StatusSelect value={job.status} onChange={(s) => onStatusChange(job.id, s)} />
              </td>
              <td>{job.work_mode ? WORK_MODE_LABELS[job.work_mode] : "—"}</td>
              <td title={locationLabel(job) ?? undefined}>{locationLabel(job) ?? "—"}</td>
              <td title={job.source ?? undefined}>{job.source || "—"}</td>
              <td className="num">{fmtDate(job.date_saved)}</td>
              <td className="num">{fmtDate(job.date_applied)}</td>
              <td className="muted" title={job.next_action ?? undefined}>
                {job.next_action || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && <p className="empty">No jobs match these filters.</p>}
    </div>
  );
}
