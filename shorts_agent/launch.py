"""Launch plan: the first days of the channel (review period) and the approval queue (private uploads you publish by hand)."""
from __future__ import annotations

import datetime as dt
import os

from . import store, uploader
from .config import PROJECTS_ROOT

CHECKLIST = [
    "Every video is uploaded as PRIVATE and published by you, after you have watched it.",
    "No source links in the description (they are kept in the script file only).",
    "Post about one video a day, at a regular time.",
    "Check each video for wrong facts before publishing: the fact-check is automatic but not perfect.",
    "Keep the AI disclosure setting on if YouTube's rules ask for it for your kind of video (Settings -> YouTube).",
    "After the review period, look at Results and decide: more public videos, or fix what did not work.",
]


def status() -> dict:
    days = int(os.getenv("LAUNCH_REVIEW_DAYS", "60") or 60)
    out = {"set": False, "review_days": days, "require_approval": os.getenv("REQUIRE_APPROVAL", "1") == "1", "checklist": CHECKLIST}
    try:
        start = dt.date.fromisoformat(os.getenv("LAUNCH_DATE", "").strip())
    except ValueError:
        return out
    day = (dt.date.today() - start).days + 1
    out.update(set=True, start=start.isoformat(), day=max(day, 0), left=max(0, days - day + 1), phase="review" if day <= days else "after")
    return out


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
    else:
        at = uploader.next_publish_time(int(os.getenv("PUBLISH_AT_UTC_HOUR") or 18))
        status_body.update(privacyStatus="private", publishAt=at)
        note = f"privacy=scheduled {at}"
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
    store.set_job(job_id, note=note)
    return note