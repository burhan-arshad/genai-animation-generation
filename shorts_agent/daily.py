"""Daily automation entry point: keep the queue stocked, make a video that passes every gate, upload it."""
from __future__ import annotations

import os
import sys
import time

from . import store, topics, uploader
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


def main() -> int:
    print(time.strftime("=== daily run %Y-%m-%d %H:%M:%S ==="))
    if not acquire():
        print("another run is active (lock younger than 4 h). Exiting.")
        return 0
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
            if run_jobs(1) == "budget":
                print("LLM budget reached: will resume on the next run.")
                break
        try:
            uploader.upload_ready(need)
        except uploader.AuthError as e:
            print("[AUTH]", e)
            return 2
        except uploader.UploadError as e:
            print("[UPLOAD]", e)
            return 3
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())