"""Skill Gap: role groups, the skill tree, the skills the user connects to each target job added
up, and the AI settings used to write skill descriptions."""

import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobpilot import ai, skills
from jobpilot.api import _get_job, _to_out, get_session
from jobpilot.capture import require_app_page
from jobpilot.models import (
    Importance, Job, Requirement, RoleGroup, Skill, SkillEvent, SkillMark,
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


def find_skill(session: Session, key: str) -> Skill | None:
    """The skill with this key now, or before the user renamed it."""
    return session.scalar(select(Skill).where(Skill.key == key)) or session.scalar(
        select(Skill).where(Skill.old_keys.contains(f"\n{key}\n"))
    )


def get_or_create_skill(session: Session, name: str) -> Skill:
    """The skill with this name; a new one waits in Unsorted."""
    name = " ".join(name.split())
    skill = find_skill(session, skills.skill_key(name))
    if skill is None:
        skill = Skill(name=name, key=skills.skill_key(name))
        session.add(skill)
        session.flush()
    return skill


def _missing(what: str):
    raise HTTPException(404, f"{what} not found")


# ---- The gap list


def years_text(low: int | None, high: int | None) -> str | None:
    """(3, 5) -> '3-5', (2, None) -> '2+'."""
    if not low:
        return None
    return f"{low}–{high}" if high and high != low else f"{low}+"


class SkillRow(BaseModel):
    """A node of the tree (every node is a skill), with what the targets ask of it."""
    id: int
    name: str
    parent_id: int | None
    position: int
    # In the tree; the others wait in Unsorted.
    placed: bool
    # Only organizes ("Cloud"); never asked for itself.
    is_group: bool = False
    # A tool you can point to ("Docker"); otherwise a concept or practice ("Feature engineering").
    is_tool: bool = False
    mark: SkillMark | None
    plan_note: str
    jobs: int
    must: int
    nice: int
    # The years the targets ask for ("1+", "3–5"), and accepted fields for degrees.
    years: list[str]
    details: list[str]
    description: str = ""
    # The targets that ask for it, so a node can count the postings that ask for anything under it.
    job_ids: list[int] = []
    # The words in their descriptions it was picked from, each once.
    quotes: list[str] = []


def _row(skill: Skill, jobs: int = 0) -> SkillRow:
    return SkillRow(id=skill.id, name=skill.name, parent_id=skill.parent_id, position=skill.position,
                    placed=skill.placed, is_group=skill.is_group, is_tool=skill.is_tool, mark=skill.mark, plan_note=skill.plan_note, jobs=jobs, must=0, nice=0,
                    years=[], details=[], description=skill.description)


class Posting(BaseModel):
    id: int
    title: str
    company: str


class GapOut(BaseModel):
    targets: int
    # Share of the targets' requirements (must counted double) the user has; ignored skills left out.
    coverage: float | None
    skills: list[SkillRow]
    postings: list[Posting] = []


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
            skill = req.skill
            row = rows.get(skill.id) or rows.setdefault(skill.id, _row(skill))
            row.jobs += 1
            row.job_ids.append(job.id)
            if (y := years_text(req.min_years, req.max_years)) and y not in row.years:
                row.years.append(y)
            if req.evidence and req.evidence not in row.quotes:
                row.quotes.append(req.evidence)
            if req.detail and req.detail not in row.details:
                row.details.append(req.detail)
            if req.importance == Importance.MUST:
                row.must += 1
            else:
                row.nice += 1
            if skill.mark != SkillMark.IGNORE:
                total += WEIGHT[req.importance]
                covered += WEIGHT[req.importance] if skill.mark == SkillMark.HAVE else 0
    # The whole tree, so the page can show (and edit) it; nodes no target asks for count 0.
    for skill in session.scalars(select(Skill).where(Skill.placed.is_(True))):
        rows.setdefault(skill.id, _row(skill))
    return GapOut(
        targets=len(targets),
        coverage=covered / total if total else None,
        skills=sorted(rows.values(), key=lambda r: (-r.jobs, -r.must, r.name.casefold())),
        postings=[Posting(id=j.id, title=j.title, company=j.company.name) for j in targets],
    )


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
    parent_id: int | None
    placed: bool
    mark: SkillMark | None
    plan_note: str
    jobs: list[Evidence]
    history: list[MarkChange]


def _skill_detail(skill: Skill, group_id: int | None) -> SkillDetail:
    reqs = [
        r for r in skill.requirements
        if r.job.target_group_id is not None and (group_id is None or r.job.target_group_id == group_id)
    ]
    return SkillDetail(
        id=skill.id, name=skill.name, description=skill.description, parent_id=skill.parent_id, placed=skill.placed,
        mark=skill.mark, plan_note=skill.plan_note,
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
    is_tool: bool | None = None
    mark: SkillMark | None = None
    plan_note: str | None = Field(default=None, max_length=10_000)
    # Moving it: under parent_id (None: the top level), at index among its new siblings.
    # placed=False takes it out of the tree, to Unsorted.
    parent_id: int | None = None
    index: int | None = Field(default=None, ge=0)
    placed: bool | None = None


def _children(session: Session, parent_id: int | None) -> list[Skill]:
    where = Skill.parent_id.is_(None) if parent_id is None else Skill.parent_id == parent_id
    return list(session.scalars(select(Skill).where(where, Skill.placed.is_(True)).order_by(Skill.position, Skill.id)))


def _renumber(nodes: list[Skill]) -> None:
    for i, node in enumerate(nodes):
        node.position = i


def _place(session: Session, skill: Skill, parent_id: int | None, index: int | None) -> None:
    """Puts a skill in the tree under parent_id (None: the top level), at index among its siblings."""
    parent = session.get(Skill, parent_id) if parent_id is not None else None
    if parent_id is not None and (parent is None or not parent.placed):
        _missing("Parent")
    above = parent
    while above is not None:  # not under itself or one of its own children
        if above.id == skill.id:
            raise HTTPException(422, f"{skill.name} can't go under itself")
        above = above.parent
    if skill.placed:
        _renumber([s for s in _children(session, skill.parent_id) if s.id != skill.id])
    siblings = [s for s in _children(session, parent_id) if s.id != skill.id]
    siblings.insert(len(siblings) if index is None else min(index, len(siblings)), skill)
    skill.parent_id, skill.placed = parent_id, True
    _renumber(siblings)


def _unplace(session: Session, skill: Skill) -> None:
    """Out of the tree, to Unsorted; its children take its place."""
    if not skill.placed:
        return
    siblings = _children(session, skill.parent_id)
    at = siblings.index(skill)
    siblings[at:at + 1] = _children(session, skill.id)
    for child in siblings:
        child.parent_id = skill.parent_id
    _renumber(siblings)
    skill.parent_id, skill.placed, skill.position = None, False, 0


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
    if changes.get("is_tool") is not None and not skill.is_group:
        skill.is_tool = changes["is_tool"]
    if changes.get("name") and (name := " ".join(changes["name"].split())) != skill.name:
        key = skills.skill_key(name)
        other = find_skill(session, key)
        if other is not None and other.id != skill.id:
            raise HTTPException(409, f"There is already a skill called {other.name}")
        if key != skill.key:
            # Postings that still use the old name find it under the new one.
            skill.old_keys = (skill.old_keys or "\n") + f"{skill.key}\n"
            skill.key = key
        skill.name = name
    if changes.get("placed") is False:
        _unplace(session, skill)
    elif "parent_id" in changes or changes.get("index") is not None or changes.get("placed"):
        _place(session, skill, changes.get("parent_id", skill.parent_id if skill.placed else None), changes.get("index"))
    session.commit()
    return _skill_detail(skill, group_id)


def _asked(session: Session) -> dict[int, int]:
    """How many targets ask for each skill."""
    return dict(session.execute(
        select(Requirement.skill_id, func.count())
        .join(Job, Job.id == Requirement.job_id)
        .where(Job.target_group_id.is_not(None))
        .group_by(Requirement.skill_id)
    ).all())


@router.get("/skills", response_model=list[SkillRow])
def list_skills(session: Session = Depends(get_session)):
    """The whole tree in order, then the skills in Unsorted, with how many targets ask for each."""
    asked = _asked(session)
    every = session.scalars(select(Skill).order_by(Skill.position, func.lower(Skill.name))).all()
    children: dict[int | None, list[Skill]] = defaultdict(list)
    for s in every:
        if s.placed:
            children[s.parent_id].append(s)
    ordered: list[Skill] = []

    def walk(parent_id: int | None) -> None:
        for s in children[parent_id]:
            ordered.append(s)
            walk(s.id)

    walk(None)
    ordered += [s for s in every if not s.placed]
    return [_row(s, asked.get(s.id, 0)) for s in ordered]


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    index: int | None = Field(default=None, ge=0)
    is_group: bool = False
    is_tool: bool = False
    description: str = Field(default="", max_length=2000)


@router.post("/skills", response_model=list[SkillRow], status_code=201)
def add_skill(body: SkillIn, session: Session = Depends(get_session)):
    """A skill or group the user adds to the tree (an existing skill with that name is moved there)."""
    name = " ".join(body.name.split())
    if body.is_group:
        if (other := find_skill(session, skills.skill_key(name))) is not None:
            raise HTTPException(409, f"There is already a skill called {other.name}")
        skill = Skill(name=name, key=skills.skill_key(name), is_group=True)
        session.add(skill)
        session.flush()
    else:
        skill = get_or_create_skill(session, name)
    if body.description.strip():
        skill.description = body.description.strip()
    skill.is_tool = body.is_tool and not skill.is_group
    _place(session, skill, body.parent_id, body.index)
    session.commit()
    return list_skills(session)


# Removed skills, newest last, so the user can bring them back (Cmd+Z); kept while the app runs.
UNDO_LIMIT = 20


def _removed(request: Request) -> list[dict]:
    if not hasattr(request.app.state, "removed_skills"):
        request.app.state.removed_skills = []
    return request.app.state.removed_skills


def _snapshot(session: Session, skill: Skill) -> dict:
    """All a removed skill had: its place in the tree, what was under it, its jobs and its marks."""
    columns = ("id", "name", "key", "parent_id", "position", "placed", "is_group", "is_tool", "mark", "plan_note",
               "description", "old_keys", "created_at")
    return {
        "skill": {c: getattr(skill, c) for c in columns},
        "children": [c.id for c in _children(session, skill.id)] if skill.placed else [],
        "requirements": [
            {c: getattr(r, c) for c in ("job_id", "importance", "evidence", "evidence_at", "min_years", "max_years",
                                        "detail", "source")}
            for r in skill.requirements
        ],
        "events": [{c: getattr(e, c) for c in ("from_mark", "to_mark", "timestamp")} for e in skill.events],
    }


@router.delete("/skills/{skill_id}", response_model=list[SkillRow])
def remove_skill(skill_id: int, request: Request, session: Session = Depends(get_session)):
    """Takes a skill out of the tree (its children take its place), and off every job connected to it."""
    skill = session.get(Skill, skill_id) or _missing("Skill")
    snapshot = _snapshot(session, skill)
    _unplace(session, skill)
    session.delete(skill)
    session.commit()
    removed = _removed(request)
    removed.append(snapshot)
    del removed[:-UNDO_LIMIT]
    return list_skills(session)


class UndoOut(BaseModel):
    name: str
    skills: list[SkillRow]


@router.post("/skills/undo-remove", response_model=UndoOut)
def undo_remove(request: Request, session: Session = Depends(get_session)):
    """Brings back the last removed skill: in its place, with what was under it and its jobs."""
    removed = _removed(request)
    if not removed:
        raise HTTPException(404, "Nothing to undo")
    snap = removed[-1]
    data = snap["skill"]
    if session.scalar(select(Skill).where(Skill.key == data["key"])) is not None:
        removed.pop()
        raise HTTPException(409, f"{data['name']} is in the tree again, so it can't be brought back")
    fields = {k: v for k, v in data.items() if k not in ("id", "parent_id", "position", "placed")}
    skill = Skill(**fields)
    if session.get(Skill, data["id"]) is None:
        skill.id = data["id"]  # the same id, so links to it keep working
    session.add(skill)
    session.flush()
    if data["placed"]:
        parent = session.get(Skill, data["parent_id"]) if data["parent_id"] is not None else None
        parent_id = parent.id if parent is not None and parent.placed else None
        _place(session, skill, parent_id, data["position"])
        # What moved up when it was removed goes back under it, if it is still where it moved to.
        for child_id in snap["children"]:
            child = session.get(Skill, child_id)
            if child is not None and child.placed and child.parent_id == parent_id:
                _place(session, child, skill.id, None)
    jobs = {j.id for j in session.scalars(select(Job).where(Job.id.in_([r["job_id"] for r in snap["requirements"]])))}
    for r in snap["requirements"]:
        if r["job_id"] in jobs:
            skill.requirements.append(Requirement(**r))
    skill.events.extend(SkillEvent(**e) for e in snap["events"])
    session.commit()
    removed.pop()
    return UndoOut(name=skill.name, skills=list_skills(session))


# ---- A skill's connections to the postings that ask for it (made on the job)


class ConnectionUpdate(BaseModel):
    evidence: str | None = Field(default=None, max_length=500)
    importance: Importance | None = None


def _connectable(session: Session, skill_id: int, job_id: int) -> tuple[Skill, Job]:
    skill = session.get(Skill, skill_id) or _missing("Skill")
    if skill.is_group:
        raise HTTPException(422, f"{skill.name} is a group: connect postings to the skills in it")
    job = session.get(Job, job_id) or _missing("Job")
    return skill, job


@router.patch("/skills/{skill_id}/jobs/{job_id}", response_model=SkillDetail)
def update_connection(skill_id: int, job_id: int, body: ConnectionUpdate, group_id: int | None = None,
                      session: Session = Depends(get_session)):
    skill, job = _connectable(session, skill_id, job_id)
    req = next((r for r in job.requirements if r.skill_id == skill.id), None) or _missing("Connection")
    if body.evidence is not None:
        # Written by hand: no longer the words selected in the description.
        req.evidence, req.evidence_at = body.evidence.strip() or None, None
    if body.importance is not None:
        req.importance = body.importance
    session.commit()
    return _skill_detail(skill, group_id)


@router.delete("/skills/{skill_id}/jobs/{job_id}", response_model=SkillDetail)
def disconnect_job(skill_id: int, job_id: int, group_id: int | None = None, session: Session = Depends(get_session)):
    skill = session.get(Skill, skill_id) or _missing("Skill")
    for req in [r for r in skill.requirements if r.job_id == job_id]:
        session.delete(req)
    session.commit()
    session.refresh(skill)
    return _skill_detail(skill, group_id)


# ---- Descriptions written by the AI


DESCRIBE_SYSTEM = """You write the description of one node of the skill tree in a job-search app (Job Pilot).
The tree goes from general to specific; a skill is something job postings ask for, and a group only
organizes the skills in it. Write one or two plain sentences that say what it is, in the sense its place
in the tree gives it. No heading, no list, no quotes, no Markdown: only the description."""


class DescribeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    is_group: bool = False
    # Where it sits (or will sit): the node it is under; null at the top level or in Unsorted.
    parent_id: int | None = None
    # Editing an existing node: what is under it goes to the model too.
    skill_id: int | None = None


class DescribeOut(BaseModel):
    description: str
    used: str


def _describe_prompt(session: Session, body: DescribeIn) -> str:
    path: list[str] = []
    parent = session.get(Skill, body.parent_id) if body.parent_id is not None else None
    while parent is not None and len(path) < 20:
        path.insert(0, parent.name)
        parent = parent.parent
    lines = [f"{'Group' if body.is_group else 'Skill'}: {body.name.strip()}"]
    lines.append(f"Where it sits: {' › '.join(path)}" if path else "Where it sits: the top level of the tree")
    if body.skill_id is not None:
        under = list(session.scalars(
            select(Skill).where(Skill.parent_id == body.skill_id, Skill.placed.is_(True)).order_by(Skill.position, Skill.id)
        ))
        if under:
            lines.append(f"Under it: {', '.join(s.name for s in under)}")
    return "\n".join(lines)


@router.post("/ai/describe", response_model=DescribeOut, dependencies=[Depends(require_app_page)])
def describe(body: DescribeIn, request: Request, session: Session = Depends(get_session)):
    """Writes a description for a skill or group; the user edits it and saves it themselves."""
    provider = _settings(request).provider()
    if provider.name == "none":
        raise HTTPException(422, "Choose an AI model in the AI settings first.")
    try:
        reply = provider.chat(DESCRIBE_SYSTEM, [{"role": "user", "content": _describe_prompt(session, body)}])
    except ai.AIError as e:
        raise HTTPException(422, str(e)) from e
    reply = " ".join(reply.split()).strip('"')
    if not reply:
        raise HTTPException(422, "The model gave an empty answer. Try again.")
    return DescribeOut(description=reply[:2000], used=provider.describe())


# ---- A job's requirements


class RequirementIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    importance: Importance = Importance.MUST
    # The words in the description it was picked from, and where they start in it; only they are highlighted.
    evidence: str = Field(default="", max_length=500)
    evidence_at: int | None = Field(default=None, ge=0)


@router.post("/jobs/{job_id}/requirements", response_model=JobDetail, status_code=201)
def add_requirement(job_id: int, body: RequirementIn, session: Session = Depends(get_session)):
    """Connects a skill to the job, from the job's side; a name the tree doesn't have waits in Unsorted."""
    job = _get_job(session, job_id)
    skill = get_or_create_skill(session, body.name)
    if skill.is_group:
        raise HTTPException(422, f"{skill.name} is a group: add the skills in it")
    evidence = " ".join(body.evidence.split()) or None
    at = body.evidence_at if evidence else None
    existing = next((r for r in job.requirements if r.skill_id == skill.id), None)
    if existing is not None:
        existing.importance, existing.source = body.importance, "user"
        if evidence:
            existing.evidence, existing.evidence_at = evidence, at
    else:
        job.requirements.append(Requirement(skill=skill, importance=body.importance, evidence=evidence, evidence_at=at, source="user"))
    session.commit()
    return _to_out(job, JobDetail)


class RequirementUpdate(BaseModel):
    importance: Importance | None = None
    note: str | None = Field(default=None, max_length=5000)


@router.patch("/jobs/{job_id}/requirements/{requirement_id}", response_model=JobDetail)
def update_requirement(job_id: int, requirement_id: int, body: RequirementUpdate, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    req = next((r for r in job.requirements if r.id == requirement_id), None) or _missing("Requirement")
    if body.importance is not None:
        req.importance, req.source = body.importance, "user"
    if body.note is not None:
        req.note = body.note.strip()
    session.commit()
    return _to_out(job, JobDetail)


@router.delete("/jobs/{job_id}/requirements/{requirement_id}", response_model=JobDetail)
def remove_requirement(job_id: int, requirement_id: int, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    req = next((r for r in job.requirements if r.id == requirement_id), None) or _missing("Requirement")
    job.requirements.remove(req)
    session.delete(req)
    session.commit()
    return _to_out(job, JobDetail)


# ---- AI settings


class ProviderSettings(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    # Claude Code's program, when it isn't found by itself.
    path: str | None = Field(default=None, max_length=500)
    effort: str | None = Field(default=None, pattern="^(|" + "|".join(ai.EFFORTS) + ")$")
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


class TestOut(BaseModel):
    used: str
    seconds: float
    reply: str


@router.post("/ai/test", response_model=TestOut, dependencies=[Depends(require_app_page)])
def test_ai(body: SettingsIn, request: Request):
    """Asks the model for a one-line answer, so the user sees it works before saving."""
    data = _merge(_settings(request).load(), body.providers)
    provider = ai._CLASSES[body.provider](data["providers"].get(body.provider, {}))
    if provider.name == "none":
        raise HTTPException(422, "Choose an AI model to test.")
    started = time.monotonic()
    try:
        reply = provider.chat("Answer in one short sentence.", [{"role": "user", "content": "Say that you're ready."}])
    except ai.AIError as e:
        raise HTTPException(422, str(e)) from e
    if not reply.strip():
        raise HTTPException(422, "The model gave an empty answer. Try another model.")
    return TestOut(used=provider.describe(), seconds=round(time.monotonic() - started, 1), reply=reply.strip()[:300])
