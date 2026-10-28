import os
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "JobPilot"


def db_path() -> Path:
    override = os.environ.get("JOBPILOT_DB")
    if override:
        return Path(override).expanduser()
    return APP_SUPPORT_DIR / "jobpilot.db"


def api_port() -> int:
    return int(os.environ.get("JOBPILOT_PORT", "8765"))
