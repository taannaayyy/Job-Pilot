"""Windows: the Win32 API through ctypes and winreg, plus the usual command-line tools (netstat, tasklist,
clip, explorer).

ctypes.windll and winreg exist only on Windows, so they are reached inside the functions; the parsing
helpers are plain functions, so they can be tested anywhere.
"""

import csv
import io
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

WINDOW_TITLE = "Job Pilot"
# A windowed app starting a console program would flash a black console window without this.
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, creationflags=NO_WINDOW, capture_output=True, timeout=5, check=False, **kwargs)


def data_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "JobPilot"


def listening_pid(netstat: str, port: int) -> int | None:
    """The process listening on 127.0.0.1 or 0.0.0.0 at port, from `netstat -ano -p TCP` output."""
    for line in netstat.splitlines():
        parts = line.split()
        # TCP    127.0.0.1:8765    0.0.0.0:0    LISTENING    4242
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def image_name(tasklist_csv: str) -> str | None:
    """"node" from `tasklist /FO CSV /NH` output like "node.exe","4242",...; None when nothing matched."""
    for row in csv.reader(io.StringIO(tasklist_csv)):
        if len(row) >= 2 and row[1].isdigit():
            return Path(row[0]).stem or None
    return None


def port_holder(port: int) -> str | None:
    """Name of the program listening on the port, e.g. "node" or "Docker Desktop"."""
    try:
        pid = listening_pid(_run(["netstat", "-ano", "-p", "TCP"], text=True).stdout, port)
        if pid is None:
            return None
        return image_name(_run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], text=True).stdout)
    except (OSError, subprocess.SubprocessError):
        return None


def ask_open_anyway(port: int, holder: str | None) -> bool:
    import ctypes

    text = (
        f"{holder or 'Another program'} is using port {port}, which the Job Pilot Chrome extension uses to reach "
        "the app.\n\nQuit it and open Job Pilot again, or open anyway: everything works except saving jobs from "
        "LinkedIn, which wait in the extension until the port is free.\n\nOpen Job Pilot anyway?"
    )
    MB_YESNO, MB_ICONWARNING, MB_TOPMOST, IDYES = 0x4, 0x30, 0x40000, 6
    return ctypes.windll.user32.MessageBoxW(None, text, f"Port {port} is already in use", MB_YESNO | MB_ICONWARNING | MB_TOPMOST) == IDYES


def screen_area() -> tuple[float, float] | None:
    """The main screen's work area (without the taskbar), in the window's units (96 dpi pixels)."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    SPI_GETWORKAREA = 0x0030
    if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return None
    try:
        scale = ctypes.windll.user32.GetDpiForSystem() / 96
    except AttributeError:  # before Windows 10
        scale = 1
    return (rect.right - rect.left) / scale, (rect.bottom - rect.top) / scale


def system_is_dark() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def run_on_main(fn, *args) -> None:
    # The Win32 calls below may come from any thread.
    fn(*args)


def add_standard_menus() -> None:
    # Windows apps have no menu bar for these: copy, paste and undo come from the web view, and Alt+F4 closes.
    pass


def apply_appearance(mode: str) -> None:
    """A dark or light title bar ("system" follows Windows), through the window manager."""
    import ctypes

    dark = mode == "dark" or (mode == "system" and system_is_dark())
    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return
    value = ctypes.c_int(1 if dark else 0)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE; 19 before Windows 10 20H1
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            break
    # Redraw the frame so the change shows at once.
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x20
    ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)


def _chrome_path() -> str | None:
    candidates = [shutil.which("chrome")]
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    return next((c for c in candidates if c and Path(c).is_file()), None)


def chrome_installed() -> bool:
    return _chrome_path() is not None


def open_in_chrome(url: str) -> None:
    if chrome := _chrome_path():
        subprocess.Popen([chrome, url], creationflags=NO_WINDOW)


def copy_to_clipboard(text: str) -> None:
    # clip reads UTF-16 with a byte order mark as Unicode, so Turkish letters and paths survive.
    _run(["clip"], input=b"\xff\xfe" + text.encode("utf-16-le"))


def reveal(path: Path) -> None:
    subprocess.Popen(["explorer", f"/select,{path}"], creationflags=NO_WINDOW)
