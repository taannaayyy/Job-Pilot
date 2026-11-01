/** The system the app runs on, for the names of keys and places in the UI (shortcuts accept both ⌘ and Ctrl). */
export const IS_MAC = /Mac/.test(navigator.platform || navigator.userAgent);

/** "⌘K" on a Mac, "Ctrl+K" elsewhere. */
export const shortcut = (key: string) => (IS_MAC ? `⌘${key}` : `Ctrl+${key}`);

/** The file manager: Finder or Explorer. */
export const FILE_MANAGER = IS_MAC ? "Finder" : "Explorer";
