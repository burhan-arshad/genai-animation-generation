"""SQLite store for jobs and stage events. Shared by the CLI, the pipeline and the dashboard API."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "jobs.db"
EXTRA_COLUMNS = {"style": "TEXT DEFAULT 'history'", "fact_status": "TEXT", "qa_status": "TEXT",
                 "approved": "INTEGER DEFAULT 0", "note": "TEXT", "youtube_id": "TEXT",
                 "tries": "INTEGER DEFAULT 0", "vision_status": "TEXT"}


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY, topic TEXT, slug TEXT, status TEXT DEFAULT 'queued',
        error TEXT, created REAL, updated REAL)""")
    have = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    for col, decl in EXTRA_COLUMNS.items():
        if col not in have:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
    con.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY, job_id INTEGER, stage TEXT, started REAL, ended REAL, ok INTEGER, error TEXT)""")
    con.commit()
    return con


def add_job(topic: str, style: str) -> int:
    con = db()
    now = time.time()
    cur = con.execute("INSERT INTO jobs(topic, created, updated, style) VALUES(?,?,?,?)", (topic, now, now, style))
    slug = f"{cur.lastrowid:03d}-" + re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    con.execute("UPDATE jobs SET slug=? WHERE id=?", (slug, cur.lastrowid))
    con.commit()
    return cur.lastrowid


def get_job(job_id: int) -> dict | None:
    row = db().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def set_job(job_id: int, **fields) -> None:
    con = db()
    cols = ", ".join(f"{k}=?" for k in fields) + ", updated=?"
    con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), time.time(), job_id))
    con.commit()


def log_event(job_id: int, stage: str, started: float, ok: bool, error: str | None = None) -> None:
    con = db()
    con.execute("INSERT INTO events(job_id, stage, started, ended, ok, error) VALUES(?,?,?,?,?,?)",
                (job_id, stage, started, time.time(), int(ok), (error or "")[:1000] or None))
    con.commit()


def delete_jobs(ids: list[int]) -> None:
    if not ids:
        return
    con = db()
    marks = ",".join("?" * len(ids))
    con.execute(f"DELETE FROM events WHERE job_id IN ({marks})", ids)
    con.execute(f"DELETE FROM jobs WHERE id IN ({marks})", ids)
    con.commit()