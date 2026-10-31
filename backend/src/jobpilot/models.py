import re
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
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


class Importance(StrEnum):
    MUST = "must"
    NICE = "nice"  # "a plus", "preferred", "nice to have"


class SkillMark(StrEnum):
    """How the user rates themselves. No mark counts as a gap."""

    HAVE = "have"
    LEARNING = "learning"
    GAP = "gap"
    IGNORE = "ignore"  # "I don't want roles that need this"


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
    # Job description as captured from the posting (or pasted), kept to read while connecting skills.
    raw_text: Mapped[str | None] = mapped_column(Text)
    # Skill Gap: the role group this job is a target of. Status doesn't matter.
    target_group_id: Mapped[int | None] = mapped_column(ForeignKey("role_group.id", ondelete="SET NULL"), index=True)
    # Kept only to study the role: not shown on the job board.
    study_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    company: Mapped[Company] = relationship(back_populates="jobs", lazy="joined")
    events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="StatusEvent.timestamp",
    )
    target_group: Mapped["RoleGroup | None"] = relationship(back_populates="jobs")
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class StatusEvent(Base):
    __tablename__ = "status_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[JobStatus | None] = mapped_column(String(20))
    to_status: Mapped[JobStatus] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    job: Mapped[Job] = relationship(back_populates="events")


class RoleGroup(Base):
    """A kind of role the user is aiming for, e.g. "AI Engineer (now)" or "Senior ML Engineer (in 3 years)"."""

    __tablename__ = "role_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    jobs: Mapped[list[Job]] = relationship(back_populates="target_group")


class Skill(Base):
    """A node of the skill tree, and one requirement across all jobs ("PyTorch", "Bachelor's degree")."""

    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # Normalized name; "pytorch" and "PyTorch" are one skill.
    key: Mapped[str] = mapped_column(String(200), unique=True)
    # The tree: every node is a skill (Machine learning > Deep learning > Computer vision > YOLO).
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("skill.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    # In the tree; a skill a posting asks for that isn't waits in Unsorted until the user places it.
    placed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Only organizes ("Cloud"): holds skills, is never asked for itself.
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    mark: Mapped[SkillMark | None] = mapped_column(String(10))
    # What the user plans to do about it: a course, a project idea.
    plan_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    # What it means, in the user's words.
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Keys of its names before the user renamed it ("\npytorch\n"), so postings that still use them find it.
    old_keys: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    requirements: Mapped[list["Requirement"]] = relationship(back_populates="skill", cascade="all, delete-orphan")
    parent: Mapped["Skill | None"] = relationship(remote_side="Skill.id")
    events: Mapped[list["SkillEvent"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", order_by="SkillEvent.timestamp"
    )


class Requirement(Base):
    """A job asks for a skill."""

    __tablename__ = "requirement"
    __table_args__ = (UniqueConstraint("job_id", "skill_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id", ondelete="CASCADE"), index=True)
    importance: Mapped[Importance] = mapped_column(String(10))
    # The words in the posting it came from, and where in the description the user selected them.
    evidence: Mapped[str | None] = mapped_column(String(500))
    evidence_at: Mapped[int | None] = mapped_column()
    # "3-5 years of Python": years on the skill they're about; overall years on "Professional experience".
    min_years: Mapped[int | None] = mapped_column()
    max_years: Mapped[int | None] = mapped_column()
    # Degrees: the fields of study accepted ("Computer Engineering, Statistics").
    detail: Mapped[str | None] = mapped_column(String(500))
    # "user"; "dictionary" and "model" for ones made when the app still read job descriptions.
    source: Mapped[str] = mapped_column(String(20))

    job: Mapped[Job] = relationship(back_populates="requirements")
    skill: Mapped[Skill] = relationship(back_populates="requirements", lazy="joined")


class SkillEvent(Base):
    """Every change of the user's mark, for the progress shown on Insights."""

    __tablename__ = "skill_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id", ondelete="CASCADE"), index=True)
    from_mark: Mapped[SkillMark | None] = mapped_column(String(10))
    to_mark: Mapped[SkillMark | None] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    skill: Mapped[Skill] = relationship(back_populates="events")
