from collections.abc import Iterator

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from jobpilot.db import utcnow
from jobpilot.locations import normalize_location
from jobpilot.logos import domain_of, sniff_media_type
from jobpilot.models import Company, Job, JobStatus, StatusEvent, WorkMode, company_key
from jobpilot.schemas import JobCreate, JobDetail, JobOut, JobUpdate

router = APIRouter(prefix="/api")

# Reaching any of these means the user applied, even if Applied itself was skipped.
APPLIED_OR_LATER = {JobStatus.APPLIED, JobStatus.SCREENING, JobStatus.INTERVIEW, JobStatus.OFFER}


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


def _get_or_create_company(session: Session, name: str) -> Company:
    key = company_key(name)
    company = session.scalar(select(Company).where(Company.name_key == key))
    if company is None:
        company = Company(name=name.strip(), name_key=key)
        session.add(company)
    return company


def _set_status(job: Job, status: JobStatus) -> None:
    if job.status == status and job.events:
        return
    job.events.append(StatusEvent(from_status=job.status if job.events else None, to_status=status))
    job.status = status
    if status in APPLIED_OR_LATER and job.date_applied is None:
        job.date_applied = utcnow()


COMPUTED = {"company", "company_website", "logo_url", "events"}


def _to_out(job: Job, model: type[JobOut] = JobOut) -> JobOut:
    data = {f: getattr(job, f) for f in model.model_fields if f not in COMPUTED}
    website = job.company.website
    data["company"] = job.company.name
    data["company_website"] = website
    # The domain in the query string makes the browser refetch when the website changes.
    data["logo_url"] = f"/api/companies/{job.company_id}/logo?d={quote(domain_of(website))}" if website else None
    if "events" in model.model_fields:
        data["events"] = job.events
    return model.model_validate(data)


def _get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    status: JobStatus | None = None,
    work_mode: WorkMode | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(Job).join(Job.company).order_by(Job.date_saved.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    if work_mode:
        stmt = stmt.where(Job.work_mode == work_mode)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Job.title.ilike(like), Company.name.ilike(like), Job.city.ilike(like), Job.district.ilike(like))
        )
    return [_to_out(j) for j in session.scalars(stmt).unique()]


@router.post("/jobs", response_model=JobDetail, status_code=201)
def create_job(body: JobCreate, session: Session = Depends(get_session)):
    fields = body.model_dump(exclude={"company", "company_website", "status"}, mode="json")
    company = _get_or_create_company(session, body.company)
    if body.company_website:  # a blank website never erases one already known for the company
        company.website = body.company_website
    job = Job(company=company, **fields)
    job.city, job.side, job.district = normalize_location(job.city, job.side, job.district)
    _set_status(job, body.status)
    session.add(job)
    session.commit()
    return _to_out(job, JobDetail)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: Session = Depends(get_session)):
    return _to_out(_get_job(session, job_id), JobDetail)


@router.patch("/jobs/{job_id}", response_model=JobDetail)
def update_job(job_id: int, body: JobUpdate, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    changes = body.model_dump(exclude_unset=True, mode="json")
    if "company" in changes:
        job.company = _get_or_create_company(session, changes.pop("company"))
    if "company_website" in changes:
        job.company.website = changes.pop("company_website")
    if "status" in changes:
        status = changes.pop("status")
        if status is not None:
            _set_status(job, JobStatus(status))
    for field, value in changes.items():
        if field in ("title", "notes") and value is None:
            continue
        setattr(job, field, value)
    job.city, job.side, job.district = normalize_location(job.city, job.side, job.district)
    session.commit()
    return _to_out(job, JobDetail)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, session: Session = Depends(get_session)):
    session.delete(_get_job(session, job_id))
    session.commit()
    return Response(status_code=204)


@router.get("/companies/{company_id}/logo")
def company_logo(company_id: int, request: Request, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if company is None or not company.website:
        raise HTTPException(404, "No logo")
    data = request.app.state.logos.get(domain_of(company.website))
    if data is None:
        raise HTTPException(404, "No logo", headers={"Cache-Control": "max-age=3600"})
    return Response(data, media_type=sniff_media_type(data), headers={"Cache-Control": "max-age=86400"})
