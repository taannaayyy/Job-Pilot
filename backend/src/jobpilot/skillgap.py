"""Skill Gap: role groups, the requirements of their target jobs added up, the user's own marks,
and the AI settings that extraction uses."""

import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobpilot import ai, extraction, skills
from jobpilot.api import _get_job, _to_out, get_session, queue_extraction, start_extraction
from jobpilot.capture import require_app_page
from jobpilot.models import (
    ExtractionStatus, Importance, Job, Requirement, RoleGroup, Skill, SkillEvent, SkillGroup, SkillMark,
)
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


def years_text(low: int | None, high: int | None) -> str | None:
    """(3, 5) -> '3-5', (2, None) -> '2+'."""
    if not low:
        return None
    return f"{low}–{high}" if high and high != low else f"{low}+"


class SkillRow(BaseModel):
    id: int
    name: str
    category: str
    group_id: int | None
    parent_id: int | None
    mark: SkillMark | None
    plan_note: str
    jobs: int
    must: int
    nice: int
    # The years the targets ask for ("1+", "3–5"), and accepted fields for degrees.
    years: list[str]
    details: list[str]
    # Placed or added by the user; shown in the tree even when no target asks for it.
    placed: bool = False
    description: str = ""


class NodeOut(BaseModel):
    id: int
    key: str | None
    name: str
    description: str
    parent_id: int | None
    position: int
    skill_count: int


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
    # The whole tree, so the list can be shown in it.
    groups: list[NodeOut]


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
                SkillRow(id=skill.id, name=skill.name, category=skill.category, group_id=skill.group_id,
                         parent_id=skill.parent_id, mark=skill.mark, plan_note=skill.plan_note,
                         jobs=0, must=0, nice=0, years=[], details=[]),
            )
            row.jobs += 1
            if (y := years_text(req.min_years, req.max_years)) and y not in row.years:
                row.years.append(y)
            if req.detail and req.detail not in row.details:
                row.details.append(req.detail)
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
        groups=_groups(session),
    )


def _groups(session: Session) -> list[NodeOut]:
    counts = dict(session.execute(select(Skill.group_id, func.count()).group_by(Skill.group_id)).all())
    return [
        NodeOut(id=g.id, key=g.key, name=g.name, description=g.description, parent_id=g.parent_id,
                 position=g.position, skill_count=counts.get(g.id, 0))
        for g in session.scalars(select(SkillGroup).order_by(SkillGroup.position, SkillGroup.id))
    ]


class Evidence(BaseModel):
    job_id: int
    title: str
    company: str
    importance: Importance
    evidence: str | None
    years: str | None
    detail: str | None


class MarkChange(BaseModel):
    from_mark: SkillMark | None
    to_mark: SkillMark | None
    timestamp: datetime


class SkillDetail(BaseModel):
    id: int
    name: str
    description: str
    category: str
    group_id: int | None
    parent_id: int | None
    # The user placed it; extraction won't move it.
    group_locked: bool
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
        id=skill.id, name=skill.name, description=skill.description, category=skill.category,
        group_id=skill.group_id, parent_id=skill.parent_id, group_locked=skill.group_locked, mark=skill.mark, plan_note=skill.plan_note,
        jobs=[
            Evidence(job_id=r.job.id, title=r.job.title, company=r.job.company.name, importance=r.importance,
                     evidence=r.evidence, years=years_text(r.min_years, r.max_years), detail=r.detail)
            for r in sorted(reqs, key=lambda r: (r.importance != "must", r.job.title.casefold()))
        ],
        history=[MarkChange(from_mark=e.from_mark, to_mark=e.to_mark, timestamp=e.timestamp) for e in skill.events],
    )


@router.get("/skills/{skill_id}", response_model=SkillDetail)
def get_skill(skill_id: int, group_id: int | None = None, session: Session = Depends(get_session)):
    return _skill_detail(session.get(Skill, skill_id) or _missing("Skill"), group_id)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    mark: SkillMark | None = None
    plan_note: str | None = Field(default=None, max_length=10_000)
    # Moving it in the tree; extraction leaves it there afterwards.
    group_id: int | None = None
    parent_id: int | None = None


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
    if changes.get("description") is not None:
        skill.description = changes["description"].strip()
    if changes.get("name") and (name := " ".join(changes["name"].split())) != skill.name:
        key = skills.skill_key(name)
        other = extraction.find_skill(session, key)
        if other is not None and other.id != skill.id:
            raise HTTPException(409, f"There is already a skill called {other.name}")
        if key != skill.key:
            # Postings that still use the old name find it under the new one.
            skill.old_keys = (skill.old_keys or "\n") + f"{skill.key}\n"
            skill.key = key
        skill.name = name
    if "group_id" in changes:
        if changes["group_id"] is not None and session.get(SkillGroup, changes["group_id"]) is None:
            _missing("Group")
        skill.group_id, skill.group_locked = changes["group_id"], True
    if "parent_id" in changes:
        parent = changes["parent_id"]
        if parent is not None:
            other = session.get(Skill, parent) or _missing("Parent skill")
            # Not under itself, directly or through its children.
            while other is not None:
                if other.id == skill.id:
                    raise HTTPException(422, f"{skill.name} can't be under one of its own children")
                other = other.parent
        skill.parent_id, skill.group_locked = parent, True
    session.commit()
    return _skill_detail(skill, group_id)


def _asked(session: Session) -> dict[int, int]:
    """How many targets ask for each skill."""
    return dict(session.execute(
        select(Requirement.skill_id, func.count())
        .join(Job, Job.id == Requirement.job_id)
        .where(Requirement.source != "removed", Job.target_group_id.is_not(None))
        .group_by(Requirement.skill_id)
    ).all())


@router.get("/skills", response_model=list[SkillRow])
def list_skills(session: Session = Depends(get_session)):
    """Every skill, with how many targets ask for it (the tree shows those, and the ones the user placed)."""
    asked = _asked(session)
    return [
        SkillRow(id=s.id, name=s.name, category=s.category, group_id=s.group_id, parent_id=s.parent_id, mark=s.mark,
                 plan_note=s.plan_note, jobs=asked.get(s.id, 0), must=0, nice=0, years=[], details=[],
                 placed=s.group_locked, description=s.description)
        for s in session.scalars(select(Skill).order_by(func.lower(Skill.name)))
    ]


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    group_id: int | None = None
    parent_id: int | None = None


@router.post("/skills", response_model=list[SkillRow], status_code=201)
def add_skill(body: SkillIn, session: Session = Depends(get_session)):
    """A skill the user puts in the tree themselves (an existing one with that name is moved there)."""
    if body.group_id is not None and session.get(SkillGroup, body.group_id) is None:
        _missing("Group")
    if body.parent_id is not None and session.get(Skill, body.parent_id) is None:
        _missing("Parent skill")
    skill = extraction.get_or_create_skill(session, " ".join(body.name.split()))
    if body.parent_id != skill.id:
        skill.parent_id = body.parent_id
    skill.group_id, skill.group_locked = body.group_id, True
    session.commit()
    return list_skills(session)


@router.delete("/skills/{skill_id}", response_model=list[SkillRow])
def remove_skill(skill_id: int, session: Session = Depends(get_session)):
    """Takes a skill out of the tree, and off every job that asks for it."""
    skill = session.get(Skill, skill_id) or _missing("Skill")
    for req in skill.requirements:
        req.source = "removed"  # remembered, so reading the description again doesn't add it back
    for child in session.scalars(select(Skill).where(Skill.parent_id == skill.id)):
        child.parent_id = None
    if skill.requirements:
        skill.group_id, skill.parent_id, skill.group_locked = None, None, False
    else:
        session.delete(skill)
    session.commit()
    return list_skills(session)


# ---- The tree


class NodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    description: str = Field(default="", max_length=2000)


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: int | None = None
    # Where it goes among the (new) parent's children; sent together with parent_id when dragged.
    index: int | None = Field(default=None, ge=0)


def _siblings(session: Session, parent_id: int | None) -> list[SkillGroup]:
    return list(session.scalars(
        select(SkillGroup).where(SkillGroup.parent_id.is_(None) if parent_id is None else SkillGroup.parent_id == parent_id)
        .order_by(SkillGroup.position, SkillGroup.id)
    ))


def _renumber(groups: list[SkillGroup]) -> None:
    for i, g in enumerate(groups):
        g.position = i


@router.get("/skill-groups", response_model=list[NodeOut])
def list_groups_tree(session: Session = Depends(get_session)):
    return _groups(session)


@router.post("/skill-groups", response_model=list[NodeOut], status_code=201)
def create_group_node(body: NodeIn, session: Session = Depends(get_session)):
    if body.parent_id is not None and session.get(SkillGroup, body.parent_id) is None:
        _missing("Group")
    siblings = _siblings(session, body.parent_id)
    session.add(SkillGroup(name=" ".join(body.name.split()), description=body.description.strip(),
                           parent_id=body.parent_id, position=len(siblings)))
    session.commit()
    return _groups(session)


@router.patch("/skill-groups/{node_id}", response_model=list[NodeOut])
def update_group_node(node_id: int, body: NodeUpdate, session: Session = Depends(get_session)):
    node = session.get(SkillGroup, node_id) or _missing("Group")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name"):
        node.name = " ".join(changes["name"].split())
    if changes.get("description") is not None:
        node.description = changes["description"].strip()
    if "parent_id" in changes or changes.get("index") is not None:
        parent_id = changes.get("parent_id", node.parent_id)
        parent = session.get(SkillGroup, parent_id) if parent_id is not None else None
        if parent_id is not None and parent is None:
            _missing("Group")
        ancestor = parent
        while ancestor is not None:  # not into itself or its own subgroups
            if ancestor.id == node.id:
                raise HTTPException(422, "A group can't go inside itself")
            ancestor = session.get(SkillGroup, ancestor.parent_id) if ancestor.parent_id else None
        if parent_id != node.parent_id:
            _renumber([g for g in _siblings(session, node.parent_id) if g.id != node.id])
        siblings = [g for g in _siblings(session, parent_id) if g.id != node.id]
        index = changes.get("index")
        siblings.insert(len(siblings) if index is None else min(index, len(siblings)), node)
        node.parent_id = parent_id
        _renumber(siblings)
    session.commit()
    return _groups(session)


@router.delete("/skill-groups/{node_id}", response_model=list[NodeOut])
def delete_group_node(node_id: int, session: Session = Depends(get_session)):
    """Its subgroups and skills move up to its parent (or out of the tree, as unsorted)."""
    node = session.get(SkillGroup, node_id) or _missing("Group")
    siblings = [g for g in _siblings(session, node.parent_id) if g.id != node.id]
    for child in _siblings(session, node.id):
        child.parent_id = node.parent_id
        siblings.append(child)
    for skill in session.scalars(select(Skill).where(Skill.group_id == node.id)):
        skill.group_id = node.parent_id
    session.flush()
    session.delete(node)
    _renumber(siblings)
    session.commit()
    return _groups(session)


# ---- Recommendations for the tree


def tree_text(session: Session) -> str:
    """The whole tree with the skills filed in it, for the model."""
    groups = session.scalars(select(SkillGroup).order_by(SkillGroup.position, SkillGroup.id)).all()
    all_skills = session.scalars(select(Skill)).all()
    asked = defaultdict(int)
    for req in session.scalars(select(Requirement)):
        if req.active:
            asked[req.skill_id] += 1
    in_use = [s for s in all_skills if asked[s.id] or s.group_locked]
    lines: list[str] = []

    by_id = {s.id: s for s in all_skills}

    def skill_lines(items: list[Skill], depth: int) -> None:
        for s in sorted(items, key=lambda s: (-asked[s.id], s.name.casefold())):
            parent = by_id.get(s.parent_id) if s.parent_id else None
            under = f", belongs to {parent.name}" if parent and parent not in items else ""
            meaning = f" — {s.description}" if s.description else ""
            lines.append("  " * depth + f"- {s.name} (in {asked[s.id]} job{'s' if asked[s.id] != 1 else ''}{under}){meaning}")
            # Its children filed in the same group; one in another group is listed there.
            skill_lines([c for c in in_use if c.parent_id == s.id and c.group_id == s.group_id], depth + 1)

    def group_lines(parent_id: int | None, depth: int) -> None:
        for g in [g for g in groups if g.parent_id == parent_id]:
            lines.append("  " * depth + f"[{g.name}]" + (f" — {g.description}" if g.description else ""))
            group_lines(g.id, depth + 1)
            here = [s for s in in_use if s.group_id == g.id]
            skill_lines([s for s in here if s.parent_id not in {x.id for x in here}], depth + 1)

    group_lines(None, 0)
    unsorted = [s for s in in_use if s.group_id is None]
    if unsorted:
        lines.append("[Unsorted]")
        skill_lines(unsorted, 1)
    return "\n".join(lines)


CHAT_SYSTEM = """You help the user organize the tree their job-search app (Job Pilot) files job requirements in.
The app reads job postings the user is aiming for and files each requirement (skill, technology, knowledge area,
years of experience, degree, language) in this tree, so the user can see which areas they need to work on.
Group descriptions are also shown to the AI model that files new requirements.

The user's tree, with the requirements now filed in it ([group], then its skills):

{tree}

Recommend concrete changes: groups to add, rename, split, merge, move or delete; group descriptions that would
help the filing; skills in the wrong group or under the wrong parent; duplicates to merge. Use the exact names
from the tree, keep it short, and order by impact. The user makes the changes in the app themselves."""


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20_000)


class ChatIn(BaseModel):
    provider: str | None = Field(default=None, pattern="^(" + "|".join(ai.PROVIDERS) + ")$")
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


class ChatOut(BaseModel):
    reply: str
    used: str


@router.post("/ai/chat", response_model=ChatOut, dependencies=[Depends(require_app_page)])
def chat(body: ChatIn, request: Request, session: Session = Depends(get_session)):
    """One turn of the recommendation chat; the whole tree goes with every turn."""
    provider = _settings(request).provider(body.provider)
    if provider.name == "none":
        raise HTTPException(422, "Choose an AI model for this: the dictionary can't give recommendations.")
    try:
        reply = provider.chat(CHAT_SYSTEM.format(tree=tree_text(session)), [m.model_dump() for m in body.messages])
    except ai.AIError as e:
        raise HTTPException(422, str(e)) from e
    if not reply.strip():
        raise HTTPException(422, "The model gave an empty answer. Try again.")
    return ChatOut(reply=reply.strip(), used=provider.describe())


# ---- A job's requirements


class RequirementIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    importance: Importance = Importance.MUST


@router.post("/jobs/{job_id}/requirements", response_model=JobDetail, status_code=201)
def add_requirement(job_id: int, body: RequirementIn, session: Session = Depends(get_session)):
    """Adds one the extraction missed. It is never replaced by a later extraction."""
    job = _get_job(session, job_id)
    skill = extraction.get_or_create_skill(session, body.name)
    known = skills.lookup(skill.name)
    tree = extraction.Tree.load(session)
    extraction.file_skill(session, skill, tree, tree.id_of_key.get(known[1]) if known else None,
                          skills.PARENTS.get(skill.name), False)
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
    # Claude Code's program, when it isn't found by itself.
    path: str | None = Field(default=None, max_length=500)
    effort: str | None = Field(default=None, pattern="^(|" + "|".join(ai.EFFORTS) + ")$")
    model_decides: bool | None = None
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
            if field == "model_decides":
                if value is not None:
                    config[field] = value
                continue
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
