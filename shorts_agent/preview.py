"""Fast preview: take a job up to the storyboard stage and make a picture sheet of the film (no long render).
python -m shorts_agent.preview --job 8                  picture sheet
python -m shorts_agent.preview --job 8 --clip 10 16     also a short test video of those seconds (a few minutes, silent)"""
from __future__ import annotations

import argparse
import json
import os
import subprocess

from . import store
from .config import PROJECTS_ROOT, proc_flags, render_env
from .pipeline import run
from .filmboard import contact_sheet


def clip(project, a: float, b: float):
    out = "renders/clip.mp4"
    (project / "renders").mkdir(exist_ok=True)
    p = subprocess.run(["node", "tools/capture.mjs", "video", out, str(a), str(b), "--draft"], cwd=project, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, **render_env(project=project)}, creationflags=proc_flags())
    print((p.stdout + p.stderr)[-500:])
    return project / out if p.returncode == 0 else None


def preview(job_id: int, clip_range: tuple[float, float] | None = None) -> None:
    job = store.get_job(job_id)
    if not job:
        raise SystemExit(f"no job {job_id}")
    stop = run(1, job_id, "storyboarded")
    if stop:
        print(f"[preview] stopped early ({stop}): run it again later")
        return
    job = store.get_job(job_id)
    project = PROJECTS_ROOT / job["slug"]
    f = project / "story.json"
    if not f.exists():
        print(f"[preview] no story.json: the job is '{job['status']}' ({job.get('error') or 'no error saved'})")
        return
    contact_sheet(project, json.loads(f.read_text(encoding="utf-8")), project / "review" / "all.jpg")
    print("[preview] done:", project / "review" / "all.jpg", "and", project / "review" / "props.jpg")
    m = project / "metrics.json"
    if m.exists():
        print("[preview] metrics:", m.read_text(encoding="utf-8").replace("\n", " "))
    if clip_range:
        out = clip(project, *clip_range)
        print("[preview] clip:", out or "failed")
        if out and hasattr(os, "startfile"):
            os.startfile(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=int, required=True)
    ap.add_argument("--clip", type=float, nargs=2, metavar=("START", "END"), default=None)
    a = ap.parse_args()
    preview(a.job, tuple(a.clip) if a.clip else None)