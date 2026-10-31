# PyInstaller spec for Job Pilot.app. Build with packaging/build_app.sh.
from pathlib import Path

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
)
coll = COLLECT(exe, a.binaries, a.datas, name="Job Pilot")
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
