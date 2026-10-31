"""The skill tree a new database starts with: a general skeleton for any field. The user grows it
from their own postings (skills a posting asks for that it lacks wait in Unsorted) and changes it on
the Skill Gap page; this text is only where it starts, and an existing tree never changes with it.
A node is a skill, which postings ask for and which can hold other skills, or a [group], which only
organizes ("Cloud") and is never asked for itself. A node counts the postings that ask for it or
for anything under it.

Two spaces of indent are one level deeper; [brackets] mark a group."""

TREE = """
[Technologies]
  [Programming languages]
    Python
    JavaScript
    Java
    SQL
  [Databases]
    Relational databases
    NoSQL
  [Cloud]
    AWS
    Azure
    Google Cloud
  [DevOps]
    Docker
    Git
    CI/CD
  [Software engineering]
    APIs
    System design
    Software testing
[Domain knowledge]
[Background]
  [Experience]
    Professional experience
  [Education]
    Bachelor's degree
    Master's degree
    PhD
  [Spoken languages]
    English
[Soft skills]
  Communication
  Problem solving
  Analytical thinking
  Teamwork
  Leadership
"""

OVERALL_EXPERIENCE = "Professional experience"


def nodes(text: str = TREE):
    """Yields (name, parent name or None, position among its siblings, is a group) in order."""
    path: list[str] = []
    counts: dict[str | None, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        depth = (len(line) - len(line.lstrip(" "))) // 2
        del path[depth:]
        parent = path[-1] if path else None
        position = counts.get(parent, 0)
        counts[parent] = position + 1
        name = line.strip()
        group = name.startswith("[") and name.endswith("]")
        name = name.strip("[]")
        yield name, parent, position, group
        path.append(name)
