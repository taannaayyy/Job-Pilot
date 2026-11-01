"""Fallback for systems without their own module (Linux).

Everything works, with less polish than on macOS and Windows: no native "port in use" dialog (the
app opens on another port and the UI banner explains why), no theme for the window frame, and the
default window size.
"""

import os
import shutil
import subprocess
from pathlib import Path

__all__ = [
    "data_dir",
    "port_holder",
    "ask_open_anyway",
    "screen_area",
    "system_is_dark",
    "run_on_main",
    "add_standard_menus",
    "apply_appearance",
    "chrome_installed",
    "open_in_chrome",
    "copy_to_clipboard",
    "reveal",
]


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "JobPilot"


def port_holder(port: int) -> str | None:
    return None


def ask_open_anyway(port: int, holder: str | None) -> bool:
    return True


def screen_area() -> tuple[float, float] | None:
    return None


def system_is_dark() -> bool:
    return False


def run_on_main(fn, *args) -> None:
    fn(*args)


def add_standard_menus() -> None:
    pass


def apply_appearance(mode: str) -> None:
    pass


def _chrome_path() -> str | None:
    candidates = [shutil.which(name) for name in ("chrome", "google-chrome", "google-chrome-stable")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def chrome_installed() -> bool:
    return _chrome_path() is not None


def open_in_chrome(url: str) -> None:
    if chrome := _chrome_path():
        subprocess.Popen([chrome, url])


def copy_to_clipboard(text: str) -> None:
    if copier := shutil.which("wl-copy") or shutil.which("xclip"):
        args = [copier] if copier.endswith("wl-copy") else [copier, "-selection", "clipboard"]
        subprocess.run(args, input=text.encode(), check=False)


def reveal(path: Path) -> None:
    if opener := shutil.which("xdg-open"):
        subprocess.run([opener, str(path.parent)], check=False)
