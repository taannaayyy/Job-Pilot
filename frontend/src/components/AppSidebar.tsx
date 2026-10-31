import type { ReactNode } from "react";
import type { Theme } from "../theme";
import { AutoIcon, BoardIcon, BriefcaseIcon, BuildingIcon, MoonIcon, PuzzleIcon, SearchIcon, SunIcon, TargetIcon } from "./Icons";
import Segmented from "./Segmented";

export type Page = "jobs" | "watchlist" | "skills";

interface Props {
  page: Page;
  onPage: (page: Page) => void;
  counts: Record<Page, number>;
  /** Where the open page puts its own lists (statuses, types, areas), under its name. */
  slotRef: (el: HTMLDivElement | null) => void;
  /** Focuses the open page's search field (also Cmd+K). */
  onSearch: () => void;
  onExtension: () => void;
  theme: Theme;
  onTheme: (theme: Theme) => void;
}

const PAGES: { page: Page; label: string; icon: ReactNode }[] = [
  { page: "jobs", label: "Jobs", icon: <BriefcaseIcon /> },
  { page: "watchlist", label: "Companies", icon: <BuildingIcon /> },
  { page: "skills", label: "Skill Gap", icon: <TargetIcon /> },
];

/** The app's one sidebar: the pages, the open page's lists folded under it, and search, the extension and the theme at the foot. */
export default function AppSidebar({ page, onPage, counts, slotRef, onSearch, onExtension, theme, onTheme }: Props) {
  return (
    <aside className="app-side">
      <div className="app-brand">
        <span className="logo" aria-hidden>
          <BoardIcon />
        </span>
        <h1>Job Pilot</h1>
      </div>
      <nav className="side-nav" aria-label="Pages">
        {PAGES.map((p) => (
          <div key={p.page}>
            <button type="button" className={`side-item page${p.page === page ? " on" : ""}`} aria-current={p.page === page ? "page" : undefined} onClick={() => onPage(p.page)}>
              {p.icon}
              <span className="side-label">{p.label}</span>
              <span className="side-count">{counts[p.page]}</span>
            </button>
            {p.page === page && <div className="side-sub" ref={slotRef} />}
          </div>
        ))}
      </nav>
      <div className="side-foot">
        <button type="button" className="side-item" onClick={onSearch} title="Search this page">
          <SearchIcon />
          <span className="side-label">Search</span>
          <kbd>⌘K</kbd>
        </button>
        <button type="button" className="side-item" onClick={onExtension} title="Save jobs from LinkedIn with the Chrome extension">
          <PuzzleIcon />
          <span className="side-label">Extension</span>
        </button>
        <Segmented
          ariaLabel="Theme"
          iconOnly
          value={theme}
          onChange={onTheme}
          options={[
            { value: "system", label: "Match system", icon: <AutoIcon /> },
            { value: "light", label: "Light", icon: <SunIcon /> },
            { value: "dark", label: "Night", icon: <MoonIcon /> },
          ]}
        />
      </div>
    </aside>
  );
}
