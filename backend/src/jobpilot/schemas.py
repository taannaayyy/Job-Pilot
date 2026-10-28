from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from jobpilot.locations import Side
from jobpilot.logos import normalize_website

from jobpilot.models import JobStatus, JobType, Openings, OrgKind, WorkMode


def _with_scheme(v):
    """Accept 'koc.edu.tr/careers' as well as full URLs; blank means none."""
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        if "://" not in v:
            return "https://" + v
    return v


class _JobFields(BaseModel):
    @field_validator("company_website", mode="before", check_fields=False)
    @classmethod
    def _website(cls, v):
        return normalize_website(v) if isinstance(v, str) or v is None else v

    @field_validator("city", "district", "source", "next_action", mode="before", check_fields=False)
    @classmethod
    def _blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class JobCreate(_JobFields):
    company: str = Field(min_length=1, max_length=200)
    company_website: str | None = None
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl | None = None
    city: str | None = Field(default=None, max_length=100)
    side: Side | None = None
    district: str | None = Field(default=None, max_length=100)
    job_type: JobType | None = None
    work_mode: WorkMode | None = None
    source: str | None = None
    status: JobStatus = JobStatus.SAVED
    next_action: str | None = None
    notes: str = ""


class JobUpdate(_JobFields):
    """All fields optional; only fields present in the request are changed."""

    company: str | None = Field(default=None, min_length=1, max_length=200)
    company_website: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: HttpUrl | None = None
    city: str | None = Field(default=None, max_length=100)
    side: Side | None = None
    district: str | None = Field(default=None, max_length=100)
    job_type: JobType | None = None
    work_mode: WorkMode | None = None
    source: str | None = None
    status: JobStatus | None = None
    next_action: str | None = None
    notes: str | None = None


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: JobStatus | None
    to_status: JobStatus
    timestamp: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    company_id: int
    company_website: str | None
    company_watching: bool
    logo_url: str | None
    title: str
    url: str | None
    city: str | None
    side: Side | None
    district: str | None
    job_type: JobType | None
    work_mode: WorkMode | None
    source: str | None
    status: JobStatus
    next_action: str | None
    notes: str
    date_saved: datetime
    date_applied: datetime | None


class JobDetail(JobOut):
    events: list[StatusEventOut]


class _CompanyFields(BaseModel):
    @field_validator("website", mode="before", check_fields=False)
    @classmethod
    def _website(cls, v):
        return normalize_website(v) if isinstance(v, str) or v is None else v

    @field_validator("careers_url", "linkedin_url", mode="before", check_fields=False)
    @classmethod
    def _urls(cls, v):
        return _with_scheme(v)


class CompanyCreate(_CompanyFields):
    name: str = Field(min_length=1, max_length=200)
    kind: OrgKind = OrgKind.COMPANY
    website: str | None = None
    careers_url: HttpUrl | None = None
    linkedin_url: HttpUrl | None = None
    notes: str = ""
    watching: bool = True


class CompanyUpdate(_CompanyFields):
    """All fields optional; only fields present in the request are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: OrgKind | None = None
    website: str | None = None
    careers_url: HttpUrl | None = None
    linkedin_url: HttpUrl | None = None
    notes: str | None = None
    watching: bool | None = None
    openings: Openings | None = None


class CompanyOut(BaseModel):
    id: int
    name: str
    kind: OrgKind
    website: str | None
    careers_url: str | None
    linkedin_url: str | None
    notes: str
    watching: bool
    date_watched: datetime | None
    openings: Openings | None
    last_checked_at: datetime | None
    logo_url: str | None
    job_count: int
    active_job_count: int
