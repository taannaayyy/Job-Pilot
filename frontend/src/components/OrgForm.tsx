import { useState } from "react";
import type { CompanyInput } from "../types";
import { useClosing } from "../useClosing";
import OrgFields, { emptyOrg } from "./OrgFields";

interface Props {
  onCancel: () => void;
  onSubmit: (input: CompanyInput) => Promise<void>;
}

export default function OrgForm({ onCancel, onSubmit }: Props) {
  const [input, setInput] = useState(emptyOrg);
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
            await onSubmit(input);
          } catch (err) {
            setError((err as Error).message);
            setBusy(false);
          }
        }}
      >
        <h2>Add to watchlist</h2>
        <p className="modal-hint">
          Companies, startups, research centers, universities: anywhere you would like to work. If you already track
          jobs there, they are linked automatically.
        </p>
        <OrgFields value={input} onChange={setInput} autoFocus />
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? <span className="spinner small" /> : "Add"}
          </button>
        </div>
      </form>
    </div>
  );
}
