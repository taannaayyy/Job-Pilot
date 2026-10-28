"""Desktop entry point: runs the backend in a thread and shows the UI in a native window.

The app runs only while its window is open: closing the window stops the backend
and quits. Nothing starts at login.
"""

import json
import socket
import threading
import time

import uvicorn
import webview
from PyObjCTools import AppHelper

from jobpilot import config
from jobpilot.main import WEB_DIR, create_app


def _pick_port(preferred: int) -> int:
    """Use the usual port when it is free, otherwise any free port, so another app on 8765 doesn't block us."""
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("no free port")


def _wait_until_up(server: uvicorn.Server, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("backend did not start")
        time.sleep(0.05)


def _add_standard_menus() -> None:
    """pywebview's menu bar has no Window menu and no Undo/Redo, so Cmd+M, Cmd+W and Cmd+Z do nothing.

    Runs on the main thread after pywebview has installed its menu bar.
    """
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    main_menu = app.mainMenu()

    # pywebview leaves the top-level items untitled, so look menus up by their submenu title.
    edit = next(
        (i.submenu() for i in main_menu.itemArray() if i.submenu() is not None and i.submenu().title() == "Edit"),
        None,
    )
    if edit is not None:
        edit.insertItemWithTitle_action_keyEquivalent_atIndex_("Undo", "undo:", "z", 0)
        redo = edit.insertItemWithTitle_action_keyEquivalent_atIndex_("Redo", "redo:", "z", 1)
        redo.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift)
        edit.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 2)

    window_menu = AppKit.NSMenu.alloc().initWithTitle_("Window")
    window_menu.addItemWithTitle_action_keyEquivalent_("Minimize", "performMiniaturize:", "m")
    window_menu.addItemWithTitle_action_keyEquivalent_("Zoom", "performZoom:", "")
    window_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    window_menu.addItemWithTitle_action_keyEquivalent_("Close", "performClose:", "w")
    window_item = AppKit.NSMenuItem.alloc().init()
    window_item.setSubmenu_(window_menu)
    main_menu.addItem_(window_item)
    # Lets macOS add the open-window list and "Bring All to Front".
    app.setWindowsMenu_(window_menu)


# Renamed from theme.json, which older builds wrote on every launch.
THEME_FILE = config.APP_SUPPORT_DIR / "ui-theme.json"
# Window background before the page paints; matches --bg in styles.css.
BACKGROUND = {"light": "#F5F6F8", "dark": "#0F1115"}


def _load_theme() -> str:
    try:
        return json.loads(THEME_FILE.read_text())["mode"]
    except (OSError, ValueError, KeyError):
        return "dark"  # night mode until the user picks a theme


def _effective_theme(mode: str) -> str:
    if mode in BACKGROUND:
        return mode
    import Foundation

    style = Foundation.NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
    return "dark" if style == "Dark" else "light"


def _apply_appearance(mode: str) -> None:
    import AppKit

    names = {"light": AppKit.NSAppearanceNameAqua, "dark": AppKit.NSAppearanceNameDarkAqua}
    appearance = AppKit.NSAppearance.appearanceNamed_(names[mode]) if mode in names else None
    AppKit.NSApplication.sharedApplication().setAppearance_(appearance)  # None follows the system


class _Api:
    """Exposed to the page as window.pywebview.api."""

    def set_appearance(self, mode: str) -> None:
        """Match the native title bar to the UI theme ("light", "dark" or "system") and remember it."""
        if mode not in ("light", "dark", "system"):
            return
        AppHelper.callAfter(_apply_appearance, mode)
        try:
            THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_FILE.write_text(json.dumps({"mode": mode}))
        except OSError:
            pass  # only affects the window color on the next launch


# Smallest size at which the header, filters, table and all eight board columns (with
# their names on one line) still fit.
MIN_SIZE = (1200, 640)


def _initial_size() -> tuple[int, int]:
    """Most of the screen the window opens on (so side panels fit without scrolling),
    capped on very large screens and never larger than the screen itself."""
    import AppKit

    AppKit.NSApplication.sharedApplication()
    screen = AppKit.NSScreen.mainScreen()
    if screen is None:
        return 1400, 900
    area = screen.visibleFrame().size  # excludes the menu bar and the Dock
    width = min(1600, round(area.width * 0.92))
    height = min(1000, round(area.height * 0.94))
    return (
        min(max(width, MIN_SIZE[0]), round(area.width)),
        min(max(height, MIN_SIZE[1]), round(area.height)),
    )


def main() -> None:
    if not (WEB_DIR / "index.html").is_file():
        raise SystemExit("UI is not built. Run `npm run build` in frontend/ first.")

    port = _pick_port(config.api_port())
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, loop="asyncio", http="h11", log_level="warning")
    )
    backend = threading.Thread(target=server.run, daemon=True)
    backend.start()
    _wait_until_up(server)

    theme = _load_theme()
    width, height = _initial_size()
    window = webview.create_window(
        "Job Pilot",
        f"http://127.0.0.1:{port}/",
        width=width,
        height=height,
        min_size=MIN_SIZE,
        js_api=_Api(),
        background_color=BACKGROUND[_effective_theme(theme)],
    )
    # Event handlers run off the main thread; menus must be changed on it.
    def on_shown() -> None:
        AppHelper.callAfter(_add_standard_menus)
        AppHelper.callAfter(_apply_appearance, theme)

    window.events.shown += on_shown
    # private_mode=False keeps WebKit storage (e.g. the remembered Board/Table view) between launches.
    # Returns when the window is closed; then the backend is stopped and the app exits.
    webview.start(private_mode=False)
    server.should_exit = True
    backend.join(timeout=5)


if __name__ == "__main__":
    main()
