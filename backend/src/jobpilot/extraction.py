"""Turns a job description into requirements: the dictionary finds the skills it knows, the chosen
model (if any) adds what the dictionary doesn't know, and both are merged under one name per skill.
The dictionary decides everything about the skills it knows; small models judge must/nice less
reliably and turn tasks into skills ("Monitor model performance" -> "Monitoring"). So the model
only adds skills the dictionary doesn't know, and only ones the posting actually names. Runs one job at a time in a background thread, because a local model
can take a minute per posting."""

import logging
import queue
import re
import threading
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobpilot import skills
from jobpilot.ai import AIError, Provider, Settings
from jobpilot.db import utcnow
from jobpilot.linkedin import fold
from jobpilot.models import ExtractionStatus, Importance, Job, Requirement, Skill

log = logging.getLogger(__name__)

MAX_NAME_WORDS = 4
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
    -> ['data preprocessing', 'feature engineering', 'model training']. A part followed by its own
    examples ('cloud environments (Azure, AWS)', 'tools such as Tableau') is a category, not a skill."""
    name = re.sub(r"[^,;()]*\([^)]*,[^)]*\)", "", name)  # "cloud environments (Azure, AWS)"
    name = re.sub(r"[^,;]*\b(?:such as|e\.g\.|including|like)\b.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\([^)]*\)", "", name)  # "(EDA)"
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
    category: str
    importance: Importance
    evidence: str
    source: str  # "dictionary" or "model"


@dataclass
class Result:
    items: list[Item]
    used: str
    # Set when the model couldn't be used and only the dictionary ran.
    warning: str | None = None


def extract(text: str, provider: Provider) -> Result:
    found: dict[str, Item] = {}

    def put(name: str, category: str, importance: Importance, evidence: str, source: str) -> None:
        key = skills.skill_key(name)
        current = found.get(key)
        if current is None:
            found[key] = Item(name, category, importance, evidence, source)
        elif current.source == "model" and importance == Importance.MUST:
            current.importance = importance  # named twice by the model: the stronger one

    for f in skills.find(text):
        put(f.name, f.category, f.importance, f.evidence, "dictionary")

    used, warning = "Dictionary", None
    if provider.name != "none":
        try:
            model_items = provider.extract(text)
            used = f"Dictionary + {provider.describe()}"
        except AIError as e:
            model_items, warning = [], str(e)
        text_words = set(_words(text))
        for m in model_items:
            for name in _parts(re.sub(r"\s+", " ", m.name)):
                # A skill the dictionary knows ("torch", "BSc", "1+ years") was found by the
                # dictionary already, or isn't in the posting.
                if skills.lookup(name) or skills.find(name):
                    continue
                if fold(name) in _GENERIC:
                    continue
                if len(name.split()) <= MAX_NAME_WORDS and _grounded(name, text_words):
                    put(name[0].upper() + name[1:], m.category, m.importance, m.evidence or name, "model")
    return Result(list(found.values()), used, warning)


def get_or_create_skill(session: Session, name: str, category: str) -> Skill:
    name = (skills.lookup(name) or (name.strip(), category))[0]
    key = skills.skill_key(name)
    skill = session.scalar(select(Skill).where(Skill.key == key))
    if skill is None:
        skill = Skill(name=name, key=key, category=category)
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
        skill = get_or_create_skill(session, item.name, item.category)
        if skill.id in user_skill_ids:
            continue
        user_skill_ids.add(skill.id)
        job.requirements.append(
            Requirement(skill=skill, importance=item.importance, evidence=item.evidence[:500], source=item.source)
        )
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
        try:
            result = extract(text, self.settings.provider())
        except AIError as e:  # e.g. Ollama has no models: still save the dictionary's findings
            result = extract(text, Provider({}))
            result.warning = str(e)
        with self.sessions() as session:
            job = session.get(Job, job_id)
            # Cancelled, or the description changed meanwhile (it is queued again then).
            if job is None or job.extraction_status != ExtractionStatus.RUNNING or job.raw_text != text:
                return
            save(session, job, result)
            session.commit()
