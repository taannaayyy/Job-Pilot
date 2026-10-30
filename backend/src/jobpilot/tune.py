"""Shows how a job description is read, step by step, without saving anything. For tuning the
prompt (ai.py: PROMPT, SYSTEM), the dictionary (skills.py) and the merge rules (extraction.py).

    uv run python -m jobpilot.tune 12                  # job 12 from the app's database
    uv run python -m jobpilot.tune posting.txt         # any text file
    uv run python -m jobpilot.tune 12 --provider none  # dictionary only
    uv run python -m jobpilot.tune 12 --model haiku    # another model than the saved one
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from jobpilot import ai, config, extraction
from jobpilot.db import make_engine, make_sessionmaker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a job id, or a text file with a job description")
    parser.add_argument("--provider", choices=ai.PROVIDERS, help="default: the one chosen in the app")
    parser.add_argument("--model", help="default: the one chosen in the app")
    parser.add_argument("--prompt", action="store_true", help="also print the prompt sent to the model")
    args = parser.parse_args()

    db = config.db_path()
    if args.source.isdigit():
        row = sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(
            "SELECT title, raw_text FROM job WHERE id = ?", (int(args.source),)
        ).fetchone()
        if not row or not row[1]:
            sys.exit(f"Job {args.source} has no description in {db}")
        title, text = row
    else:
        title, text = args.source, Path(args.source).read_text()

    with make_sessionmaker(make_engine(db))() as session:
        tree = extraction.Tree.load(session)
    settings = ai.Settings(db.parent / "ai-settings.json")
    overrides = {"model": args.model} if args.model else {}
    provider = settings.provider(args.provider, overrides)
    if args.prompt:
        print("---- system prompt\n" + ai.SYSTEM + "\n---- prompt\n" + ai.prompt(tree.text) + "<the job description>\n")

    print(f"---- {title}: {provider.describe()}, the model decides must/nice: {provider.model_decides}\n")
    trace: list[str] = []
    started = time.monotonic()
    result = extraction.extract(text, provider, trace, tree)
    print("\n".join(trace))
    print(f"\n---- result ({time.monotonic() - started:.1f}s, {result.used}){' WARNING: ' + result.warning if result.warning else ''}")
    def show(i):
        y = f" {i.min_years}{'-' + str(i.max_years) if i.max_years else '+'}y" if i.min_years else ""
        return f"{i.name}{y}{' (nice)' if i.importance == 'nice' else ''}{'*' if i.source == 'model' else ''}"
    in_tree = [i for i in result.items if extraction.skills.skill_key(i.name) in tree.keys]
    print("In the tree: " + ", ".join(show(i) for i in in_tree))
    print("Unsorted: " + ", ".join(show(i) for i in result.items if i not in in_tree))
    print("* added by the model · (nice) nice to have")


if __name__ == "__main__":
    main()
