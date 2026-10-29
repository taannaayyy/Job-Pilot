"""Company logos, cached next to the database: the logo captured from a LinkedIn job page
(sent by the Chrome extension), otherwise the website's icon, fetched once."""

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# Tried in order; both return 404 when they have no icon for the domain.
SOURCES = [
    "https://www.google.com/s2/favicons?domain={domain}&sz=128",
    "https://icons.duckduckgo.com/ip3/{domain}.ico",
]
RETRY_MISSING_AFTER = 7 * 24 * 3600
MAX_LOGO_BYTES = 512 * 1024


def normalize_website(raw: str | None) -> str | None:
    """'insider.com', 'https://www.Insider.com/careers' -> 'https://insider.com'."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if "://" not in value:
        value = "https://" + value
    host = (urlsplit(value).hostname or "").lower().removeprefix("www.")
    if "." not in host or " " in host:
        raise ValueError("not a valid website")
    return f"https://{host}"


def domain_of(website: str) -> str:
    return urlsplit(website).hostname or ""


def fetch_icon(domain: str) -> bytes | None:
    for template in SOURCES:
        req = urllib.request.Request(template.format(domain=domain), headers={"User-Agent": "JobPilot/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                data = res.read(MAX_LOGO_BYTES)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        if sniff_media_type(data):
            return data
    return None


def sniff_media_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if b"<svg" in data[:512]:
        return "image/svg+xml"
    return None


class LogoCache:
    def __init__(self, directory: Path, fetch=fetch_icon):
        self.directory = directory
        self.fetch = fetch

    def get(self, domain: str) -> bytes | None:
        key = hashlib.sha1(domain.encode()).hexdigest()[:16]
        image, missing = self.directory / f"{key}.img", self.directory / f"{key}.none"
        if image.is_file():
            return image.read_bytes()
        if missing.is_file() and time.time() - missing.stat().st_mtime < RETRY_MISSING_AFTER:
            return None
        data = self.fetch(domain)
        self.directory.mkdir(parents=True, exist_ok=True)
        if data is None:
            missing.touch()
            return None
        image.write_bytes(data)
        missing.unlink(missing_ok=True)
        return data

    def _captured(self, company_id: int) -> Path:
        return self.directory / f"company-{company_id}.img"

    def get_captured(self, company_id: int) -> bytes | None:
        path = self._captured(company_id)
        return path.read_bytes() if path.is_file() else None

    def put_captured(self, company_id: int, data: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._captured(company_id).write_bytes(data)
