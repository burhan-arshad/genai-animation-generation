"""Fully automatic pipeline: topic -> research -> script -> fact-check -> voice -> shots -> render -> loudness -> QA -> ready.
No human review: automatic gates decide. A video that cannot pass them is dropped, never published."""
from __future__ import annotations

import argparse
import json
import os
import time

from . import store, styles
from .config import PROJECTS_ROOT as ROOT
from .factcheck_agent import FactCheckFailed, verify_project
from .finalize import finalize
from .llm import BudgetExceeded
from .qa import run_qa
from .runner import run_pipeline
from .script_agent import generate
from .storyboard_agent import build_shots

TERMINAL = ("ready", "uploaded", "dropped", "rejected", "awaiting_approval", "approved")
FLOW = ["queued", "scripted", "verified", "timed", "storyboarded", "rendered", "finalized", "ready"]
STAGE_NAME = {"queued": "research+script", "scripted": "fact-check", "verified": "voice+timing",
              "timed": "storyboard", "storyboarded": "render", "rendered": "loudness", "finalized": "qa"}
MAX_TRIES = 3


class Drop(RuntimeError):
    """A gate failed in a way retrying will not fix: drop the video."""


def advance(job: dict) -> str:
    """Run exactly one stage; return the new status."""
    styles.set_active(job["style"] or "history")
    project = ROOT / job["slug"]
    s = job["status"]
    if s == "queued":
        generate(job["topic"], project)
        return "scripted"
    if s == "scripted":
        store.set_job(job["id"], fact_status=verify_project(project))
        return "verified"
    if s == "verified":
        run_pipeline(project, "final", only=["voice", "words"])
        return "timed"
    if s == "timed":
        build_shots(project)
        return "storyboarded"
    if s == "storyboarded":
        run_pipeline(project, "final", only=["check", "cues", "mix", "video"])
        return "rendered"
    if s == "rendered":
        finalize(project)
        return "finalized"
    if s == "finalized":
        qa = run_qa(project / "renders" / "final_norm.mp4")
        (project / "qa.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
        store.set_job(job["id"], qa_status=qa["status"])
        if qa["status"] == "failed":
            raise Drop("QA failed: " + "; ".join(i["msg"] for i in qa["issues"] if i["level"] == "FAIL"))
        return "ready"
    raise ValueError(f"unknown status {s}")


def run(limit: int, job_id: int | None = None) -> None:
    con = store.db()
    marks = ",".join("?" * len(TERMINAL))
    if job_id:
        rows = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchall()
    else:  # fresh jobs first, previously failed ones after
        rows = con.execute(f"SELECT * FROM jobs WHERE status NOT IN ({marks}) "
                           "ORDER BY (error IS NOT NULL), id LIMIT ?", (*TERMINAL, limit)).fetchall()

    if not rows:
        print("no job to run (see `pipeline list`)")
        return
    
    for r in rows:
        job = dict(r)
        while job["status"] not in TERMINAL:
            stage, t0 = job["status"], time.time()
            name = STAGE_NAME.get(stage, stage)
            try:
                new = advance(job)
            except BudgetExceeded as e:
                print(f"[budget] {e}\nStopping. Re-run later; jobs resume where they stopped.")
                return
            except Drop as e:
                store.log_event(job["id"], stage, t0, False, str(e))
                store.set_job(job["id"], status="dropped", error=str(e)[:2000])
                job["status"] = "dropped"
                print(f"[job {job['id']}] DROPPED at '{name}': {str(e)[:300]}")
                break
            except (Exception, SystemExit) as e:
                tries = (job.get("tries") or 0) + 1
                job["tries"] = tries
                store.log_event(job["id"], stage, t0, False, str(e))
                if tries >= MAX_TRIES:
                    store.set_job(job["id"], status="dropped", error=str(e)[:2000], tries=tries)
                    job["status"] = "dropped"
                    print(f"[job {job['id']}] DROPPED after {tries} failed tries at '{name}': {str(e)[:300]}")
                    break
                if isinstance(e, FactCheckFailed):   # facts did not hold up: write a fresh script
                    store.set_job(job["id"], status="queued", error=None, tries=tries)
                    job["status"] = "queued"
                    print(f"[job {job['id']}] facts failed ({tries}/{MAX_TRIES}), writing a new script")
                    continue
                store.set_job(job["id"], error=str(e)[:2000], tries=tries)
                print(f"[job {job['id']}] FAILED at '{name}' (try {tries}/{MAX_TRIES}): {str(e)[:300]}")
                break
            store.log_event(job["id"], stage, t0, True)
            store.set_job(job["id"], status=new, error=None)
            job["status"] = new
            print(f"[job {job['id']}] {name} done in {time.time() - t0:.0f}s -> {new}")
        if job["status"] == "ready":
            print(f"[job {job['id']}] READY: {ROOT / job['slug'] / 'renders' / 'final_norm.mp4'}")


def list_jobs() -> None:
    n = store.db().execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"db: {store.DB} ({n} jobs)")
    print(f"{'id':>3} {'status':<13} {'facts':<20} {'qa':<21} {'try':>3}  topic")
    for r in store.db().execute("SELECT * FROM jobs ORDER BY id"):
        print(f"{r['id']:>3} {r['status']:<13} {(r['fact_status'] or '-'):<20} {(r['qa_status'] or '-'):<21} "
              f"{(r['tries'] or 0):>3}  {r['topic']}" + (f"  !! {r['error'][:60]}" if r["error"] else ""))


def events(job_id: int) -> None:
    for e in store.db().execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,)):
        print(f"{time.strftime('%H:%M:%S', time.localtime(e['started']))}  {STAGE_NAME.get(e['stage'], e['stage']):<16} "
              f"{e['ended'] - e['started']:>6.0f}s  {'ok' if e['ok'] else 'FAILED: ' + (e['error'] or '')[:100]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("topics", nargs="+")
    a.add_argument("--style", default=os.getenv("STYLE", "history"))
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=1)
    r.add_argument("--job", type=int)
    sub.add_parser("list")
    e = sub.add_parser("events")
    e.add_argument("job", type=int)
    j = sub.add_parser("reject")
    j.add_argument("jobs", nargs="+", type=int)
    j.add_argument("--note", default=None)
    z = sub.add_parser("reset")
    z.add_argument("job", type=int)
    z.add_argument("status", choices=FLOW)
    args = ap.parse_args()
    if args.cmd == "add":
        styles.set_active(args.style)
        for t in args.topics:
            print(f"queued job {store.add_job(t, args.style)} [{args.style}]: {t}")
    elif args.cmd == "run":
        run(args.limit, args.job)
    elif args.cmd == "list":
        list_jobs()
    elif args.cmd == "events":
        events(args.job)
    elif args.cmd == "reject":
        for i in args.jobs:
            store.set_job(i, status="rejected", note=args.note)
        print("rejected", args.jobs)
    elif args.cmd == "reset":
        if not store.get_job(args.job):
            raise SystemExit(f"no job {args.job}")
        store.set_job(args.job, status=args.status, error=None, tries=0)
        print(f"job {args.job} reset to {args.status}")