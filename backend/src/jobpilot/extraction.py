"""Turns a job description into requirements: the dictionary finds the skills it knows, the chosen
model (if any) adds what the dictionary doesn't know, and both are merged under one name per skill.
The dictionary names the skills it knows, so spellings stay merged. Whether such a skill is a must
or a nice to have is the dictionary's call (its section rules) unless the provider's model_decides
is on: strong models read context the rules can't ("these lines after the duties are a plus"),
small local ones judge it worse. Models only add skills the dictionary doesn't know, and only ones
the posting actually names, so a task ("Monitor model performance") doesn't become a skill.

The tree is the user's (taxonomy.py, then Edit tree) and readings never change it. The model sees
it and writes a posting's skill the way the tree names it ("YOLOv8" is YOLO); a skill the tree
doesn't have is saved in Unsorted, for the user to place. Years go on the skill they're about.
Runs one job at a time in a background thread, because a model can take a minute per posting."""

import logging
import queue
import re
import threading
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobpilot import ai, skills, taxonomy
from jobpilot.ai import AIError, Provider, Settings
from jobpilot.db import utcnow
from jobpilot.linkedin import fold
from jobpilot.models import ExtractionStatus, Importance, Job, Requirement, Skill

log = logging.getLogger(__name__)

MAX_NAME_WORDS = 4
# Degrees come from the dictionary's rules (which one is required, which a plus).
_DEGREE = re.compile(r"degree|bachelor|master'?s|ph\.?d|\bb\.?sc?\b|\bm\.?sc?\b|diploma", re.IGNORECASE)
# One word too general to be a skill to learn: "Automation", "Analysis".
_GENERIC = {
    "automation", "analysis", "analytics", "data", "models", "modeling", "modelling", "insights", "solutions",
    "reporting", "reports", "projects", "documentation", "research", "development", "engineering", "software",
    "design", "operations", "support", "business", "technology", "technologies", "tools", "systems", "processes",
}
# Words that say how much of a skill, not which: "Strong knowledge of X" is X.
_FILLER = {
    "a", "an", "and", "or", "of", "the", "in", "on", "with", "for", "to", "at", "as",
    "knowledge", "experience", "skill", "skills", "understanding", "ability", "proficiency",
    "familiarity", "strong", "good", "solid", "basic", "advanced", "hands", "using",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", fold(text))


# "Hands-on experience with", "Good knowledge of", "Proficiency in"
_LEAD = re.compile(
    r"^(?:(?:good|strong|solid|basic|advanced|proven|deep|hands[\s-]on|working|practical)\s+)*"
    r"(?:knowledge|experience|understanding|proficiency|familiarity|expertise|background)\s+(?:of|with|in)\s+",
    re.IGNORECASE,
)


def _parts(name: str) -> list[str]:
    """'Hands-on experience with data preprocessing, feature engineering and model training'
    -> ['data preprocessing', 'feature engineering', 'model training']."""
    # "Cloud environments (Azure, AWS)" and "tools such as Tableau": the examples are found on their own.
    name = re.sub(r"\s*\b(?:such as|e\.g\.|including|like)\b[^,;]*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\([^)]*\)", "", name)  # "(EDA)", "(Azure, AWS)"
    parts = []
    for part in re.split(r",|;|\band\b|\bor\b", _LEAD.sub("", name.strip())):
        part = _LEAD.sub("", part.strip(" .:-"))
        part = re.sub(r"^(?:(?:good|strong|solid|basic|advanced|deep|analytical)\s+)+(?=\w+\s)", "", part, flags=re.IGNORECASE)
        if part:
            parts.append(part.strip())
    return parts


def _grounded(name: str, text_words: set[str]) -> bool:
    """Every word of the name is in the posting ("Report preparation" is not grounded in
    "Prepare reports": the posting asks for the task, not a skill of that name)."""
    words = [w for w in _words(name) if w not in _FILLER]
    return bool(words) and all(w in text_words or w + "s" in text_words or w.rstrip("s") in text_words for w in words)


@dataclass
class Item:
    name: str
    importance: Importance
    evidence: str
    source: str  # "dictionary" or "model"
    min_years: int | None = None
    max_years: int | None = None
    detail: str | None = None


@dataclass
class Result:
    items: list[Item]
    used: str
    # Set when the model couldn't be used and only the dictionary ran.
    warning: str | None = None


@dataclass
class Tree:
    """The user's tree as the model sees it (indented names, [groups] in brackets), and the keys of
    its skills (groups are never asked for)."""

    text: str
    keys: set[str] = field(default_factory=set)

    @classmethod
    def default(cls) -> "Tree":
        return cls(taxonomy.TREE, {skills.skill_key(name) for name, _, _, group in taxonomy.nodes() if not group})

    @classmethod
    def load(cls, session: Session) -> "Tree":
        placed = session.scalars(select(Skill).where(Skill.placed.is_(True)).order_by(Skill.position, Skill.id)).all()
        children: dict[int | None, list[Skill]] = {}
        for s in placed:
            children.setdefault(s.parent_id, []).append(s)
        lines: list[str] = []

        def walk(parent_id: int | None, depth: int) -> None:
            for s in children.get(parent_id, []):
                lines.append("  " * depth + (f"[{s.name}]" if s.is_group else s.name))
                walk(s.id, depth + 1)

        walk(None, 0)
        return cls("\n".join(lines), {s.key for s in placed if not s.is_group})


_OVERALL_KEY = skills.skill_key(taxonomy.OVERALL_EXPERIENCE)


def extract(text: str, provider: Provider, trace: list[str] | None = None, tree: Tree | None = None) -> Result:
    """trace, when given, collects every decision with its reason (see tune.py)."""
    tree = tree or Tree.default()
    found: dict[str, Item] = {}

    def note(line: str) -> None:
        if trace is not None:
            trace.append(line)

    def put(item: Item) -> None:
        key = skills.skill_key(item.name)
        current = found.get(key)
        if current is None:
            found[key] = item
        elif current.source == "model" and item.importance == Importance.MUST:
            current.importance = item.importance  # named twice by the model: the stronger one

    def years(m) -> str:
        return f" [{m.min_years}{'-' + str(m.max_years) if m.max_years else '+'} yrs]" if m.min_years else ""

    for f in skills.find(text):
        put(Item(f.name, f.importance, f.evidence, "dictionary", min_years=f.min_years, max_years=f.max_years,
                 detail=f.detail))
        note(f"dictionary  {f.importance:4}  {f.name}{years(f)}  <- {f.evidence[:80]!r}")

    used, warning = "Dictionary", None
    if provider.name != "none":
        try:
            model_items = provider.extract(text, tree.text)
            used = f"Dictionary + {provider.describe()}"
        except AIError as e:
            model_items, warning = [], str(e)
            note(f"model failed: {e}")
        text_words = set(_words(text))
        model_says: dict[str, Importance] = {}  # dictionary skills the model named, and how
        for m in model_items:
            note(f"model said  {m.importance:4}  {m.name!r}{years(m)}  <- {m.evidence[:80]!r}")
            # "Professional experience, 3+ years": overall years, which the dictionary may have too.
            if m.min_years and "experience" in fold(m.name) and not skills.find(m.name):
                current = found.get(_OVERALL_KEY)
                if current is None:
                    put(Item(taxonomy.OVERALL_EXPERIENCE, m.importance, m.evidence, "model",
                             min_years=m.min_years, max_years=m.max_years))
                    note("   overall experience: added")
                elif current.min_years is None:
                    current.min_years, current.max_years = m.min_years, m.max_years
                continue
            name = re.sub(r"\s+", " ", m.name)
            # A skill of the tree, as the tree writes it ("Data structures and algorithms"): kept whole.
            for name in [name] if skills.skill_key(name) in tree.keys else _parts(name):
                in_tree = skills.skill_key(name) in tree.keys
                known_name = skills.lookup(name)
                known = [known_name] if known_name else [] if in_tree else [f.name for f in skills.find(name)]
                # The model may map the posting's words onto a skill of the tree ("deep neural networks"
                # is Deep learning) when the words it quotes are in the posting.
                mapped = in_tree and _grounded(m.evidence, text_words)
                if known and (not mapped or skills.skill_key(known[0]) in found):
                    # A skill the dictionary knows ("torch", "BSc") was found by the dictionary
                    # already, or isn't in the posting; the model can only add years and judgement.
                    for known_name in known:
                        key = skills.skill_key(known_name)
                        if known_name not in skills.DEGREES:  # "BSc or MSc" keeps the degree rule
                            model_says[key] = Importance.MUST if Importance.MUST in (model_says.get(key), m.importance) else m.importance
                        if key in found:
                            item = found[key]
                            if item.min_years is None and m.min_years:
                                item.min_years, item.max_years = m.min_years, m.max_years
                            if known_name in skills.DEGREES and not item.detail and m.detail:
                                item.detail = m.detail
                    note(f"   {name!r}: the dictionary's {', '.join(known)}")
                    continue
                if _DEGREE.search(name):
                    note(f"   {name!r}: dropped, degrees come from the dictionary")
                elif fold(name) in _GENERIC:
                    note(f"   {name!r}: dropped, too general")
                elif len(name.split()) > MAX_NAME_WORDS:
                    note(f"   {name!r}: dropped, longer than {MAX_NAME_WORDS} words")
                elif not (mapped if in_tree else _grounded(name, text_words)):
                    note(f"   {name!r}: dropped, not all its words are in the posting")
                else:
                    put(Item(known_name or name[0].upper() + name[1:], m.importance, m.evidence or name, "model",
                             min_years=m.min_years, max_years=m.max_years, detail=m.detail or None))
                    note(f"   {name!r}: added{' (in the tree)' if in_tree else ''}")
        if provider.model_decides:
            for key, importance in model_says.items():
                if key in found and found[key].source == "dictionary":
                    if found[key].importance != importance:
                        note(f"model decides: {found[key].name} {found[key].importance} -> {importance}")
                    found[key].importance = importance
    return Result(list(found.values()), used, warning)


def find_skill(session: Session, key: str) -> Skill | None:
    """The skill with this key now, or before the user renamed it."""
    return session.scalar(select(Skill).where(Skill.key == key)) or session.scalar(
        select(Skill).where(Skill.old_keys.contains(f"\n{key}\n"))
    )


def get_or_create_skill(session: Session, name: str) -> Skill:
    """The skill under its dictionary name; a new one waits in Unsorted."""
    name = skills.lookup(name) or name.strip()
    key = skills.skill_key(name)
    skill = find_skill(session, key)
    if skill is None:
        skill = Skill(name=name, key=key)
        session.add(skill)
        session.flush()
    return skill


def save(session: Session, job: Job, result: Result) -> None:
    """Replaces what extraction found before; what the user added, edited or removed stays."""
    kept = [r for r in job.requirements if r.source in ("user", "removed")]
    user_skill_ids = {r.skill_id for r in kept}
    job.requirements = kept
    session.flush()
    for item in result.items:
        skill = get_or_create_skill(session, item.name)
        if skill.is_group:  # "Cloud" organizes the tree; a posting asks for what is in it
            continue
        if skill.id in user_skill_ids:
            continue
        user_skill_ids.add(skill.id)
        job.requirements.append(Requirement(
            skill=skill, importance=item.importance, evidence=item.evidence[:500], source=item.source,
            min_years=item.min_years, max_years=item.max_years, detail=(item.detail or None) and item.detail[:500],
        ))
    job.extraction_status = ExtractionStatus.DONE
    job.extraction_error = result.warning[:500] if result.warning else None
    job.extracted_at = utcnow()
    job.extracted_with = result.used


class Worker:
    """Extracts queued jobs one by one. inline=True runs them right away (tests)."""

    def __init__(self, sessions: sessionmaker, settings: Settings, inline: bool = False):
        self.sessions = sessions
        self.settings = settings
        self.inline = inline
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Picks up jobs left waiting when the app was last closed."""
        with self.sessions() as session:
            waiting = session.scalars(
                select(Job.id).where(Job.extraction_status.in_([ExtractionStatus.PENDING, ExtractionStatus.RUNNING]))
            ).all()
        for job_id in waiting:
            self.enqueue(job_id)

    def enqueue(self, job_id: int) -> None:
        """The caller has already set the job's status to pending."""
        if self.inline:
            self.run(job_id)
            return
        self._queue.put(job_id)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="extraction", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                job_id = self._queue.get(timeout=5)
            except queue.Empty:
                return
            try:
                self.run(job_id)
            except Exception:
                log.exception("extraction of job %s failed", job_id)

    def run(self, job_id: int) -> None:
        with self.sessions() as session:
            job = session.get(Job, job_id)
            if job is None or job.extraction_status not in (ExtractionStatus.PENDING, ExtractionStatus.RUNNING):
                return
            if not (job.raw_text or "").strip():
                job.extraction_status, job.extraction_error = ExtractionStatus.FAILED, "No job description saved"
                session.commit()
                return
            job.extraction_status = ExtractionStatus.RUNNING
            session.commit()
            text = job.raw_text
            tree = Tree.load(session)
        try:
            result = extract(text, self.settings.provider(), tree=tree)
        except AIError as e:  # e.g. Ollama has no models: still save the dictionary's findings
            result = extract(text, Provider({}), tree=tree)
            result.warning = str(e)
        with self.sessions() as session:
            job = session.get(Job, job_id)
            # Cancelled, or the description changed meanwhile (it is queued again then).
            if job is None or job.extraction_status != ExtractionStatus.RUNNING or job.raw_text != text:
                return
            save(session, job, result)
            session.commit()
