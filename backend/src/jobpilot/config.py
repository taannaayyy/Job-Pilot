import os
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "JobPilot"


def db_path() -> Path:
    override = os.environ.get("JOBPILOT_DB")
    if override:
        return Path(override).expanduser()
    return APP_SUPPORT_DIR / "jobpilot.db"


# The installed app's port, where the Chrome extension looks for it.
CAPTURE_PORT = 8765
# The development backend (dev.sh) uses the next one, so it can run while the app is open.
DEV_PORT = 8766


def api_port(default: int = DEV_PORT) -> int:
    return int(os.environ.get("JOBPILOT_PORT", default))
