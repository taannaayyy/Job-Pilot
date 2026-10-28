import { useCallback, useRef, useState } from "react";

/** Plays the CSS exit animation (`.closing`) before actually unmounting. */
export function useClosing(onClose: () => void, ms = 180): [boolean, () => void] {
  const [closing, setClosing] = useState(false);
  const started = useRef(false);
  const close = useCallback(() => {
    if (started.current) return;
    started.current = true;
    setClosing(true);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(onClose, reduced ? 0 : ms);
  }, [onClose, ms]);
  return [closing, close];
}
