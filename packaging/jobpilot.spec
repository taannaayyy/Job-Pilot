# PyInstaller spec for Job Pilot: Job Pilot.app on macOS (packaging/build_app.sh), a "Job Pilot" folder with
# Job Pilot.exe on Windows (packaging/build_windows.ps1, then the installer from packaging/windows/installer.iss).
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"

ROOT = Path(SPECPATH).parent
PKG = ROOT / "backend" / "src" / "jobpilot"

a = Analysis(
    [str(PKG / "desktop.py")],
    pathex=[str(ROOT / "backend" / "src")],
    # Alembic loads migration scripts from files at runtime, so they ship as data.
    datas=[
        (str(PKG / "web"), "jobpilot/web"),
        (str(PKG / "migrations"), "jobpilot/migrations"),
        # The Chrome extension, copied out by "Show extension folder" in the app.
        (str(ROOT / "extension"), "jobpilot/extension"),
    ],
    # Imported only by migration scripts, which PyInstaller doesn't see.
    hiddenimports=["jobpilot.models", "jobpilot.skills", "jobpilot.taxonomy"],
    excludes=["tkinter", "uvloop", "httptools", "watchfiles", "websockets"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Job Pilot",
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico") if WINDOWS else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Job Pilot")
if not WINDOWS:
    app = BUNDLE(
        coll,
        name="Job Pilot.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="com.tanayalpkonur.jobpilot",
        version="0.1.0",
        info_plist={
            "CFBundleDisplayName": "Job Pilot",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            # The window only talks to its own backend on 127.0.0.1.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
