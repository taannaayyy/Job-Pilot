from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from jobpilot import ai, capture, config, skillgap
from jobpilot.api import router
from jobpilot.db import make_engine, make_sessionmaker
from jobpilot.logos import LogoCache

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Built UI (`npm run build` in frontend/). Absent during development, where Vite serves it.
WEB_DIR = Path(__file__).parent / "web"


class _WebFiles(StaticFiles):
    """The page itself is always revalidated, so a rebuilt app never shows the previous UI
    from the window's cache. Built assets have a content hash in their name and never change."""

    def file_response(self, full_path, *args, **kwargs):
        response = super().file_response(full_path, *args, **kwargs)
        immutable = "/assets/" in str(full_path)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if immutable else "no-cache"
        return response


def run_migrations(db_file: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.upgrade(cfg, "head")


def create_app(db_file: Path | None = None) -> FastAPI:
    db_file = db_file or config.db_path()
    engine = make_engine(db_file)
    run_migrations(db_file)

    app = FastAPI(title="Job Pilot")
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.logos = LogoCache(db_file.parent / "logos")
    # Key the Chrome extension must send; kept next to the database.
    app.state.token_file = db_file.parent / "extension-key"
    app.state.ai_settings = ai.Settings(db_file.parent / "ai-settings.json")
    app.include_router(router)
    app.include_router(capture.router)
    app.include_router(skillgap.router)
    if WEB_DIR.is_dir():
        app.mount("/", _WebFiles(directory=WEB_DIR, html=True), name="web")
    return app
