import { useState } from "react";
import { STATUSES, STATUS_LABELS, type Status } from "../types";
import { useClosing } from "../useClosing";
import JobFields, { emptyInput } from "./JobFields";

interface Props {
  onCancel: () => void;
  onSubmit: (input: ReturnType<typeof emptyInput> & { status: Status }) => Promise<void>;
}

export default function JobForm({ onCancel, onSubmit }: Props) {
  const [input, setInput] = useState(emptyInput);
  const [status, setStatus] = useState<Status>("saved");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [closing, close] = useClosing(onCancel);

  return (
    <div className={`overlay ${closing ? "closing" : ""}`} onMouseDown={close}>
      <form
        className="modal"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && close()}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await onSubmit({ ...input, status });
          } catch (err) {
            setError((err as Error).message);
            setBusy(false);
          }
        }}
      >
        <h2>Add job</h2>
        <JobFields value={input} onChange={setInput} autoFocus />
        <label className="inline">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
            {STATUSES.filter((s) => s !== "inbox").map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? <span className="spinner small" /> : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
