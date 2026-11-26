"""Launch plan: the first days of the channel (review period) and the approval queue (private uploads you publish by hand)."""
from __future__ import annotations

import datetime as dt
import os

from . import store, uploader
from .config import PROJECTS_ROOT


def pending() -> list[dict]:
    out = []
    for r in store.db().execute("SELECT * FROM jobs WHERE status='uploaded' ORDER BY id DESC"):
        note = r["note"] or ""
        if "privacy=private" in note or "privacy=unlisted" in note:
            out.append({"id": r["id"], "topic": r["topic"], "youtube_id": r["youtube_id"], "note": note})
    return out


def publish(job_id: int, when: str = "now") -> str:
    from googleapiclient.errors import HttpError
    job = store.get_job(job_id)
    if not job or not job.get("youtube_id"):
        raise RuntimeError("this video has no YouTube id")
    status_body = {"selfDeclaredMadeForKids": False}
    if when == "now":
        status_body["privacyStatus"], note = "public", "privacy=public"
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        from . import schedule
        slots = schedule.next_slots(1)
        if not slots:
            raise RuntimeError("no free slot: check the days and times in the Assistant tab")
        at = schedule.iso(slots[0])
        status_body.update(privacyStatus="private", publishAt=at)
        note, stamp = f"privacy=scheduled {at}", at
    if os.getenv("SYNTHETIC_DISCLOSURE", "false").lower() == "true":
        status_body["containsSyntheticMedia"] = True
    svc = uploader.get_service()
    try:
        svc.videos().update(part="status", body={"id": job["youtube_id"], "status": status_body}).execute()
    except HttpError as e:
        if "containsSyntheticMedia" not in str(e):
            raise RuntimeError(str(e)[:300])
        status_body.pop("containsSyntheticMedia")
        svc.videos().update(part="status", body={"id": job["youtube_id"], "status": status_body}).execute()
    store.set_job(job_id, note=note, publish_at=stamp)
    return note