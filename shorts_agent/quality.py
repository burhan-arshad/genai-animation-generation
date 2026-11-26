"""Quality score of a finished video (0-100). Below the assistant's minimum the video is held for your review instead of being uploaded."""
from __future__ import annotations

import json
from pathlib import Path

from .config import PROJECTS_ROOT


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def score(job: dict) -> tuple[int, list[str]]:
    project = PROJECTS_ROOT / job["slug"]
    s, why = 0, []
    fs = job.get("fact_status") or ""
    if fs == "verified":
        s += 30
    elif fs == "verified_with_notes":
        s += 22
        why.append("fact-check passed with notes")
    else:
        why.append(f"fact-check: {fs or 'not done'}")
    qs = job.get("qa_status") or ""
    if qs == "passed":
        s += 25
    elif qs == "passed_with_warnings":
        s += 17
        why.append("quality check has warnings")
    else:
        why.append(f"quality check: {qs or 'not done'}")
    story = _read(project / "story.json") or {}
    body = [x for x in story.get("shots", []) if x.get("set") != "study"]
    if body:
        props = sum(1 for x in body if x.get("props")) / len(body)
        acting = sum(1 for x in body if any(a.get("beats") or (a.get("arms") or {}).get("r", "down") != "down" or a.get("x0") != a.get("x1")
                                             for a in x.get("actors", []))) / len(body)
        cams = len({x.get("camera") for x in body})
        s += round(15 * min(1, props / 0.8)) + round(10 * min(1, acting / 0.5)) + (5 if cams >= 4 else 0)
        if props < 0.5:
            why.append(f"only {props:.0%} of the shots show an object")
        if acting < 0.3:
            why.append("the people hardly act")
        if cams < 4:
            why.append("few camera moves")
    else:
        why.append("no storyboard found")
    dur = float(((_read(project / "qa.json") or {}).get("meta") or {}).get("duration") or 0)
    if 30 <= dur <= 58:
        s += 10
    elif 20 <= dur < 30 or 58 < dur <= 60:
        s += 5
        why.append(f"duration {dur:.0f}s")
    else:
        why.append(f"duration {dur:.0f}s")
    if (project / "thumb.jpg").exists():
        s += 5
    else:
        why.append("no thumbnail")
    return max(0, min(100, s)), why