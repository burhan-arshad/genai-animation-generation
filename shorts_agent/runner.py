"""Runs the faceless-shorts skill pipeline on a project folder, stage by stage."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from .config import SKILL_DIR, SKILL_PY


class StageError(RuntimeError):
    pass


def run_stage(label: str, cmd: list[str], cwd: Path, must_contain: str | None = None) -> float:
    """Run one stage, save its log, raise StageError on failure. Returns seconds taken."""
    print(f"[{label}] running ...", flush=True)
    start = time.time()
    p = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    secs = time.time() - start

    log_dir = cwd / "logs"
    log_dir.mkdir(exist_ok=True)
    (log_dir / f"{label}.log").write_text(
        f"$ {' '.join(cmd)}\n\n{p.stdout}\n--- stderr ---\n{p.stderr}", encoding="utf-8"
    )

    if p.returncode != 0:
        raise StageError(f"stage '{label}' failed (exit {p.returncode}). See logs/{label}.log")
    if must_contain and must_contain not in p.stdout:
        raise StageError(f"stage '{label}' did not print '{must_contain}'. See logs/{label}.log")

    print(f"[{label}] ok in {secs:.1f}s", flush=True)
    return secs


def build_stages(project: Path, out_name: str):
    node = "node"
    capture = ["tools/capture.mjs"]
    return [
        ("voice", [str(SKILL_PY), str(SKILL_DIR / "scripts" / "voice.py"), str(project)], None),
        ("words", [str(SKILL_PY), str(SKILL_DIR / "scripts" / "words.py"), str(project)], None),
        ("check", [node, *capture, "check"], "CHECK OK"),
        ("cues", [node, *capture, "cues"], None),
        ("mix", [str(SKILL_PY), "tools/mix.py", "."], None),
        ("video", [node, *capture, "video", f"renders/{out_name}.mp4"], None),
    ]


def run_pipeline(project: Path, out_name: str = "out", only: list[str] | None = None) -> Path:
    project = project.resolve()
    (project / "renders").mkdir(exist_ok=True)
    timings: dict[str, float] = {}
    for label, cmd, must in build_stages(project, out_name):
        if only and label not in only:
            continue
        timings[label] = run_stage(label, cmd, project, must)
    print("\nTimings:", {k: round(v, 1) for k, v in timings.items()})
    return project / "renders" / f"{out_name}.mp4"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--name", default="out")
    ap.add_argument("--only", nargs="*", help="e.g. --only voice words")
    args = ap.parse_args()
    try:
        print("Output:", run_pipeline(args.project, args.name, args.only))
    except StageError as e:
        print("FAILED:", e)
        sys.exit(1)