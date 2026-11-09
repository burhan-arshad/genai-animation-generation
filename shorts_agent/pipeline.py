"""Job queue + state machine: topic -> script -> timing -> shots -> render. Resumable."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

from .runner import run_pipeline
from .schemas import to_script_json
from .script_agent import make_project, write_script
from .storyboard_agent import build_shots
from .llm import BudgetExceeded

ROOT = Path(r"C:\Users\burha\faceless-shorts")
DB = Path(__file__).resolve().parent.parent / "jobs.db"


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY, topic TEXT, slug TEXT, status TEXT DEFAULT 'queued',
        error TEXT, created REAL, updated REAL)""")
    return con


def add(topics: list[str]) -> None:
    con = db()
    for t in topics:
        cur = con.execute("INSERT INTO jobs(topic, created, updated) VALUES(?,?,?)", (t, time.time(), time.time()))
        slug = f"{cur.lastrowid:03d}-" + re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40]
        con.execute("UPDATE jobs SET slug=? WHERE id=?", (slug, cur.lastrowid))
        print(f"queued job {cur.lastrowid}: {t}")
    con.commit()


def advance(job: dict) -> str:
    """Run exactly one stage; return the new status."""
    project = ROOT / job["slug"]
    s = job["status"]
    if s == "queued":
        draft = write_script(job["topic"])
        if not project.exists():
            make_project(project)
        (project / "script.json").write_text(
            json.dumps(to_script_json(draft), indent=2, ensure_ascii=False), encoding="utf-8")
        return "scripted"
    if s == "scripted":
        run_pipeline(project, "final", only=["voice", "words"])
        return "timed"
    if s == "timed":
        build_shots(project)
        return "storyboarded"
    if s == "storyboarded":
        run_pipeline(project, "final", only=["check", "cues", "mix", "video"])
        return "rendered"
    raise ValueError(f"unknown status {s}")


def run(limit: int) -> None:
    con = db()
    rows = con.execute("SELECT * FROM jobs WHERE status != 'rendered' ORDER BY id LIMIT ?", (limit,)).fetchall()
    for r in rows:
        job = dict(r)
        while job["status"] != "rendered":
            try:
                new = advance(job)
            except BudgetExceeded as e:
                print(f"[budget] {e}\nStopping. Re-run later; jobs resume where they stopped.")
                return
            except (Exception, SystemExit) as e:
                con.execute("UPDATE jobs SET error=?, updated=? WHERE id=?", (str(e)[:2000], time.time(), job["id"]))
                con.commit()
                print(f"[job {job['id']}] FAILED at '{job['status']}': {str(e)[:300]}")
                break
            job["status"] = new
            con.execute("UPDATE jobs SET status=?, error=NULL, updated=? WHERE id=?", (new, time.time(), job["id"]))
            con.commit()
            print(f"[job {job['id']}] -> {new}")
        if job["status"] == "rendered":
            print(f"[job {job['id']}] DONE: {ROOT / job['slug'] / 'renders' / 'final.mp4'}")


def list_jobs() -> None:
    for r in db().execute("SELECT id, status, topic, error FROM jobs ORDER BY id"):
        print(f"{r['id']:>3} {r['status']:<13} {r['topic']}" + (f"  !! {r['error'][:80]}" if r["error"] else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("topics", nargs="+")
    r = sub.add_parser("run"); r.add_argument("--limit", type=int, default=1)
    sub.add_parser("list")
    args = ap.parse_args()
    {"add": lambda: add(args.topics), "run": lambda: run(args.limit), "list": list_jobs}[args.cmd]()