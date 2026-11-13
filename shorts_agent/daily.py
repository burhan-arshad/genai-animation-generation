"""Daily automation entry point: keep the queue stocked, make a video that passes every gate, upload it, e-mail a summary."""
from __future__ import annotations

import os
import sys
import time
import traceback

from . import notify, store, topics, uploader
from .config import REPO
from .pipeline import run as run_jobs

LOCK = REPO / "daily.lock"
TARGET = int(os.getenv("VIDEOS_PER_DAY", "1"))
OPEN = "('ready','uploaded','dropped','rejected')"


def acquire() -> bool:
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 4 * 3600:
        return False
    LOCK.write_text(str(os.getpid()))
    return True


def count(where: str) -> int:
    return store.db().execute(f"SELECT COUNT(*) FROM jobs WHERE {where}").fetchone()[0]


def dropped_today():
    return store.db().execute("SELECT id, topic, error FROM jobs WHERE status='dropped' "
                              "AND date(updated,'unixepoch','localtime')=date('now','localtime')").fetchall()


def main() -> int:
    print(time.strftime("=== daily run %Y-%m-%d %H:%M:%S ==="))
    if not acquire():
        print("another run is active (lock younger than 4 h). Exiting.")
        return 0
    notes: list[str] = []
    urls: list[str] = []
    code = 0
    try:
        need = TARGET - count("status='uploaded' AND date(updated,'unixepoch','localtime')=date('now','localtime')")
        if need <= 0:
            print("already uploaded today's video(s).")
            return 0
        for _ in range(4):                               # dropped videos do not count: try the next topic
            if count("status='ready'") >= need:
                break
            if count(f"status NOT IN {OPEN}") == 0:
                topics.enqueue(3)
            stop = run_jobs(1)
            if stop == "budget":
                notes.append("LLM budget reached: the run will continue tomorrow.")
                break
            if stop == "overload":
                notes.append("The model provider was overloaded: the run will continue at the next schedule.")
                break
        try:
            urls = uploader.upload_ready(need)
        except uploader.AuthError as e:
            notes.append(f"YOUTUBE LOGIN PROBLEM: {e}")
            code = 2
        except uploader.UploadError as e:
            notes.append(f"UPLOAD FAILED: {e}")
            code = 3
    except Exception:
        notes.append("CRASH:\n" + traceback.format_exc())
        code = 1
    finally:
        LOCK.unlink(missing_ok=True)
    notes += [f"Uploaded: {u}" for u in urls]
    for r in dropped_today():
        notes.append(f"Dropped job {r['id']} ({r['topic']}): {str(r['error'])[:200]}")
    if not urls and code == 0:
        notes.append("No video was uploaded today.")
    subject = "[shorts-agent] OK: " + ", ".join(urls) if urls else f"[shorts-agent] ATTENTION (exit {code})"
    print("\n".join(notes))
    notify.send(subject, "\n".join(notes) or "done")
    return code


if __name__ == "__main__":
    sys.exit(main())
