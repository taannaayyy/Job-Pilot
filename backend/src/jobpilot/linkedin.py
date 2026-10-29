"""Reads the text LinkedIn shows on a job or company page. Nothing here fetches LinkedIn: the Chrome
extension sends what the user already has open."""

import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

from jobpilot.locations import ISTANBUL, SIDE_OF
from jobpilot.models import JobType, OrgKind, WorkMode

# /jobs/view/1234567890 and the public /jobs/view/ml-engineer-at-acme-1234567890
_VIEW_ID = re.compile(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})")
# Universities have /school/ pages; LinkedIn redirects /company/ links to them.
_COMPANY_SLUG = re.compile(r"/(?:company|school)/([^/?#]+)")


def job_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not (parts.hostname or "").endswith("linkedin.com"):
        return None
    if m := _VIEW_ID.search(parts.path):
        return m.group(1)
    current = parse_qs(parts.query).get("currentJobId", [""])[0]
    return current if current.isdigit() else None


def job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def company_slug(url: str | None) -> str | None:
    """'https://www.linkedin.com/company/acme-ai/life/' -> 'acme-ai'."""
    if not url or not (urlsplit(url).hostname or "").endswith("linkedin.com"):
        return None
    m = _COMPANY_SLUG.search(urlsplit(url).path)
    return m.group(1).lower() if m else None


def company_url(slug: str) -> str:
    return f"https://www.linkedin.com/company/{slug}/"


def website_from_link(url: str | None) -> str | None:
    """The company's own site from a "Visit website" link, which LinkedIn sometimes wraps
    in /redir/redirect?url=... . None for LinkedIn's own pages."""
    if not url:
        return None
    parts = urlsplit(url)
    if (parts.hostname or "").endswith("linkedin.com"):
        url = parse_qs(parts.query).get("url", [""])[0]
        parts = urlsplit(url)
        if not url or (parts.hostname or "").endswith("linkedin.com"):
            return None
    return url if parts.scheme in ("http", "https") and parts.hostname else None


def parse_org_kind(industry: str | None, url: str | None = None) -> OrgKind:
    """'Higher Education' or a /school/ page -> university, 'Research Services' -> research."""
    text = fold(industry or "")
    if "/school/" in (url or "") or re.search(r"higher education|universit|egitim kurumlari", text):
        return OrgKind.UNIVERSITY
    if re.search(r"research|arastirma", text):
        return OrgKind.RESEARCH
    return OrgKind.COMPANY


def fold(text: str) -> str:
    """Lowercase without Turkish letters or accents: 'İstanbul' -> 'istanbul', 'Kadıköy' -> 'kadikoy'."""
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_DISTRICT_BY_FOLD = {fold(d): d for d in SIDE_OF}
_COUNTRIES = {"turkiye", "turkey", "tr"}
# "Greater Istanbul", "Istanbul Metropolitan Area"
_AREA_WORDS = re.compile(r"\b(greater|metropolitan|area|province|ili)\b", re.IGNORECASE)


def parse_location(raw: str | None) -> tuple[str | None, str | None]:
    """'Kadıköy, İstanbul, Türkiye (Hybrid)' -> ('Istanbul', 'Kadıköy'); 'Ankara, Türkiye' -> ('Ankara', None)."""
    if not raw:
        return None, None
    text = re.sub(r"\(.*?\)", "", raw)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    folded = [_AREA_WORDS.sub("", fold(p)).strip() for p in parts]
    district = next((_DISTRICT_BY_FOLD[f] for f in folded if f in _DISTRICT_BY_FOLD), None)
    if district or "istanbul" in folded:
        return ISTANBUL, district
    cities = [p for p, f in zip(parts, folded) if f and f not in _COUNTRIES]
    return (re.sub(r"\s+", " ", _AREA_WORDS.sub("", cities[0])).strip() or None) if cities else None, None


def parse_work_mode(*texts: str | None) -> WorkMode | None:
    text = fold(" ".join(t for t in texts if t))
    if "hybrid" in text or "hibrit" in text:
        return WorkMode.HYBRID
    if "remote" in text or "uzaktan" in text:
        return WorkMode.REMOTE
    if re.search(r"on-?site|ofiste|isyerinde", text):
        return WorkMode.ONSITE
    return None


def parse_job_type(*texts: str | None) -> JobType | None:
    text = fold(" ".join(t for t in texts if t))
    if re.search(r"intern|staj", text):
        return JobType.INTERNSHIP
    if re.search(r"part[-_ ]?time|yari zamanli", text):
        return JobType.PART_TIME
    if re.search(r"contract|temporary|freelance|sozlesmeli", text):
        return JobType.CONTRACT
    if re.search(r"full[-_ ]?time|tam zamanli", text):
        return JobType.FULL_TIME
    return None
