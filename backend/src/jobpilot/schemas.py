from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from jobpilot.models import JobStatus, WorkMode


class JobCreate(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    source: str | None = None
    status: JobStatus = JobStatus.SAVED
    next_action: str | None = None
    notes: str = ""


class JobUpdate(BaseModel):
    """All fields optional; only fields present in the request are changed."""

    company: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: HttpUrl | None = None
    location: str | None = None
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
    title: str
    url: str | None
    location: str | None
    work_mode: WorkMode | None
    source: str | None
    status: JobStatus
    next_action: str | None
    notes: str
    date_saved: datetime
    date_applied: datetime | None


class JobDetail(JobOut):
    events: list[StatusEventOut]
