"""Skill Gap: role groups, the requirements of their target jobs added up, the user's own marks,
and the AI settings that extraction uses."""

import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobpilot import ai, extraction
from jobpilot.api import _get_job, _to_out, get_session, queue_extraction, start_extraction
from jobpilot.capture import require_app_page
from jobpilot.models import ExtractionStatus, Importance, Job, Requirement, RoleGroup, Skill, SkillEvent, SkillMark
from jobpilot.schemas import JobDetail

router = APIRouter(prefix="/api")

# Coverage counts a must-have twice as much as a nice-to-have.
WEIGHT = {Importance.MUST: 2, Importance.NICE: 1}


# ---- Role groups


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupOut(BaseModel):
    id: int
    name: str
    job_count: int


def _group_out(session: Session, group: RoleGroup) -> GroupOut:
    count = session.scalar(select(func.count()).select_from(Job).where(Job.target_group_id == group.id))
    return GroupOut(id=group.id, name=group.name, job_count=count or 0)


def _unique_name(session: Session, name: str, group_id: int | None = None) -> str:
    name = " ".join(name.split())
    other = session.scalar(select(RoleGroup).where(func.lower(RoleGroup.name) == name.lower(), RoleGroup.id != group_id))
    if other is not None:
        raise HTTPException(409, f"There is already a group called {other.name}")
    return name


@router.get("/role-groups", response_model=list[GroupOut])
def list_groups(session: Session = Depends(get_session)):
    return [_group_out(session, g) for g in session.scalars(select(RoleGroup).order_by(RoleGroup.created_at))]


@router.post("/role-groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupIn, session: Session = Depends(get_session)):
    group = RoleGroup(name=_unique_name(session, body.name))
    session.add(group)
    session.commit()
    return _group_out(session, group)


@router.patch("/role-groups/{group_id}", response_model=GroupOut)
def rename_group(group_id: int, body: GroupIn, session: Session = Depends(get_session)):
    group = session.get(RoleGroup, group_id) or _missing("Role group")
    group.name = _unique_name(session, body.name, group.id)
    session.commit()
    return _group_out(session, group)


@router.delete("/role-groups/{group_id}", status_code=204)
def delete_group(group_id: int, session: Session = Depends(get_session)):
    """Its jobs stop being targets; the jobs themselves and the user's marks stay."""
    group = session.get(RoleGroup, group_id) or _missing("Role group")
    for job in group.jobs:
        job.target_group_id = None
    session.delete(group)
    session.commit()
    return Response(status_code=204)


def _missing(what: str):
    raise HTTPException(404, f"{what} not found")


# ---- The gap list


class SkillRow(BaseModel):
    id: int
    name: str
    category: str
    mark: SkillMark | None
    plan_note: str
    jobs: int
    must: int
    nice: int


class GapOut(BaseModel):
    targets: int
    # Targets whose requirements are known, still being read, failed, or have no description to read.
    extracted: int
    pending: int
    failed: int
    without_text: int
    # Share of the targets' requirements (must counted double) the user has; ignored skills left out.
    coverage: float | None
    skills: list[SkillRow]


def _targets(session: Session, group_id: int | None) -> list[Job]:
    stmt = select(Job).where(Job.target_group_id.is_not(None))
    if group_id is not None:
        stmt = stmt.where(Job.target_group_id == group_id)
    return list(session.scalars(stmt).unique())


@router.get("/skill-gap", response_model=GapOut)
def skill_gap(group_id: int | None = None, session: Session = Depends(get_session)):
    """Every requirement of the group's targets (all targets without a group_id), most asked for first."""
    targets = _targets(session, group_id)
    rows: dict[int, SkillRow] = {}
    covered = total = 0
    for job in targets:
        for req in job.requirements:
            if not req.active:
                continue
            skill = req.skill
            row = rows.get(skill.id) or rows.setdefault(
                skill.id,
                SkillRow(id=skill.id, name=skill.name, category=skill.category, mark=skill.mark,
                         plan_note=skill.plan_note, jobs=0, must=0, nice=0),
            )
            row.jobs += 1
            if req.importance == Importance.MUST:
                row.must += 1
            else:
                row.nice += 1
            if skill.mark != SkillMark.IGNORE:
                total += WEIGHT[req.importance]
                covered += WEIGHT[req.importance] if skill.mark == SkillMark.HAVE else 0
    status = defaultdict(int)
    for job in targets:
        if not job.raw_text:
            status["without_text"] += 1
        elif job.extraction_status == ExtractionStatus.DONE:
            status["extracted"] += 1
        elif job.extraction_status == ExtractionStatus.FAILED:
            status["failed"] += 1
        else:
            status["pending"] += 1
    return GapOut(
        targets=len(targets),
        extracted=status["extracted"],
        pending=status["pending"],
        failed=status["failed"],
        without_text=status["without_text"],
        coverage=covered / total if total else None,
        skills=sorted(rows.values(), key=lambda r: (-r.jobs, -r.must, r.name.casefold())),
    )


class Evidence(BaseModel):
    job_id: int
    title: str
    company: str
    importance: Importance
    evidence: str | None


class MarkChange(BaseModel):
    from_mark: SkillMark | None
    to_mark: SkillMark | None
    timestamp: datetime


class SkillDetail(BaseModel):
    id: int
    name: str
    category: str
    mark: SkillMark | None
    plan_note: str
    jobs: list[Evidence]
    history: list[MarkChange]


def _skill_detail(skill: Skill, group_id: int | None) -> SkillDetail:
    reqs = [
        r for r in skill.requirements
        if r.active and r.job.target_group_id is not None and (group_id is None or r.job.target_group_id == group_id)
    ]
    return SkillDetail(
        id=skill.id, name=skill.name, category=skill.category, mark=skill.mark, plan_note=skill.plan_note,
        jobs=[
            Evidence(job_id=r.job.id, title=r.job.title, company=r.job.company.name, importance=r.importance, evidence=r.evidence)
            for r in sorted(reqs, key=lambda r: (r.importance != "must", r.job.title.casefold()))
        ],
        history=[MarkChange(from_mark=e.from_mark, to_mark=e.to_mark, timestamp=e.timestamp) for e in skill.events],
    )


@router.get("/skills/{skill_id}", response_model=SkillDetail)
def get_skill(skill_id: int, group_id: int | None = None, session: Session = Depends(get_session)):
    return _skill_detail(session.get(Skill, skill_id) or _missing("Skill"), group_id)


class SkillUpdate(BaseModel):
    mark: SkillMark | None = None
    plan_note: str | None = Field(default=None, max_length=10_000)


@router.patch("/skills/{skill_id}", response_model=SkillDetail)
def update_skill(skill_id: int, body: SkillUpdate, group_id: int | None = None, session: Session = Depends(get_session)):
    skill = session.get(Skill, skill_id) or _missing("Skill")
    changes = body.model_dump(exclude_unset=True)
    if "mark" in changes and changes["mark"] != skill.mark:
        # Every change is kept for the progress shown on Insights.
        skill.events.append(SkillEvent(from_mark=skill.mark, to_mark=changes["mark"]))
        skill.mark = changes["mark"]
    if changes.get("plan_note") is not None:
        skill.plan_note = changes["plan_note"]
    session.commit()
    return _skill_detail(skill, group_id)


# ---- A job's requirements


class RequirementIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    importance: Importance = Importance.MUST


@router.post("/jobs/{job_id}/requirements", response_model=JobDetail, status_code=201)
def add_requirement(job_id: int, body: RequirementIn, session: Session = Depends(get_session)):
    """Adds one the extraction missed. It is never replaced by a later extraction."""
    job = _get_job(session, job_id)
    skill = extraction.get_or_create_skill(session, body.name, "other")
    existing = next((r for r in job.requirements if r.skill_id == skill.id), None)
    if existing is not None:
        existing.importance, existing.source = body.importance, "user"
    else:
        job.requirements.append(Requirement(skill=skill, importance=body.importance, evidence=None, source="user"))
    session.commit()
    return _to_out(job, JobDetail)


class RequirementUpdate(BaseModel):
    importance: Importance


@router.patch("/jobs/{job_id}/requirements/{requirement_id}", response_model=JobDetail)
def update_requirement(job_id: int, requirement_id: int, body: RequirementUpdate, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    req = next((r for r in job.requirements if r.id == requirement_id and r.active), None) or _missing("Requirement")
    req.importance, req.source = body.importance, "user"  # an edited one is kept like an added one
    session.commit()
    return _to_out(job, JobDetail)


@router.delete("/jobs/{job_id}/requirements/{requirement_id}", response_model=JobDetail)
def remove_requirement(job_id: int, requirement_id: int, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    req = next((r for r in job.requirements if r.id == requirement_id and r.active), None) or _missing("Requirement")
    req.source = "removed"  # remembered, so reading the description again doesn't add it back
    session.commit()
    return _to_out(job, JobDetail)


@router.post("/jobs/{job_id}/extract", response_model=JobDetail)
def extract_job(job_id: int, request: Request, session: Session = Depends(get_session)):
    """Reads the job's description again, e.g. after choosing another model."""
    job = _get_job(session, job_id)
    if not job.raw_text:
        raise HTTPException(422, "This job has no description. Paste it first.")
    queue_extraction(job)
    session.commit()
    start_extraction(request, job)
    return _to_out(job, JobDetail)


@router.post("/skill-gap/extract", response_model=GapOut)
def extract_all(request: Request, group_id: int | None = None, session: Session = Depends(get_session)):
    """Reads every target of the group again."""
    jobs = [j for j in _targets(session, group_id) if j.raw_text]
    for job in jobs:
        queue_extraction(job)
    session.commit()
    for job in jobs:
        start_extraction(request, job)
    return skill_gap(group_id, session)


# ---- AI settings


class ProviderSettings(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    # Write only: the key is never sent back, only whether one is saved.
    api_key: str | None = Field(default=None, max_length=500)


class SettingsOut(BaseModel):
    provider: str
    providers: dict[str, dict]


class SettingsIn(BaseModel):
    provider: str = Field(pattern="^(" + "|".join(ai.PROVIDERS) + ")$")
    providers: dict[str, ProviderSettings] = {}


def _settings(request: Request) -> ai.Settings:
    return request.app.state.ai_settings


def _public(data: dict) -> SettingsOut:
    providers = {}
    for name, config in data["providers"].items():
        public = {k: v for k, v in config.items() if k != "api_key"}
        if "api_key" in config:
            public["has_key"] = bool(config["api_key"])
        providers[name] = public
    return SettingsOut(provider=data["provider"], providers=providers)


@router.get("/ai/settings", response_model=SettingsOut, dependencies=[Depends(require_app_page)])
def get_ai_settings(request: Request):
    return _public(_settings(request).load())


def _merge(data: dict, providers: dict[str, ProviderSettings]) -> dict:
    for name, given in providers.items():
        if name not in ai.DEFAULTS:
            continue
        config = data["providers"][name]
        for field, value in given.model_dump(exclude_unset=True).items():
            if field not in config:
                continue
            if field == "api_key" and value is None:
                continue  # blank in the form: keep the saved key (sending "" removes it)
            config[field] = (value or "").strip()
    return data


@router.put("/ai/settings", response_model=SettingsOut, dependencies=[Depends(require_app_page)])
def save_ai_settings(body: SettingsIn, request: Request):
    store = _settings(request)
    data = _merge(store.load(), body.providers)
    data["provider"] = body.provider
    store.save(data)
    return _public(data)


class ModelsOut(BaseModel):
    models: list[str]


@router.post("/ai/models", response_model=ModelsOut, dependencies=[Depends(require_app_page)])
def list_models(body: SettingsIn, request: Request):
    """The models a provider offers, with the settings typed in the form (not saved yet)."""
    data = _merge(_settings(request).load(), body.providers)
    provider = ai._CLASSES[body.provider](data["providers"].get(body.provider, {}))
    try:
        return ModelsOut(models=provider.models())
    except ai.AIError as e:
        raise HTTPException(422, str(e)) from e


SAMPLE = """Requirements
- 3+ years of experience with Python and SQL
- Experience with PyTorch and Docker
Nice to have
- Kubernetes"""


class TestOut(BaseModel):
    used: str
    seconds: float
    found: list[str]


@router.post("/ai/test", response_model=TestOut, dependencies=[Depends(require_app_page)])
def test_ai(body: SettingsIn, request: Request):
    """Runs the model on a short sample posting, so the user sees it works before saving."""
    data = _merge(_settings(request).load(), body.providers)
    provider = ai._CLASSES[body.provider](data["providers"].get(body.provider, {}))
    started = time.monotonic()
    try:
        items = provider.extract(SAMPLE) if provider.name != "none" else []
    except ai.AIError as e:
        raise HTTPException(422, str(e)) from e
    if provider.name != "none" and not items:
        raise HTTPException(422, "The model answered but found nothing. Try a bigger model.")
    result = extraction.extract(SAMPLE, ai.Provider({})) if provider.name == "none" else None
    names = [i.name for i in result.items] if result else [i.name for i in items]
    return TestOut(used=provider.describe(), seconds=round(time.monotonic() - started, 1), found=names)
