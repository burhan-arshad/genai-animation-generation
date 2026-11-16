"""Channel stats from YouTube (Data API + Analytics API), kept in jobs.db. Needs the newer login (YouTube tab: log in again)."""
from __future__ import annotations

import datetime as dt
import time

from . import store, uploader


def _con():
    con = store.db()
    con.execute("CREATE TABLE IF NOT EXISTS stats(job_id INTEGER PRIMARY KEY, views INTEGER, likes INTEGER, comments INTEGER, "
                "avg_pct REAL, avg_sec REAL, fetched REAL)")
    con.commit()
    return con


def refresh() -> dict:
    from googleapiclient.discovery import build
    con = _con()
    by_vid = {r["youtube_id"]: r["id"] for r in con.execute("SELECT id, youtube_id FROM jobs WHERE status='uploaded' AND youtube_id IS NOT NULL")}
    if not by_vid:
        return {"updated": 0, "analytics": False}
    creds = uploader.get_creds()
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ids, got = list(by_vid), {}
    for k in range(0, len(ids), 50):
        for it in yt.videos().list(part="statistics", id=",".join(ids[k:k + 50])).execute().get("items", []):
            s = it.get("statistics", {})
            got[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                             "comments": int(s.get("commentCount", 0)), "avg_pct": None, "avg_sec": None}
    ok = False
    try:
        an = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        today = dt.date.today()
        for k in range(0, len(ids), 50):
            r = an.reports().query(ids="channel==MINE", startDate=(today - dt.timedelta(days=90)).isoformat(), endDate=today.isoformat(),
                                   metrics="views,averageViewDuration,averageViewPercentage", dimensions="video",
                                   filters="video==" + ",".join(ids[k:k + 50]), maxResults=50, sort="-views").execute()
            for row in r.get("rows", []):
                if row[0] in got:
                    got[row[0]]["avg_sec"], got[row[0]]["avg_pct"] = float(row[2]), float(row[3])
        ok = True
    except Exception as e:                                   # views still work without the Analytics API
        print(f"[analytics] retention not available ({type(e).__name__}): {str(e)[:150]}")
    for vid, s in got.items():
        con.execute("INSERT OR REPLACE INTO stats VALUES(?,?,?,?,?,?,?)",
                    (by_vid[vid], s["views"], s["likes"], s["comments"], s["avg_pct"], s["avg_sec"], time.time()))
    con.commit()
    return {"updated": len(got), "analytics": ok}


def rows() -> list[dict]:
    return [dict(r) for r in _con().execute(
        "SELECT j.id, j.topic, s.views, s.likes, s.comments, s.avg_pct, s.avg_sec FROM jobs j JOIN stats s ON s.job_id=j.id ORDER BY s.views DESC")]


def lessons(n: int = 3) -> str:
    """Text for the topic agent: what worked and what did not ('' until at least 4 videos have stats)."""
    r = rows()
    if len(r) < 4:
        return ""
    f = lambda xs: "; ".join(f"{x['topic']} ({x['views']} views" + (f", {x['avg_pct']:.0f}% watched" if x["avg_pct"] else "") + ")" for x in xs)
    return f"What worked on this channel: {f(r[:n])}.\nWhat did worst: {f(r[-n:])}.\nPropose topics like the best ones and unlike the worst."