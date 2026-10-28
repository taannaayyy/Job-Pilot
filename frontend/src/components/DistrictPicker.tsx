import { useEffect, useMemo, useRef, useState } from "react";
import { DISTRICTS, SIDE_LABELS, SIDE_SHORT, fold, type Side } from "../locations";
import { CheckIcon } from "./Icons";

export interface DistrictValue {
  side: Side | null;
  district: string | null;
}

type Option =
  | { kind: "any"; label: string }
  | { kind: "side"; side: Side; label: string }
  | { kind: "district"; side: Side; district: string; label: string };

const SIDES = Object.keys(DISTRICTS) as Side[];

function isSelected(o: Option, v: DistrictValue) {
  if (o.kind === "any") return !v.side && !v.district;
  if (o.kind === "side") return v.side === o.side && !v.district;
  return v.district === o.district;
}

function triggerLabel(v: DistrictValue) {
  if (v.district) return v.district;
  if (v.side) return SIDE_LABELS[v.side];
  return "Any district";
}

/**
 * District picker with a fixed-height, scrollable list grouped by side. Replaces a native
 * select, whose macOS pop-up menu grows toward full screen height with 39 entries.
 */
export default function DistrictPicker({
  value,
  onChange,
}: {
  value: DistrictValue;
  onChange: (value: DistrictValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [upward, setUpward] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  // Groups shown for the current search, and the flat list of choices used for arrow keys.
  const { groups, flat } = useMemo(() => {
    const q = fold(query.trim());
    const match = (text: string) => !q || fold(text).includes(q);
    const groups = SIDES.map((side) => {
      const sideOption: Option = { kind: "side", side, label: `All of ${SIDE_LABELS[side]}` };
      const districts: Option[] = DISTRICTS[side]
        .filter(match)
        .map((district) => ({ kind: "district", side, district, label: district }));
      const showSide = match(SIDE_LABELS[side]) || match(SIDE_SHORT[side]) || !q;
      return { side, options: showSide ? [sideOption, ...districts] : districts };
    }).filter((g) => g.options.length > 0);
    const any: Option[] = q ? [] : [{ kind: "any", label: "Any district" }];
    return { groups, any, flat: [...any, ...groups.flatMap((g) => g.options)] };
  }, [query]);

  const openMenu = () => {
    const rect = trigger.current?.getBoundingClientRect();
    // Open upward when there is not enough room below (e.g. near the bottom of the form).
    setUpward(!!rect && window.innerHeight - rect.bottom < 330 && rect.top > window.innerHeight - rect.bottom);
    setQuery("");
    setOpen(true);
  };

  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };

  const choose = (o: Option) => {
    if (o.kind === "any") onChange({ side: null, district: null });
    else if (o.kind === "side") onChange({ side: o.side, district: null });
    else onChange({ side: o.side, district: o.district });
    close();
  };

  // Start on the current choice, and keep the highlighted row scrolled into view.
  useEffect(() => {
    if (!open) return;
    const i = flat.findIndex((o) => isSelected(o, value));
    setActive(i >= 0 && !query ? i : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, query]);

  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) close(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openMenu();
      }
      return;
    }
    if (e.key === "Escape") {
      // Close only the menu, not the form or panel around it.
      e.preventDefault();
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(flat.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flat[active]) choose(flat[active]);
    } else if (e.key === "Tab") {
      close(false);
    }
  };

  let index = -1;
  const row = (o: Option) => {
    index += 1;
    const i = index;
    const selected = isSelected(o, value);
    return (
      <div
        key={o.kind === "district" ? o.district : `${o.kind}-${"side" in o ? o.side : ""}`}
        role="option"
        aria-selected={selected}
        data-index={i}
        className={`picker-option ${o.kind} ${i === active ? "active" : ""}`}
        onMouseEnter={() => setActive(i)}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => choose(o)}
      >
        <span>{o.label}</span>
        {selected && <CheckIcon />}
      </div>
    );
  };

  return (
    <div className="picker" ref={root} onKeyDown={onKeyDown}>
      <button
        ref={trigger}
        type="button"
        className={`picker-trigger no-ripple ${open ? "open" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close() : openMenu())}
      >
        <span className="picker-value">
          {triggerLabel(value)}
          {value.district && value.side && <span className="picker-tag">{SIDE_SHORT[value.side]}</span>}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className={`picker-pop ${upward ? "upward" : ""}`}>
          <input
            autoFocus
            className="picker-search"
            placeholder="Search districts"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="picker-list" role="listbox" ref={list}>
            {!query && row({ kind: "any", label: "Any district" })}
            {groups.map((g) => (
              <div key={g.side} role="group" aria-label={SIDE_LABELS[g.side]}>
                <div className="picker-group">{SIDE_LABELS[g.side]}</div>
                {g.options.map(row)}
              </div>
            ))}
            {flat.length === 0 && <div className="picker-empty">No district matches “{query}”</div>}
          </div>
        </div>
      )}
    </div>
  );
}
