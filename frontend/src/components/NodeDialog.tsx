import { useState } from "react";
import { api } from "../api";
import { CloseIcon, SettingsIcon, SparkIcon } from "./Icons";
import Segmented from "./Segmented";

export interface NodeFields {
  name: string;
  description: string;
  isGroup: boolean;
  /** A tool you can point to ("Docker"), not a concept ("Feature engineering"). */
  isTool: boolean;
}

interface Props {
  title: string;
  initial: NodeFields;
  /** Adding: the user picks a skill or a group. */
  pickKind: boolean;
  onSave: (fields: NodeFields) => void;
  /** Editing: the remove button; returns false when the user cancelled. */
  onRemove?: () => boolean;
  onClose: () => void;
  /** Where it sits, and the node itself when editing: the AI writes the description from them. */
  parentId: number | null;
  skillId: number | null;
  onOpenAI: () => void;
}

/** Adds a skill or group to the tree, or renames and describes one. */
export default function NodeDialog({ title, initial, pickKind, onSave, onRemove, onClose, parentId, skillId, onOpenAI }: Props) {
  const [fields, setFields] = useState(initial);
  const set = (patch: Partial<NodeFields>) => setFields({ ...fields, ...patch });
  const [writing, setWriting] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);

  const write = async () => {
    setWriteError(null);
    setWriting(true);
    try {
      if ((await api.getAISettings()).provider === "none") return onOpenAI();
      const { description } = await api.describeSkill({ name: fields.name, is_group: fields.isGroup, parent_id: parentId, skill_id: skillId });
      setFields((f) => ({ ...f, description }));
    } catch (e) {
      setWriteError((e as Error).message);
    } finally {
      setWriting(false);
    }
  };
  return (
    <div className="edit-pop-overlay" onMouseDown={onClose}>
      <form
        className="edit-pop"
        role="dialog"
        aria-labelledby="edit-pop-title"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          if (fields.name.trim()) onSave(fields);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            onClose();
          }
        }}
      >
        <div className="modal-head">
          <h2 id="edit-pop-title">{title}</h2>
          <button type="button" className="icon" aria-label="Close" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>
        {(pickKind || !initial.isGroup) && (
          <Segmented
            ariaLabel="Kind"
            value={fields.isGroup ? "group" : fields.isTool ? "tool" : "concept"}
            onChange={(v) => set({ isGroup: v === "group", isTool: v === "tool" })}
            options={[
              { value: "concept", label: "Concept" },
              { value: "tool", label: "Tool" },
              ...(pickKind ? [{ value: "group", label: "Group" }] : []),
            ]}
          />
        )}
        <p className="muted small-note">
          {fields.isGroup
            ? "A group only organizes the tree, like Cloud. Postings are counted on the skills in it."
            : fields.isTool
              ? "A tool is something you can point to, like Docker or PyTorch. Put it under the concept it is used for."
              : "A concept is a kind of work or knowledge, like Feature engineering. Concepts and tools go under it."}
        </p>
        <label>
          Name
          <input autoFocus value={fields.name} maxLength={200} onChange={(e) => set({ name: e.target.value })} />
        </label>
        <div className="field">
          <div className="desc-head">
            <label htmlFor="node-description">Description</label>
            <span className="spacer" />
            <button type="button" onClick={write} disabled={!fields.name.trim() || writing} title="Write it with the AI model in the AI settings">
              {writing ? <span className="spinner tiny dark" /> : <SparkIcon />}
              {writing ? "Writing…" : "Write with AI"}
            </button>
            <button type="button" className="icon" title="AI settings: models, keys" aria-label="AI settings" onClick={onOpenAI}>
              <SettingsIcon />
            </button>
          </div>
          <textarea
            id="node-description"
            rows={5}
            value={fields.description}
            maxLength={2000}
            disabled={writing}
            placeholder={fields.isGroup ? "What this group is for" : "What it means"}
            onChange={(e) => set({ description: e.target.value })}
          />
        </div>
        {writeError && <div className="error">{writeError}</div>}
        <div className="row">
          {onRemove && (
            <button type="button" className="danger" onClick={() => onRemove() && onClose()}>
              Remove {initial.isGroup ? "group" : "skill"}
            </button>
          )}
          <span className="spacer" />
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={!fields.name.trim()}>
            {pickKind ? "Add" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
