import re
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobpilot.db import Base, UTCDateTime, utcnow


class JobStatus(StrEnum):
    INBOX = "inbox"
    SAVED = "saved"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    # All interviews done, waiting for their answer.
    AWAITING = "awaiting"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class JobType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"


class OrgKind(StrEnum):
    COMPANY = "company"
    STARTUP = "startup"
    RESEARCH = "research"
    UNIVERSITY = "university"
    OTHER = "other"


class Openings(StrEnum):
    HIRING = "hiring"
    NONE = "none"


# Jobs still going somewhere; counted as "active" on the watchlist.
ACTIVE_STATUSES = {"inbox", "saved", "applied", "screening", "interview", "awaiting", "offer"}


def company_key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), unique=True)
    website: Mapped[str | None] = mapped_column(String(300))
    # Companies, startups, research centers, universities: anything that might hire.
    kind: Mapped[OrgKind] = mapped_column(String(20), default=OrgKind.COMPANY, server_default=OrgKind.COMPANY)
    careers_url: Mapped[str | None] = mapped_column(String(1000))
    linkedin_url: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    # On the watchlist. Companies are also created by jobs, which doesn't put them there.
    watching: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    date_watched: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Result of the last manual check for open positions; None means never checked.
    openings: Mapped[Openings | None] = mapped_column(String(10))
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # From the LinkedIn company link on a captured job ("acme-ai"); matches companies across name changes.
    linkedin_slug: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)
    # "linkedin" when the logo was captured from a LinkedIn job page; otherwise it comes from the website.
    logo_source: Mapped[str | None] = mapped_column(String(20))

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(1000))
    city: Mapped[str | None] = mapped_column(String(100))
    # Only for Istanbul. Side can be set alone ("anywhere on Anadolu"); a district implies its side.
    side: Mapped[str | None] = mapped_column(String(10))
    district: Mapped[str | None] = mapped_column(String(100))
    job_type: Mapped[JobType | None] = mapped_column(String(20))
    work_mode: Mapped[WorkMode | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.SAVED, index=True)
    next_action: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    date_saved: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    date_applied: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # The same LinkedIn job is never saved twice.
    linkedin_job_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    # Job description as captured from the posting, for the extraction step.
    raw_text: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="jobs", lazy="joined")
    events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="StatusEvent.timestamp",
    )


class StatusEvent(Base):
    __tablename__ = "status_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[JobStatus | None] = mapped_column(String(20))
    to_status: Mapped[JobStatus] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    job: Mapped[Job] = relationship(back_populates="events")
