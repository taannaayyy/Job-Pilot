import { useCallback, useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";

// Saved only when the user picks a theme. (Renamed from "jobpilot.theme", which older builds wrote on every launch.)
export const THEME_KEY = "jobpilot.ui.theme";

declare global {
  interface Window {
    pywebview?: { api?: { set_appearance?: (mode: Theme) => Promise<void> } };
  }
}

/** Night is the default until the user picks a theme. */
function load(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "system" ? t : "dark";
  } catch {
    return "dark";
  }
}

/** Tells the desktop shell, when there is one, so the native title bar matches. */
function syncNative(theme: Theme) {
  const send = () => window.pywebview?.api?.set_appearance?.(theme);
  if (window.pywebview?.api) send();
  else window.addEventListener("pywebviewready", send, { once: true });
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(load);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // per-viewer convenience only
    }
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    // Colors animate only during a switch, not on every hover or first paint.
    root.classList.add("theme-switching");
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    const t = setTimeout(() => root.classList.remove("theme-switching"), 350);
    syncNative(theme);
    return () => clearTimeout(t);
  }, [theme]);

  return [theme, setTheme];
}
