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

from jobpilot import config, system
from jobpilot.main import WEB_DIR, create_app


def _free_port(port: int) -> int | None:
    """The port if it can be bound (0 picks any free one), otherwise None."""
    with socket.socket() as s:
        # Like uvicorn: connections from a just-closed app linger on the port (TIME_WAIT)
        # but don't stop a new server from listening there.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return None
        return s.getsockname()[1]


def _choose_port(preferred: int) -> tuple[int, str | None]:
    """The extension's port when free. Otherwise, if the user agrees, any free port, plus the
    name of the program in the way (the UI shows it in a banner)."""
    # A Job Pilot that was just quit (e.g. to update it) can take a moment to let go of the port.
    deadline = time.monotonic() + 3
    while (port := _free_port(preferred)) is None and time.monotonic() < deadline:
        time.sleep(0.2)
    if port is not None:
        return port, None
    holder = system.port_holder(preferred)
    if not system.ask_open_anyway(preferred, holder):
        raise SystemExit(0)
    port = _free_port(0)
    if port is None:
        raise RuntimeError("no free port")
    return port, holder or "another program"


def _wait_until_up(server: uvicorn.Server, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("backend did not start")
        time.sleep(0.05)


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
    return "dark" if system.system_is_dark() else "light"


class _Api:
    """Exposed to the page as window.pywebview.api."""

    def set_appearance(self, mode: str) -> None:
        """Match the native title bar to the UI theme ("light", "dark" or "system") and remember it."""
        if mode not in ("light", "dark", "system"):
            return
        system.run_on_main(system.apply_appearance, mode)
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
    area = system.screen_area()
    if area is None:
        return 1400, 900
    area_width, area_height = area
    width = min(1600, round(area_width * 0.92))
    height = min(1000, round(area_height * 0.94))
    return (
        min(max(width, MIN_SIZE[0]), round(area_width)),
        min(max(height, MIN_SIZE[1]), round(area_height)),
    )


def main() -> None:
    if not (WEB_DIR / "index.html").is_file():
        raise SystemExit("UI is not built. Run `npm run build` in frontend/ first.")

    port, blocked_by = _choose_port(config.api_port(default=config.CAPTURE_PORT))
    app = create_app()
    app.state.port_blocked_by = blocked_by
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, loop="asyncio", http="h11", log_level="warning")
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
        system.run_on_main(system.add_standard_menus)
        system.run_on_main(system.apply_appearance, theme)

    window.events.shown += on_shown
    # private_mode=False keeps WebKit storage (e.g. the remembered Board/Table view) between launches.
    # Returns when the window is closed; then the backend is stopped and the app exits.
    webview.start(private_mode=False)
    server.should_exit = True
    backend.join(timeout=5)


if __name__ == "__main__":
    main()
