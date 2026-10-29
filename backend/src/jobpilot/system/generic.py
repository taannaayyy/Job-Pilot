"""Fallback for systems without their own module yet (Windows, Linux).

Everything works, with less polish than on macOS: no native "port in use" dialog (the app
opens on another port and the UI banner explains why), no theme for the window frame, and
the default window size. A Windows module would replace these one by one.
"""

import os
import shutil
import subprocess
import sys
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
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "JobPilot"
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
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    return next((c for c in candidates if c and Path(c).is_file()), None)


def chrome_installed() -> bool:
    return _chrome_path() is not None


def open_in_chrome(url: str) -> None:
    if chrome := _chrome_path():
        subprocess.Popen([chrome, url])


def copy_to_clipboard(text: str) -> None:
    if sys.platform == "win32":
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=False)


def reveal(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    elif opener := shutil.which("xdg-open"):
        subprocess.run([opener, str(path.parent)], check=False)
