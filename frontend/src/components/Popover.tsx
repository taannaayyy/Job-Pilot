import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  /** What the button shows. */
  label: ReactNode;
  /** Extra classes for the button ("icon", "active"...). */
  className?: string;
  title?: string;
  /** Opens to the left of the button's right edge instead of from its left edge. */
  alignRight?: boolean;
  /** The menu; close() shuts it, for items that act once. */
  children: (close: () => void) => ReactNode;
}

/** A button that opens a small menu under it; a click outside or Escape closes it. */
export default function Popover({ label, className = "", title, alignRight, children }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  return (
    <div className="popover" ref={ref}>
      <button type="button" className={`${className}${open ? " open" : ""}`} title={title} aria-expanded={open} onClick={() => setOpen(!open)}>
        {label}
      </button>
      {open && (
        <div className={`picker-pop menu-pop${alignRight ? " right" : ""}`} role="menu">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
