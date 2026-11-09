"""Topic -> validated script.json. Loop: generate -> validate -> feed problems back."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .llm import generate_structured
from .runner import SKILL_DIR
from .schemas import ScriptDraft, check_script, repair_caps, to_script_json

SYSTEM = """You write scripts for 35-second faceless YouTube Shorts (vertical, 'Inside Out' flat 2D explainer style).
Rules:
- Talk like a person to a friend: full flowing sentences with connecting words ("Well,", "but", "so", "which means").
- 90-110 words total. Each entry in `lines` is one CUT (1.5-3.5 s of picture): split sentences into 1-3 lines at natural pauses.
- Structure: hook question -> escalation -> a myth or surprise -> a twist -> a punchy last line that loops back to the hook.
- In `text`, write every number as words ("seven"). In `caps`, use 1-3 word chunks separated by " | ", EXACTLY one *highlighted word per chunk, uppercase, e.g. "WHAT *HAPPENS | IF YOU *SWALLOW | YOUR *GUM?".
- Only claims you are confident are accurate. `sources` = 2-4 specific, real references (institution/journal/article title) that support the key claims. If unsure about a claim, leave it out.
- Original writing only. No gore, no scary misinformation."""

SYSTEM += """

Exact caption format examples (different topic):
text: "Well, it slides down your throat and lands right in your stomach,"
caps: "WELL, IT *SLIDES | DOWN YOUR *THROAT | RIGHT IN YOUR *STOMACH"
text: "where strong acid gets to work on it."
caps: "WHERE STRONG *ACID | GETS TO *WORK"
text: "So maybe, just spit it out."
caps: "SO *MAYBE... | SPIT IT *OUT"
Every chunk has 1-3 words and exactly ONE word starting with *. Never leave a chunk without a *."""

EXAMPLE = Path(SKILL_DIR) / "styles" / "inside-out" / "example"


def write_script(topic: str, max_tries: int = 5, escalate_after: int = 3) -> ScriptDraft:
    base = f"Topic: {topic}\nWrite the script."
    prompt = base
    for attempt in range(1, max_tries + 1):
        task = "script" if attempt <= escalate_after else "script_hard"   # cheap model first, strong model last
        draft = repair_caps(generate_structured(prompt, ScriptDraft, system=SYSTEM, task=task))
        problems = check_script(draft)
        print(f"[script] attempt {attempt} ({task}): {len(problems)} problem(s)")
        if not problems:
            return draft
        prompt = (
            f"{base}\n\nYour previous attempt:\n{draft.model_dump_json(indent=1)}\n\n"
            "Fix ALL of these problems and return the full corrected script:\n- " + "\n- ".join(problems)
        )
    raise RuntimeError("Could not produce a valid script:\n- " + "\n- ".join(problems))

def make_project(project: Path) -> None:
    if project.exists():
        raise SystemExit(f"{project} already exists; choose a new name.")
    shutil.copytree(EXAMPLE, project)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--project", type=Path, required=True)
    a = ap.parse_args()

    draft = write_script(a.topic)
    make_project(a.project)
    (a.project / "script.json").write_text(
        json.dumps(to_script_json(draft), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {a.project / 'script.json'}")
    for l in draft.lines:
        print(" -", l.text)