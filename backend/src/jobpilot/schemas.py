from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from jobpilot.locations import Side
from jobpilot.logos import normalize_website

from jobpilot.models import JobStatus, WorkMode


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
    logo_url: str | None
    title: str
    url: str | None
    city: str | None
    side: Side | None
    district: str | None
    work_mode: WorkMode | None
    source: str | None
    status: JobStatus
    next_action: str | None
    notes: str
    date_saved: datetime
    date_applied: datetime | None


class JobDetail(JobOut):
    events: list[StatusEventOut]
