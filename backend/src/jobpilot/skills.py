"""Skill names: "pytorch" and "PyTorch" are one skill."""

import re

from jobpilot.linkedin import fold


def skill_key(name: str) -> str:
    """'PyTorch', ' pytorch ' -> 'pytorch'. Keeps + and # so C++ and C# stay apart from C."""
    text = fold(name).replace("&", " and ")
    text = re.sub(r"[^\w+#./ -]", " ", text)
    return re.sub(r"[\s_-]+", " ", text).strip(" .")
