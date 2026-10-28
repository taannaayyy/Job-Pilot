from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from jobpilot import config
from jobpilot.api import router
from jobpilot.db import make_engine, make_sessionmaker
from jobpilot.logos import LogoCache

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Built UI (`npm run build` in frontend/). Absent during development, where Vite serves it.
WEB_DIR = Path(__file__).parent / "web"


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
    app.include_router(router)
    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
