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

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import store
from .config import PROJECTS_ROOT, REPO

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT, TOKEN = REPO / "client_secret.json", REPO / "token.json"


class UploadError(RuntimeError):
    pass


class AuthError(UploadError):
    pass


class QuotaError(UploadError):
    pass


def get_service(interactive: bool = False):
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise AuthError("YouTube login missing or expired. Run once: python -m shorts_agent.uploader login")
        if not CLIENT.exists():
            raise AuthError(f"{CLIENT} not found (Google Cloud OAuth client JSON).")
        creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def build_metadata(project: Path) -> dict:
    s = json.loads((project / "script.json").read_text(encoding="utf-8"))
    title = re.sub(r"\s+", " ", s["title"]).strip()
    if len(title) > 95:
        title = title[:95].rsplit(" ", 1)[0]
    desc = (s["lines"][0]["text"] + "\n\nSources:\n" + "\n".join(f"- {x}" for x in s["sources"])
            + "\n\nNarrated and animated with AI tools. The script is written from the sources above.\n\n"
              "#shorts #history #historyfacts")
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", s["title"])][:4]
    tags, total = [], 0
    for t in ["history", "shorts", "history facts", "true story"] + words:
        if total + len(t) + 1 > 450:
            break
        tags.append(t)
        total += len(t) + 1
    return {"title": title, "description": desc[:4900], "tags": tags}


def next_publish_time(hour_utc: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    t = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if t <= now + dt.timedelta(minutes=30):
        t += dt.timedelta(days=1)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _insert(svc, body: dict, video: Path) -> dict:
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


def upload(svc, video: Path, meta: dict, privacy: str, publish_at: str | None, synthetic: bool) -> dict:
    status = {"privacyStatus": "private" if publish_at else privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["publishAt"] = publish_at
    if synthetic:
        status["containsSyntheticMedia"] = True
    body = {"snippet": {**meta, "categoryId": os.getenv("CATEGORY_ID", "27")}, "status": status}
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


def upload_ready(limit: int = 1) -> list[str]:
    rows = store.db().execute("SELECT * FROM jobs WHERE status='ready' ORDER BY id LIMIT ?", (limit,)).fetchall()
    if not rows:
        print("no ready videos to upload")
        return []
    svc = get_service()
    privacy = os.getenv("UPLOAD_PRIVACY", "private")
    hour = os.getenv("PUBLISH_AT_UTC_HOUR", "").strip()
    synthetic = os.getenv("SYNTHETIC_DISCLOSURE", "false").lower() == "true"
    urls = []
    for r in rows:
        project = PROJECTS_ROOT / r["slug"]
        video = project / "renders" / "final_norm.mp4"
        if not video.exists():
            store.set_job(r["id"], error="final_norm.mp4 missing")
            continue
        meta = build_metadata(project)
        publish_at = next_publish_time(int(hour)) if (hour and privacy == "public") else None
        print(f"[job {r['id']}] uploading '{meta['title']}' as {'private + publishAt ' + publish_at if publish_at else privacy}")
        resp = upload(svc, video, meta, privacy, publish_at, synthetic)
        real = resp.get("status", {}).get("privacyStatus", "?")
        url = f"https://www.youtube.com/watch?v={resp['id']}"
        store.set_job(r["id"], status="uploaded", youtube_id=resp["id"], note=f"privacy={real}", error=None)
        print(f"[job {r['id']}] UPLOADED ({real}): {url}")
        if privacy == "public" and real == "private" and not publish_at:
            print("  WARNING: public was requested but YouTube kept the video private (API project may need verification).")
        urls.append(url)
    return urls


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=1)
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            TOKEN.unlink(missing_ok=True)
            get_service(interactive=True)
            print("Logged in. Token saved to", TOKEN)
        else:
            upload_ready(args.limit)
    except UploadError as e:
        sys.exit(f"UPLOAD FAILED: {e}")