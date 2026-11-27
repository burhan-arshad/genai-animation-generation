"""Channel stats from YouTube (Data API + Analytics API) kept in jobs.db, and what the channel learns from them.
Every uploaded video gets its stats (views, retention, likes, shares, subscribers; the first 7 days separately so that videos of different
age compare fairly) and its features (kind of mystery, hook, shot length, moving objects, night scenes, music, voice...).
A performance score (retention 50%, views 30%, engagement 20%, each as a rank among your own videos) shows what works.
The assistant uses it gently: hints in the prompts of the topic, hook and film steps, a lean towards the better hook formula and kind of mystery,
and a share of the choices (LEARN_EXPLORE) always stays random so that the channel does not get stuck."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import random
import re
import time

from . import hooks, store, uploader
from .config import PROJECTS_ROOT

STAT_COLS = {"shares": "INTEGER", "subs": "INTEGER", "minutes": "REAL", "views7": "INTEGER", "pct7": "REAL",
             "shares7": "INTEGER", "subs7": "INTEGER", "published": "TEXT", "privacy": "TEXT"}
METRICS = ["views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained",
           "views,averageViewDuration,averageViewPercentage"]


def _con():
    con = store.db()
    con.execute("CREATE TABLE IF NOT EXISTS stats(job_id INTEGER PRIMARY KEY, views INTEGER, likes INTEGER, comments INTEGER, "
                "avg_pct REAL, avg_sec REAL, fetched REAL)")
    have = {r[1] for r in con.execute("PRAGMA table_info(stats)")}
    for c, t in STAT_COLS.items():
        if c not in have:
            con.execute(f"ALTER TABLE stats ADD COLUMN {c} {t}")
    con.commit()
    return con


def _num(x, cast=float):
    try:
        return cast(x)
    except (TypeError, ValueError):
        return None


def _parse(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _query(an, start: str, end: str, filters: str, dimensions: str | None = None):
    last: Exception | None = None
    for m in METRICS:                                       # the richer set first; the older permission set may only allow the short one
        try:
            kw = dict(ids="channel==MINE", startDate=start, endDate=end, metrics=m, filters=filters)
            if dimensions:
                kw.update(dimensions=dimensions, maxResults=50, sort="-views")
            r = an.reports().query(**kw).execute()
            return [h["name"] for h in r.get("columnHeaders", [])], r.get("rows", [])
        except Exception as e:
            last = e
    raise last


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
        for it in yt.videos().list(part="statistics,snippet,status", id=",".join(ids[k:k + 50])).execute().get("items", []):
            s, sn, st = it.get("statistics", {}), it.get("snippet", {}), it.get("status", {})
            got[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0)),
                             "published": sn.get("publishedAt") or "", "privacy": st.get("privacyStatus") or ""}
    ok = False
    try:
        an = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        today = dt.date.today()
        for k in range(0, len(ids), 50):
            head, rows = _query(an, (today - dt.timedelta(days=700)).isoformat(), today.isoformat(), "video==" + ",".join(ids[k:k + 50]), "video")
            for row in rows:
                d = dict(zip(head, row))
                g = got.get(d.get("video"))
                if g is not None:
                    g.update(avg_sec=_num(d.get("averageViewDuration")), avg_pct=_num(d.get("averageViewPercentage")), shares=_num(d.get("shares"), int),
                             subs=_num(d.get("subscribersGained"), int), minutes=_num(d.get("estimatedMinutesWatched")))
        now = dt.datetime.now(dt.timezone.utc)
        for vid, g in got.items():                         # the first 7 days: videos of different age can be compared
            pub = _parse(g.get("published"))
            if g.get("privacy") != "public" or not pub or (now - pub).days < 2:
                continue
            try:
                head, rows = _query(an, pub.date().isoformat(), min(today, pub.date() + dt.timedelta(days=6)).isoformat(), f"video=={vid}")
            except Exception:
                continue
            if rows:
                d = dict(zip(head, rows[0]))
                g.update(views7=_num(d.get("views"), int), pct7=_num(d.get("averageViewPercentage")), shares7=_num(d.get("shares"), int),
                         subs7=_num(d.get("subscribersGained"), int))
        ok = True
    except Exception as e:                                 # views and likes still work without the Analytics API
        print(f"[analytics] retention not available ({type(e).__name__}): {str(e)[:150]}")
    for vid, g in got.items():
        jid = by_vid[vid]
        con.execute("INSERT OR IGNORE INTO stats(job_id) VALUES(?)", (jid,))
        sets = ", ".join(f"{c}=COALESCE(?, {c})" for c in g) + ", fetched=?"
        con.execute(f"UPDATE stats SET {sets} WHERE job_id=?", (*g.values(), time.time(), jid))
    con.commit()
    return {"updated": len(got), "analytics": ok}


def stale(hours: float = 12) -> bool:
    r = _con().execute("SELECT MAX(fetched) FROM stats").fetchone()[0]
    return not r or time.time() - r > hours * 3600


# ───────────── what each video looked like ─────────────
def _read(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kind_of(text: str) -> str:
    """A rough kind of mystery from the title (also used on the niche's 'formats' to find the matching format)."""
    t = text.lower()
    if re.search(r"unsolved|open case|never solved", t):
        return "unsolved"
    if re.search(r"hoax|forger|fake|fraud|fabricat", t):
        return "hoax"
    if re.search(r"theft|stolen|heist|robbery|stole", t):
        return "theft"
    if re.search(r"\bcode\b|cipher|\bscript\b|manuscript|inscription|symbol|runestone|\bdisc\b", t):
        return "code"
    if re.search(r"vanish|disappear|abandon|missing|lost|never found", t):
        return "vanished"
    if re.search(r"(?<!un)solved|cracked|deciphered", t):
        return "solved"
    return "unsolved"


def features(job: dict) -> dict:
    p = PROJECTS_ROOT / job["slug"]
    sc, story, qa, vp = (_read(p / "script.json") or {}), (_read(p / "story.json") or {}), (_read(p / "qa.json") or {}), (_read(p / "data" / "voice_plan.json") or {})
    lines = [l.get("text", "") for l in sc.get("lines", [])]
    l0, l1 = (lines + ["", ""])[:2]
    allshots = story.get("shots", [])
    shots = [s for s in allshots if s.get("set") != "study"]
    dur = float(((qa.get("meta") or {}).get("duration")) or story.get("duration") or 0)
    props = [x for s in shots for x in s.get("props", [])]
    times = [((story.get("sets") or {}).get(s.get("set")) or {}).get("time", "day") for s in shots]
    pct = lambda a, b: round(100 * a / b) if b else 0
    return {
        "kind": kind_of(job["topic"]), "hook_line": l0, "hook_words": len(l0.split()),
        "hook_number": int(bool(re.search(r"\d", l0) or any(w.lower().strip(".,!?") in hooks.NUMBER_WORDS for w in l0.split()))),
        "hook_contrast": int(bool(hooks.CONTRAST.search(l0))), "hook_question": int(l0.strip().endswith("?")),
        "hook_year_first": int(bool(hooks.YEAR_FIRST.search(l0))), "hook_score": hooks.score_hook(l0, l1),
        "hook_type": job.get("hook_type") or "", "end_type": job.get("end_type") or "",
        "end_question": int(bool(lines) and lines[-1].strip().endswith("?")),
        "words": sum(len(t.split()) for t in lines), "lines": len(lines), "duration": round(dur, 1),
        "shots": len(allshots), "avg_shot_s": round(dur / len(allshots), 2) if allshots and dur else 0,
        "moving_props": sum(1 for x in props if x.get("move") not in (None, "", "pop", "none")),
        "props_per_shot": round(len(props) / len(shots), 2) if shots else 0,
        "callouts": sum(len(s.get("callouts", [])) for s in allshots), "cameras": len({s.get("camera") for s in shots}),
        "closeup_pct": pct(sum(1 for s in shots if s.get("framing") in ("close", "extreme_close")), len(shots)),
        "night_pct": pct(sum(1 for t in times if t in ("night", "dusk", "storm", "dawn", "sepia")), len(shots)),
        "effects": sum(1 for s in shots if s.get("effect")), "music": sc.get("music") or "", "voice": vp.get("actor") or sc.get("voice") or "",
        "emotions": len({d.get("emotion") for d in (vp.get("lines") or [])}), "quality_score": job.get("score"), "tokens": job.get("tokens"),
    }


# ───────────── the score ─────────────
def _pct_rank(vals: list) -> list:
    xs = sorted(v for v in vals if v is not None)
    if len(xs) < 2:
        return [0.5 if v is not None else None for v in vals]
    return [None if v is None else (sum(1 for x in xs if x < v) + 0.5 * sum(1 for x in xs if x == v)) / len(xs) for v in vals]


def _age_days(r: dict) -> float:
    pub = _parse(r.get("published") or "")
    return (dt.datetime.now(dt.timezone.utc) - pub).total_seconds() / 86400 if pub else 0.0


def _ret(r: dict):
    return r.get("pct7") if r.get("pct7") is not None else r.get("avg_pct")


def with_perf(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["perf"] = None
    elig = [r for r in rows if r.get("privacy") == "public" and (r.get("views") or 0) >= 1 and _age_days(r) >= 2]
    if len(elig) < 3:
        return rows
    ret = _pct_rank([_ret(r) for r in elig])
    vw = _pct_rank([r.get("views7") if r.get("views7") else r.get("views") for r in elig])
    eng = _pct_rank([((r.get("likes") or 0) + (r.get("comments") or 0) + 2 * (r.get("shares") or 0)) / max(1, r.get("views") or 1) for r in elig])
    for r, a, b, c in zip(elig, ret, vw, eng):
        r["perf"] = round(0.5 * (a if a is not None else 0.5) + 0.3 * b + 0.2 * c, 3)
    return rows


def dataset() -> list[dict]:
    out = []
    for r in _con().execute("SELECT j.*, s.views, s.likes, s.comments, s.avg_pct, s.avg_sec, s.shares, s.subs, s.minutes, s.views7, s.pct7, s.shares7, s.subs7, "
                            "s.published, s.privacy FROM jobs j JOIN stats s ON s.job_id = j.id WHERE j.status='uploaded' ORDER BY j.id"):
        j = dict(r)
        row = {k: j.get(k) for k in ("id", "topic", "youtube_id", "views", "views7", "avg_pct", "pct7", "avg_sec", "likes", "comments", "shares", "subs",
                                     "minutes", "published", "privacy")}
        row.update(features(j))
        v = row["views"] or 0
        row["like_rate"] = round(100 * (row["likes"] or 0) / v, 2) if v else 0
        pub = _parse(row["published"] or "")
        row["published_hour"] = pub.hour if pub else None
        row["published_day"] = pub.strftime("%a") if pub else ""
        out.append(row)
    return with_perf(out)


# ───────────── comparisons ─────────────
def _b(v, cuts, labels):
    for c, l in zip(cuts, labels):
        if v < c:
            return l
    return labels[-1]


def _hour_bucket(r):
    h = r.get("published_hour")
    return None if h is None else ("00-05" if h < 6 else "06-11" if h < 12 else "12-17" if h < 18 else "18-23") + " UTC"


YN = lambda k: (lambda r: "yes" if r[k] else "no")
DIMS = [
    ("kind", "Kind of mystery", "topic", lambda r: r["kind"]),
    ("hook_len", "Hook length", "hook", lambda r: _b(r["hook_words"], (7, 10), ("up to 6 words", "7-9 words", "10+ words"))),
    ("hook_number", "Hook has a number", "hook", YN("hook_number")),
    ("hook_contrast", "Hook has a contradiction word", "hook", YN("hook_contrast")),
    ("hook_question", "Hook is a question", "hook", YN("hook_question")),
    ("hook_year", "Hook starts with a year", "hook", YN("hook_year_first")),
    ("end_question", "Ends with a question", "hook", YN("end_question")),
    ("shot_len", "Average shot length", "animation", lambda r: _b(r["avg_shot_s"], (2.5, 3.5), ("under 2.5 s", "2.5-3.5 s", "over 3.5 s")) if r["avg_shot_s"] else None),
    ("moving", "Moving objects", "animation", lambda r: _b(r["moving_props"], (3, 5), ("0-2", "3-4", "5+"))),
    ("night", "Night and dusk scenes", "animation", lambda r: _b(r["night_pct"], (30, 70), ("under 30%", "30-70%", "over 70%"))),
    ("closeups", "Close-ups", "animation", lambda r: _b(r["closeup_pct"], (15, 30), ("under 15%", "15-30%", "over 30%"))),
    ("callouts", "Text callouts", "animation", lambda r: _b(r["callouts"], (3, 6), ("0-2", "3-5", "6+"))),
    ("duration", "Video length", "animation", lambda r: _b(r["duration"], (35, 45), ("under 35 s", "35-45 s", "45 s and more")) if r["duration"] else None),
    ("music", "Music", "animation", lambda r: r["music"] or None),
    ("voice", "Voice", "animation", lambda r: r["voice"] or None),
    ("pub_hour", "Publish time", "publish", _hour_bucket),
]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def _scored(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("perf") is not None]


def _groups(rows: list[dict], fn) -> list[dict]:
    g: dict = {}
    for r in rows:
        k = fn(r)
        if k is not None:
            g.setdefault(k, []).append(r)
    out = [{"value": k, "n": len(rs), "perf": round(sum(r["perf"] for r in rs) / len(rs), 2), "retention": _mean([_ret(r) for r in rs]),
            "views": _median([r.get("views7") or r.get("views") for r in rs])} for k, rs in g.items()]
    return sorted(out, key=lambda x: -x["perf"])


def _slim(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "topic", "hook_line", "avg_pct", "pct7", "views", "perf")}


def insights(rows: list[dict] | None = None) -> dict:
    rows = dataset() if rows is None else rows
    sc, need = _scored(rows), int(os.getenv("LEARN_MIN_VIDEOS", "8") or 8)
    groups, findings = [], []
    for key, label, grp, fn in DIMS:
        gs = _groups(sc, fn)
        if not gs:
            continue
        groups.append({"key": key, "label": label, "group": grp, "values": gs})
        sol = [g for g in gs if g["n"] >= 2]
        if len(sol) >= 2 and sol[0]["perf"] - sol[-1]["perf"] >= 0.2:
            findings.append({"key": key, "label": label, "group": grp, "best": sol[0]["value"], "worst": sol[-1]["value"],
                             "best_perf": sol[0]["perf"], "worst_perf": sol[-1]["perf"], "best_n": sol[0]["n"], "worst_n": sol[-1]["n"],
                             "confidence": "medium" if min(sol[0]["n"], sol[-1]["n"]) >= 4 else "low"})
    order = sorted(sc, key=lambda r: -r["perf"])
    on = os.getenv("LEARN", "1") != "0"
    return {"videos": len(rows), "scored": len(sc), "needed": need, "learning": on, "ready": on and len(sc) >= need, "groups": groups,
            "findings": findings, "top": [_slim(r) for r in order[:3]], "bottom": [_slim(r) for r in order[-3:][::-1]] if len(order) > 3 else []}


# ───────────── what the assistant takes from it ─────────────
def _ready(rows: list[dict] | None = None) -> bool:
    if os.getenv("LEARN", "1") == "0":
        return False
    rows = dataset() if rows is None else rows
    return len(_scored(rows)) >= int(os.getenv("LEARN_MIN_VIDEOS", "8") or 8)


def _explore() -> float:
    return float(os.getenv("LEARN_EXPLORE", "25") or 25) / 100


def preferred_kind() -> str | None:
    """The kind of mystery that did best, or None (not enough data, learning off, or this pick is an exploration)."""
    rows = dataset()
    if not _ready(rows) or random.random() < _explore():
        return None
    gs = [g for g in _groups(_scored(rows), lambda r: r["kind"]) if g["n"] >= 2]
    return gs[0]["value"] if gs and (len(gs) < 2 or gs[0]["perf"] - gs[-1]["perf"] >= 0.1) else None


def weights() -> dict | None:
    """Score per hook formula and ending formula, for hooks.pick."""
    rows = dataset()
    if not _ready(rows):
        return None
    sc, w = _scored(rows), {"hooks": {}, "ends": {}}
    for field, key, pool in (("hook_type", "hooks", hooks.HOOKS), ("end_type", "ends", hooks.ENDINGS)):
        g: dict = {}
        for r in sc:
            if r.get(field) in pool:
                g.setdefault(r[field], []).append(r["perf"])
        w[key] = {k: sum(v) / len(v) for k, v in g.items() if len(v) >= 2}
    return w if (w["hooks"] or w["ends"]) else None


def _name(r: dict) -> str:
    pct, v = _ret(r), r.get("views7") or r.get("views") or 0
    return f"{r['topic']} ({'' if pct is None else format(pct, '.0f') + '% watched, '}{v} views)"


def hints(kind: str, rows: list[dict] | None = None) -> str:
    """A few lines for the prompts of the AI steps: what worked on this channel. '' until there is enough data or when learning is off."""
    if os.getenv("LEARN", "1") == "0":
        return ""
    rows = dataset() if rows is None else rows
    sc = _scored(rows)
    if len(sc) < int(os.getenv("LEARN_MIN_VIDEOS", "8") or 8):
        return ""
    ins = insights(rows)
    order = sorted(sc, key=lambda r: -r["perf"])
    top, bot, parts = order[:3], (order[-2:][::-1] if len(order) >= 6 else []), []
    if kind == "topic":
        parts.append("What viewers did on this channel (its own YouTube data). Best: " + "; ".join(_name(r) for r in top) + "."
                     + ((" Weakest: " + "; ".join(_name(r) for r in bot) + ".") if bot else ""))
        by = next((g for g in ins["groups"] if g["key"] == "kind"), None)
        if by:
            parts.append("Score by kind of mystery: " + ", ".join(f"{v['value']} {v['perf']}" for v in by["values"]) + ".")
        parts.append("Propose topics like the best ones and unlike the weakest, and keep some variety.")
    elif kind == "hook":
        good, bad = [r for r in top if r.get("hook_line")], [r for r in bot if r.get("hook_line")]
        if good:
            parts.append("Hooks that held viewers on this channel: " + "; ".join(f"\"{r['hook_line']}\"" for r in good) + ".")
        if bad:
            parts.append("Hooks that did not: " + "; ".join(f"\"{r['hook_line']}\"" for r in bad) + ".")
        parts += [f"{f['label']}: '{f['best']}' worked better than '{f['worst']}'." for f in ins["findings"] if f["group"] == "hook"]
        if parts:
            parts.append("Write the new hooks in the style of the ones that worked.")
    elif kind == "storyboard":
        parts = [f"{f['label']}: '{f['best']}' kept viewers better than '{f['worst']}'." for f in ins["findings"] if f["group"] == "animation"]
        if parts:
            parts.insert(0, "What your viewers' retention says about the film style (follow it when it does not conflict with the story):")
    return "\n".join(parts)[:900]


def lessons(n: int = 3) -> str:
    """Used by the topic agent."""
    return hints("topic")


# ───────────── export ─────────────
PREFERRED = ["id", "topic", "youtube_id", "published", "privacy", "views", "views7", "avg_pct", "pct7", "avg_sec", "likes", "comments", "shares", "subs",
             "perf", "kind", "hook_line"]


def export_csv() -> str:
    rows = dataset()
    cols = PREFERRED + sorted({k for r in rows for k in r} - set(PREFERRED))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return "\ufeff" + buf.getvalue()


def export_json() -> str:
    rows = dataset()
    return json.dumps({"exported": dt.datetime.now(dt.timezone.utc).isoformat(), "videos": rows, "insights": insights(rows)}, indent=2, ensure_ascii=False, default=str)