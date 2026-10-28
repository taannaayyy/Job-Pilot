import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";

const KEY = "jobpilot.theme";

declare global {
  interface Window {
    pywebview?: { api?: { set_appearance?: (mode: Theme) => Promise<void> } };
  }
}

function load(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

/** Tells the desktop shell, when there is one, so the native title bar matches. */
function syncNative(theme: Theme) {
  const send = () => window.pywebview?.api?.set_appearance?.(theme);
  if (window.pywebview?.api) send();
  else window.addEventListener("pywebviewready", send, { once: true });
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(load);

  useEffect(() => {
    const root = document.documentElement;
    // Colors animate only during a switch, not on every hover or first paint.
    root.classList.add("theme-switching");
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    const t = setTimeout(() => root.classList.remove("theme-switching"), 350);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      // per-viewer convenience only
    }
    syncNative(theme);
    return () => clearTimeout(t);
  }, [theme]);

  return [theme, setTheme];
}
