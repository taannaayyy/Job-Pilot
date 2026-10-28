import re
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobpilot.db import Base, UTCDateTime, utcnow


class JobStatus(StrEnum):
    INBOX = "inbox"
    SAVED = "saved"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


def company_key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), unique=True)
    website: Mapped[str | None] = mapped_column(String(300))

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(1000))
    city: Mapped[str | None] = mapped_column(String(100))
    # Only for Istanbul; the Anadolu/Avrupa side is derived from it in the UI.
    district: Mapped[str | None] = mapped_column(String(100))
    work_mode: Mapped[WorkMode | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.SAVED, index=True)
    next_action: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    date_saved: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    date_applied: Mapped[datetime | None] = mapped_column(UTCDateTime)

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
