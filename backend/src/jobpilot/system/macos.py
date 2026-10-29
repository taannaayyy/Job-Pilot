"""macOS: AppKit through PyObjC, plus the usual command-line tools (lsof, open, pbcopy).

AppKit is imported inside the functions so that importing this module stays cheap and works
in tests.
"""

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
    return Path.home() / "Library" / "Application Support" / "JobPilot"


def port_holder(port: int) -> str | None:
    """Name of the program listening on the port, e.g. "node" or "Docker"."""
    try:
        pid = subprocess.run(
            ["lsof", "-nP", "-tiTCP:%d" % port, "-sTCP:LISTEN"], capture_output=True, text=True, timeout=3
        ).stdout.split()[0]
        command = subprocess.run(["ps", "-o", "comm=", "-p", pid], capture_output=True, text=True, timeout=3).stdout
    except (OSError, IndexError, subprocess.SubprocessError):
        return None
    path = Path(command.strip())
    # Show "Docker" for /Applications/Docker.app/Contents/MacOS/com.docker.backend.
    app = next((p.stem for p in path.parents if p.suffix == ".app"), None)
    return app or path.name or None


def ask_open_anyway(port: int, holder: str | None) -> bool:
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(f"Port {port} is already in use")
    alert.setInformativeText_(
        f"{holder or 'Another program'} is using port {port}, which the Job Pilot Chrome extension uses "
        "to reach the app.\n\nQuit it and open Job Pilot again, or open anyway: everything works except "
        "saving jobs from LinkedIn, which wait in the extension until the port is free."
    )
    alert.addButtonWithTitle_("Open Anyway")
    alert.addButtonWithTitle_("Quit")
    return alert.runModal() == AppKit.NSAlertFirstButtonReturn


def screen_area() -> tuple[float, float] | None:
    import AppKit

    AppKit.NSApplication.sharedApplication()
    screen = AppKit.NSScreen.mainScreen()
    if screen is None:
        return None
    area = screen.visibleFrame().size  # excludes the menu bar and the Dock
    return area.width, area.height


def system_is_dark() -> bool:
    import Foundation

    style = Foundation.NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
    return style == "Dark"


def run_on_main(fn, *args) -> None:
    from PyObjCTools import AppHelper

    AppHelper.callAfter(fn, *args)


def add_standard_menus() -> None:
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


def apply_appearance(mode: str) -> None:
    import AppKit

    names = {"light": AppKit.NSAppearanceNameAqua, "dark": AppKit.NSAppearanceNameDarkAqua}
    appearance = AppKit.NSAppearance.appearanceNamed_(names[mode]) if mode in names else None
    AppKit.NSApplication.sharedApplication().setAppearance_(appearance)  # None follows the system


def chrome_installed() -> bool:
    return subprocess.run(["open", "-Ra", "Google Chrome"], capture_output=True).returncode == 0


def open_in_chrome(url: str) -> None:
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=False)


def reveal(path: Path) -> None:
    subprocess.run(["open", "-R", str(path)], check=False)
