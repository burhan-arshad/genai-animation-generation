"""YouTube upload (Data API v3, OAuth desktop flow) for jobs in status 'ready'."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

from . import niche, store, styles
from .config import PROJECTS_ROOT, REPO

SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/yt-analytics.readonly"]
CLIENT, TOKEN = REPO / "client_secret.json", REPO / "token.json"


class UploadError(RuntimeError):
    pass


class AuthError(UploadError):
    pass


class QuotaError(UploadError):
    pass


def get_creds(interactive: bool = False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds = Credentials.from_authorized_user_file(str(TOKEN)) if TOKEN.exists() else None
    if creds and not set(SCOPES) <= set(creds.scopes or []):
        creds = None                                         # an older login without the new permissions
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise AuthError("YouTube login missing, expired or without the new permissions. Dashboard: YouTube tab, Log out, then Log in.")
        if not CLIENT.exists():
            raise AuthError(f"{CLIENT} not found (Google Cloud OAuth client JSON).")
        creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_service(interactive: bool = False):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=get_creds(interactive), cache_discovery=False)

def upload_defaults(key: str | None = None) -> dict:
    return niche.load(key or styles.default_key()).get("upload", {}) if (key or styles.default_key()) in niche.available() else {}


def build_metadata(project: Path, key: str | None = None) -> dict:
    u = upload_defaults(key)
    s = json.loads((project / "script.json").read_text(encoding="utf-8"))
    title = re.sub(r"\s+", " ", s["title"]).strip()
    if len(title) > 95:
        title = title[:95].rsplit(" ", 1)[0]
    footer = u.get("footer", "Narrated and animated with AI tools. The script is written from the sources above.")
    hashtags = u.get("hashtags", "#shorts")
    parts = [s["lines"][0]["text"]]
    if os.getenv("SOURCES_IN_DESCRIPTION", "0") == "1":              # off by default: no links in the description for now
        parts.append("Sources:\n" + "\n".join(f"- {x}" for x in s["sources"]))
    else:
        footer = re.sub(r"\s*The script is written from the sources above\.?", "", footer).strip() or "Narrated and animated with AI tools."
    parts += [footer, hashtags]
    desc = "\n\n".join(parts)
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", s["title"])][:4]
    tags, total = [], 0
    for t in ["shorts"] + list(u.get("tags", [])) + words:
        if total + len(t) + 1 > 450:
            break
        tags.append(t)
        total += len(t) + 1
    if s.get("series"):
        ser = s["series"]
        title = f"{ser['title']} | Episode {ser['ep']}: {ser['ep_title']}"
        title = title[:95].rsplit(" ", 1)[0] if len(title) > 95 else title
        nxt = f" Next: {ser['next_title']}." if ser.get("next_title") else ""
        desc = "\n\n".join([ser.get("logline", ""), f"Episode {ser['ep']} of {ser['eps']}.{nxt}", footer, u.get("hashtags", "#mystery").replace("#shorts", "").strip()])
    return {"title": title, "description": desc[:4900], "tags": tags}



def _insert(svc, body: dict, video: Path) -> dict:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, retries = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"  uploaded {int(status.progress() * 100)}%", flush=True)
        except HttpError as e:
            if getattr(e.resp, "status", 0) in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise
        except (ConnectionError, TimeoutError) as e:
            if retries >= 5:
                raise UploadError(f"network error: {e}") from e
            retries += 1
            time.sleep(2 ** retries)
    return resp


def upload(svc, video: Path, meta: dict, privacy: str, publish_at: str | None, synthetic: bool, category: str = "27") -> dict:
    from googleapiclient.errors import HttpError
    status = {"privacyStatus": "private" if publish_at else privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["publishAt"] = publish_at
    if synthetic:
        status["containsSyntheticMedia"] = True
    body = {"snippet": {**meta, "categoryId": category}, "status": status}
    try:
        return _insert(svc, body, video)
    except HttpError as e:
        text = str(e)
        if "quotaExceeded" in text or "uploadLimitExceeded" in text:
            raise QuotaError(text[:300]) from e
        if synthetic and "containsSyntheticMedia" in text:
            status.pop("containsSyntheticMedia")
            print("  (synthetic-media flag rejected, retrying without it)")
            return _insert(svc, body, video)
        raise UploadError(text[:400]) from e


def upload_ready(limit: int = 1, job_id: int | None = None, mode: str | None = None, publish_at: str | None = None) -> list[str]:
    """mode None or 'private' = private; 'now' = public at once; 'private' = private;
    'schedule' = private + publishAt (the given time, or the next free slot of the schedule)."""
    if job_id:
        rows = store.db().execute("SELECT * FROM jobs WHERE id=? AND status='ready'", (job_id,)).fetchall()
    else:
        rows = store.db().execute("SELECT * FROM jobs WHERE status='ready' ORDER BY id LIMIT ?", (limit,)).fetchall()
    if not rows:
        print("no ready videos to upload")
        return []
    svc = get_service()
    synthetic = os.getenv("SYNTHETIC_DISCLOSURE", "false").lower() == "true"
    urls = []
    for r in rows:
        project = PROJECTS_ROOT / r["slug"]
        video = project / "renders" / "final_norm.mp4"
        if not video.exists():
            store.set_job(r["id"], error="final_norm.mp4 missing")
            continue
        meta = build_metadata(project, r["style"])
        category = os.getenv("CATEGORY_ID") or upload_defaults(r["style"]).get("category_id", "27")
        if mode == "now":
            privacy, pub = "public", None
        elif mode == "private":
            privacy, pub = "private", None
        elif mode == "schedule":
            from . import schedule
            if publish_at:
                pub = publish_at
            else:
                slots = schedule.next_slots(1)
                if not slots:
                    raise UploadError("no free slot: check the days and times in the Assistant tab")
                pub = schedule.iso(slots[0])
            privacy = "private"
        else:
            privacy, pub = "private", None
        print(f"[job {r['id']}] uploading '{meta['title']}' as {'private + publishAt ' + pub if pub else privacy}")
        resp = upload(svc, video, meta, privacy, pub, synthetic, category)
        real = resp.get("status", {}).get("privacyStatus", "?")
        url = f"https://www.youtube.com/watch?v={resp['id']}"
        thumb = project / "thumb.jpg"
        if thumb.exists():
            try:
                from googleapiclient.http import MediaFileUpload
                svc.thumbnails().set(videoId=resp["id"], media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
            except Exception as e:
                print(f"  (thumbnail not set: {str(e)[:120]})")
        stamp = pub or (dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if real == "public" else None)
        note = f"privacy=scheduled {pub}" if mode == "schedule" else f"privacy={real}"
        store.set_job(r["id"], status="uploaded", youtube_id=resp["id"], note=note, publish_at=stamp, error=None)
        if r["series_id"]:
            try:
                from . import series
                series.after_upload(svc, r["series_id"], r["ep_no"], resp["id"])
            except Exception as e:
                print(f"  (playlist not updated: {str(e)[:120]})")
        print(f"[job {r['id']}] UPLOADED ({real}{', goes live ' + pub if pub else ''}): {url}")
        urls.append(url)
    return urls

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=1)
    r.add_argument("--job", type=int)
    r.add_argument("--mode", choices=["now", "private", "schedule"], default="private")
    r.add_argument("--at", default=None)
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            TOKEN.unlink(missing_ok=True)
            get_service(interactive=True)
            print("Logged in. Token saved to", TOKEN)
        else:
            upload_ready(args.limit, args.job, args.mode, args.at)
    except UploadError as e:
        sys.exit(f"UPLOAD FAILED: {e}")
