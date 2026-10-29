"""Endpoints for the Chrome extension, which saves LinkedIn job pages the user has open.

The extension proves itself with a random key the app makes once and the user pastes into
the extension's settings. The app sends no CORS headers, so websites can neither read
these responses nor send the key header.
"""

import base64
import binascii
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobpilot import config, linkedin
from jobpilot.api import _get_or_create_company, _set_status, _to_out, get_session, set_linkedin_job_id
from jobpilot.db import utcnow
from jobpilot.locations import normalize_location
from jobpilot.logos import MAX_LOGO_BYTES, sniff_media_type
from jobpilot.models import Company, Job, JobStatus
from jobpilot.schemas import JobOut

router = APIRouter(prefix="/api")

TOKEN_HEADER = "X-JobPilot-Token"
# The extension's source: next to the package when bundled, at the repo root in development.
_PACKAGE_DIR = Path(__file__).parent
EXTENSION_SOURCE = next(
    (p for p in (_PACKAGE_DIR / "extension", _PACKAGE_DIR.parents[2] / "extension") if (p / "manifest.json").is_file()),
    None,
)
# Where "Show extension folder" puts a copy, so Chrome can load it from outside the app bundle.
EXTENSION_INSTALL_DIR = config.APP_SUPPORT_DIR / "Chrome Extension"


def read_token(path: Path) -> str:
    try:
        token = path.read_text().strip()
    except OSError:
        token = ""
    return token or new_token(path)


def new_token(path: Path) -> str:
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token)
    path.chmod(0o600)
    return token


def _token_ok(request: Request, token: str | None) -> bool:
    return bool(token) and secrets.compare_digest(token, read_token(request.app.state.token_file))


def require_token(request: Request, token: str | None = Header(None, alias=TOKEN_HEADER)) -> None:
    if not _token_ok(request, token):
        raise HTTPException(401, "Wrong or missing extension key")
    request.app.state.extension_seen_at = utcnow()


def require_app_page(request: Request) -> None:
    """For the app's own settings: refuse pages that reached the server under another
    host name (DNS rebinding) and plain cross-site form posts (no JSON content type)."""
    if request.url.hostname not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "Only the Job Pilot window can do this")
    if request.method != "GET" and request.headers.get("content-type") != "application/json":
        raise HTTPException(415, "Expected JSON")


@router.get("/ping")
def ping(request: Request, token: str | None = Header(None, alias=TOKEN_HEADER)):
    """Lets the extension tell "Job Pilot is closed" from "another program is on this port"
    and "the key is wrong"."""
    ok = _token_ok(request, token)
    if ok:
        request.app.state.extension_seen_at = utcnow()
    return {"app": "jobpilot", "token_ok": ok}


class CaptureIn(BaseModel):
    url: str = Field(max_length=2000)
    linkedin_job_id: str | None = Field(default=None, pattern=r"^\d{6,20}$")
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    company_linkedin_url: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=300)
    workplace: str | None = Field(default=None, max_length=100)
    employment_type: str | None = Field(default=None, max_length=100)
    # Text of the job's header (location, workplace, type badges), used when the fields above are missing.
    details: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=100_000)
    logo_base64: str | None = Field(default=None, max_length=MAX_LOGO_BYTES * 4 // 3 + 4)


class CaptureOut(BaseModel):
    created: bool
    job: JobOut


def _company_for(session: Session, body: CaptureIn) -> Company:
    slug = linkedin.company_slug(body.company_linkedin_url)
    company = session.scalar(select(Company).where(Company.linkedin_slug == slug)) if slug else None
    if company is None:
        company = _get_or_create_company(session, body.company)
    if slug and company.linkedin_slug is None:
        # Two companies can't share a slug; a renamed company is found by its slug above instead.
        company.linkedin_slug = slug
    if slug and not company.linkedin_url:
        company.linkedin_url = linkedin.company_url(slug)
    return company


def _decode_logo(raw: str | None) -> bytes | None:
    if not raw:
        return None
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None
    # SVGs can carry scripts; LinkedIn serves logos as raster images anyway.
    if len(data) > MAX_LOGO_BYTES or sniff_media_type(data) in (None, "image/svg+xml"):
        return None
    return data


@router.post("/capture", response_model=CaptureOut, dependencies=[Depends(require_token)])
def capture(body: CaptureIn, request: Request, session: Session = Depends(get_session)):
    job_id = body.linkedin_job_id or linkedin.job_id_from_url(body.url)
    if job_id is None:
        raise HTTPException(422, "Not a LinkedIn job page")
    existing = session.scalar(select(Job).where(Job.linkedin_job_id == job_id))
    if existing is not None:
        return CaptureOut(created=False, job=_to_out(existing))

    company = _company_for(session, body)
    city, district = linkedin.parse_location(body.location)
    job = Job(
        company=company,
        title=body.title.strip(),
        url=linkedin.job_url(job_id),
        work_mode=linkedin.parse_work_mode(body.workplace, body.location) or linkedin.parse_work_mode(body.details),
        job_type=linkedin.parse_job_type(body.employment_type) or linkedin.parse_job_type(body.details),
        source="LinkedIn",
        raw_text=(body.description or "").strip() or None,
    )
    job.city, job.side, job.district = normalize_location(city, None, district)
    set_linkedin_job_id(session, job, job_id)
    _set_status(job, JobStatus.SAVED)
    session.add(job)
    session.flush()  # gives a new company its id for the logo file

    if logo := _decode_logo(body.logo_base64):
        request.app.state.logos.put_captured(company.id, logo)
        company.logo_source = "linkedin"
    session.commit()
    return CaptureOut(created=True, job=_to_out(job))


class ExtensionInfo(BaseModel):
    token: str
    last_seen: datetime | None
    # The port the extension looks for, and the program holding it if the app had to use another one.
    capture_port: int
    port_blocked_by: str | None
    folder_available: bool


@router.get("/extension", response_model=ExtensionInfo, dependencies=[Depends(require_app_page)])
def extension_info(request: Request):
    state = request.app.state
    return ExtensionInfo(
        token=read_token(state.token_file),
        last_seen=getattr(state, "extension_seen_at", None),
        capture_port=config.CAPTURE_PORT,
        port_blocked_by=getattr(state, "port_blocked_by", None),
        folder_available=EXTENSION_SOURCE is not None,
    )


@router.post("/extension/token", response_model=ExtensionInfo, dependencies=[Depends(require_app_page)])
def reset_token(request: Request):
    """Makes a new key; the extension has to be given the new one."""
    new_token(request.app.state.token_file)
    request.app.state.extension_seen_at = None
    return extension_info(request)


def _copy_extension() -> None:
    """Copies the extension out of the app bundle, where Chrome's "Load unpacked" can reach it.
    Copying over an installed copy updates it; Chrome picks that up when the extension is reloaded."""
    if EXTENSION_SOURCE is None:
        raise HTTPException(404, "The extension isn't included in this build")
    shutil.copytree(EXTENSION_SOURCE, EXTENSION_INSTALL_DIR, dirs_exist_ok=True)


class InstallOut(BaseModel):
    folder: str


@router.post("/extension/install", response_model=InstallOut, dependencies=[Depends(require_app_page)])
def install_extension():
    """Opens Chrome's extensions page with the folder path on the clipboard, ready to paste
    into "Load unpacked" (Cmd+Shift+G). Chrome doesn't let apps install extensions themselves."""
    if subprocess.run(["open", "-Ra", "Google Chrome"], capture_output=True).returncode != 0:
        raise HTTPException(404, "Google Chrome isn't installed")
    _copy_extension()
    subprocess.run(["pbcopy"], input=str(EXTENSION_INSTALL_DIR).encode(), check=False)
    subprocess.run(["open", "-a", "Google Chrome", "chrome://extensions/"], check=False)
    return InstallOut(folder=str(EXTENSION_INSTALL_DIR))


@router.post("/extension/reveal", status_code=204, dependencies=[Depends(require_app_page)])
def reveal_extension():
    """Shows the extension folder in Finder."""
    _copy_extension()
    subprocess.run(["open", "-R", str(EXTENSION_INSTALL_DIR)], check=False)

