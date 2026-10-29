import { useState } from "react";
import type { CompanyInput } from "../types";
import { useClosing } from "../useClosing";
import FavoriteButton from "./FavoriteButton";
import OrgFields, { emptyOrg } from "./OrgFields";

interface Props {
  onCancel: () => void;
  onSubmit: (input: CompanyInput & { watching: boolean }) => Promise<void>;
}

export default function OrgForm({ onCancel, onSubmit }: Props) {
  const [input, setInput] = useState(emptyOrg);
  const [favorite, setFavorite] = useState(true);
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
            await onSubmit({ ...input, watching: favorite });
          } catch (err) {
            setError((err as Error).message);
            setBusy(false);
          }
        }}
      >
        <div className="modal-head">
          <h2>Add organization</h2>
          <FavoriteButton name={input.name.trim() || "it"} favorite={favorite} onToggle={() => setFavorite(!favorite)} />
        </div>
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
