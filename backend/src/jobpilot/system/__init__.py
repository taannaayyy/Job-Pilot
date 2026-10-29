"""Everything that depends on the operating system, behind one set of functions.

`macos` is the real implementation. `generic` is a plain fallback for other systems and the
starting point for a Windows version. The rest of the app only calls the functions listed here:

    data_dir()                    folder for the database, logos and settings
    port_holder(port)             name of the program listening on a port, if known
    ask_open_anyway(port, holder) native "port in use" dialog; True to open anyway
    screen_area()                 usable (width, height) of the main screen, or None
    system_is_dark()              whether the system appearance is dark
    run_on_main(fn, *args)        run on the UI thread (window callbacks arrive on others)
    add_standard_menus()          menus and shortcuts the window toolkit leaves out
    apply_appearance(mode)        "light", "dark" or "system" for the native window parts
    chrome_installed()            whether Google Chrome is installed
    open_in_chrome(url)           open a URL (including chrome://) in Chrome
    copy_to_clipboard(text)       put text on the clipboard
    reveal(path)                  show a file or folder in the file manager
"""

import sys

if sys.platform == "darwin":
    from jobpilot.system.macos import *  # noqa: F403
else:
    from jobpilot.system.generic import *  # noqa: F403
