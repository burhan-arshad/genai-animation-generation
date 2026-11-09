"""YouTube upload via Data API v3 (OAuth desktop flow). Default privacy: private."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
ROOT = Path(__file__).resolve().parent.parent
CLIENT, TOKEN = ROOT / "client_secret.json", ROOT / "token.json"


def get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def build_metadata(project: Path) -> dict:
    s = json.loads((project / "script.json").read_text(encoding="utf-8"))
    title = s["title"][:90] + " #shorts"
    desc = (s["lines"][0]["text"] + "\n\nSources:\n" + "\n".join(f"- {x}" for x in s["sources"])
            + "\n\n#shorts #science #explained")
    return {"title": title[:100], "description": desc, "tags": ["shorts", "science", "explained"]}


def upload(video: Path, meta: dict, privacy: str = "private", category: str = "27") -> str:
    body = {"snippet": {**meta, "categoryId": category},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True)
    req = get_service().videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"uploaded {int(status.progress() * 100)}%")
    return resp["id"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--name", default="final")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    a = ap.parse_args()
    meta = build_metadata(a.project)
    print("Uploading:", meta["title"], "|", a.privacy)
    vid = upload(a.project / "renders" / f"{a.name}.mp4", meta, a.privacy)
    print("Done: https://www.youtube.com/watch?v=" + vid)