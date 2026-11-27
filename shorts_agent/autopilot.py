"""The assistant: one run does the whole job.
  topic -> script -> fact-check -> voice -> storyboard -> render -> quality check -> upload (scheduled in the next free slot)
Every step has its own settings (autopilot.json, dashboard tab 'Assistant'). It keeps a few videos ready ahead, stops a video that costs
too many tokens, and stops the day when too many videos failed.
  python -m shorts_agent.autopilot --once       one run (what the Task Scheduler starts, through shorts_agent.daily)
  python -m shorts_agent.autopilot --loop       keeps running, one run every `loop_minutes`
  python -m shorts_agent.autopilot --status"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import traceback
from zoneinfo import ZoneInfo

from . import notify, quality, schedule, store, styles, uploader
from .config import REPO
from .llm import tokens_between
from . import llm as _llm
from .pipeline import FLOW, TERMINAL, run as run_pipeline

PATH = REPO / "autopilot.json"
STATE = REPO / "logs" / "assistant_state.json"
LOCK = REPO / "daily.lock"
WORKING = ("queued", "scripted", "verified", "timed", "storyboarded", "rendered", "finalized")

# key, label, kind, default, hint, group, env variable it sets for the pipeline (None = the assistant's own setting)
FIELDS = [
    ("enabled", "Assistant is on", "select:1,0", "1", "0 = the daily run does nothing.", "main", None),
    ("mode", "What to do with a finished video", "select:schedule,private,manual", "schedule",
     "schedule = upload as private and publish in the next free slot. private = upload as private, you publish it. manual = only make the video; you press Upload now or Schedule.", "main", None),
    ("buffer", "Videos to keep ready ahead", "number", "2", "The assistant makes videos until this many are ready or scheduled. With one video a day, 2 means two days of buffer.", "main", None),
    ("run_time", "Daily run (this computer's time)", "time", "12:00", "Used by 'Turn the daily run on'. The computer must be on.", "main", None),
    ("use_my_queue", "Use my own queued topics first", "select:1,0", "1", "0 = the assistant ignores the topics you added by hand.", "topic", None),
    ("topic_tries", "Topic ideas to try per video", "number", "3", "If an idea is rejected or its video fails, ask for another one, up to this many times a run.", "topic", None),
    ("topic_web_probe", "A second reliable source must exist", "select:1,0", "1", "Needs the Tavily key. Topics with only one source are skipped.", "topic", "TOPIC_WEB_PROBE"),
    ("topic_min_facts", "Checkable facts a topic needs", "number", "3", "Paragraphs with numbers or dates in the research.", "topic", "TOPIC_MIN_FACTS"),
    ("script_tries", "Script attempts", "number", "4", "More attempts = more tokens when the writer struggles.", "script", "SCRIPT_TRIES"),
    ("script_accept_soft", "Accept a script with only style notes", "select:1,0", "1", "Length a little off, weak ending: accepted from the 3rd attempt. Facts are never accepted loosely.", "script", "SCRIPT_ACCEPT_SOFT"),
    ("min_sources", "Different pages a script must cite", "number", "2", "1 = a script may rely on one page.", "script", "MIN_SOURCES"),
    ("evidence_items", "Evidence paragraphs for the writer", "number", "10", "", "script", "EVIDENCE_ITEMS"),
    ("evidence_chars", "Characters per evidence paragraph", "number", "600", "", "script", "EVIDENCE_CHARS"),
    ("fact_mode", "Fact-check mode", "select:line,claims", "line", "line = every line against the evidence it was written from (cheap, reliable). claims = the old way (many calls).", "fact", "FACT_MODE"),
    ("fact_repair_rounds", "Rewrite rounds for unsupported lines", "number", "2", "", "fact", "FACT_REPAIR_ROUNDS"),
    ("fact_web", "Use a second source to confirm a doubtful line", "select:1,0", "1", "Needs the Tavily key (1 credit per doubtful line).", "fact", "FACT_WEB"),
    ("fact_web_max", "Second-source lookups per video", "number", "3", "", "fact", "FACT_WEB_MAX"),
    ("fact_max_weak", "Unverified claims allowed (claims mode only)", "number", "1", "", "fact", "FACT_MAX_WEAK"),
    ("voice_engine", "Voice", "select:gemini,kokoro", "gemini", "gemini = an actor (falls back to Kokoro when it fails). kokoro = local, free, flat.", "voice", "VOICE_ENGINE"),
    ("voice_segments", "Voice scenes per video", "number", "3", "Gemini free allows 3 requests a minute.", "voice", "VOICE_SEGMENTS"),
    ("storyboard_rounds", "Storyboard attempts", "number", "2", "", "voice", "STORYBOARD_ROUNDS"),
    ("chunk_lines", "Storyboard: script lines per AI call", "number", "3", "Small calls fit a free Groq model.", "voice", "STORYBOARD_CHUNK_LINES"),
    ("render_profile", "Render quality", "select:draft,balanced,quality", "balanced", "", "render", "RENDER_PROFILE"),
    ("render_fps", "Frames drawn per second", "select:15,10,30", "15", "15 = half the work, saved at 30 fps. 30 = every frame.", "render", "RENDER_FPS"),
    ("render_workers", "Parallel render workers", "number", "3", "", "render", "RENDER_WORKERS"),
    ("min_score", "Minimum quality score (0-100)", "number", "70", "Fact-check 30, quality check 25, storyboard 30, duration 10, thumbnail 5.", "quality", None),
    ("hold_below", "Hold a video below the minimum", "select:1,0", "1", "1 = it is not uploaded; you see why and press Upload now or Schedule yourself.", "quality", None),
    ("sched_tz", "Time zone of the schedule", "text", "UTC", "For example UTC, America/New_York, Europe/London, Asia/Karachi.", "publish", "SCHEDULE_TZ"),
    ("sched_times", "Publish times (24-hour, in that time zone)", "text", "18:00", "Comma separated, for example 18:00 or 09:30, 18:00.", "publish", "SCHEDULE_TIMES"),
    ("sched_days", "Publish days", "text", "mon,tue,wed,thu,fri,sat,sun", "Comma separated.", "publish", "SCHEDULE_DAYS"),
    ("videos_per_day", "Videos per day", "number", "1", "", "publish", "SCHEDULE_PER_DAY"),
    ("tokens_per_video", "Most tokens one video may cost", "number", "150000", "A video above this is dropped and another topic is tried.", "safety", None),
    ("failed_per_day", "Failed videos that stop the day", "number", "3", "", "safety", None),
    ("stage_failures", "Failures of one step before the video is dropped", "number", "2", "", "safety", None),
    ("hook_agent", "Write the opening lines in a separate step", "select:1,0", "1", "6 hook candidates, the strongest by rules is used. One small extra call.", "script", "HOOK_AGENT"),
    ("topic_min_pages", "Pages of research a topic needs", "number", "2", "", "topic", "TOPIC_MIN_PAGES"),
    ("topic_min_chars", "Characters of research text a topic needs", "number", "2500", "", "topic", "TOPIC_MIN_CHARS"),
    ("learn", "Learn from my YouTube stats", "select:1,0", "1", "Topics, hooks and film style lean towards what worked on your channel. Videos count after 2 days public.", "learn", "LEARN"),
    ("learn_min_videos", "Videos with data before it learns", "number", "8", "With fewer videos the numbers are noise.", "learn", "LEARN_MIN_VIDEOS"),
    ("learn_explore", "Choices that stay random (%)", "number", "25", "Keeps trying new things so the channel does not get stuck. 0 = always follow the data.", "learn", "LEARN_EXPLORE"),
    ("budget_gate", "Do not start a video the AI budget cannot finish", "select:1,0", "1",
     "Needs DAILY_TOKENS in .env (tokens per day of each Groq model). A video that stops half way wastes the tokens already spent.", "safety", None),
]
KIND = {f[0]: f[2] for f in FIELDS}


def _stored() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load() -> dict:
    st = _stored()
    return {f[0]: str(st[f[0]]) if f[0] in st else f[3] for f in FIELDS}


def env_overrides() -> dict:
    """The environment variables the saved settings set for every pipeline process (only what you saved)."""
    st = _stored()
    return {f[6]: str(st[f[0]]).strip() for f in FIELDS if f[6] and f[0] in st and str(st[f[0]]).strip() != ""}


def _check(key: str, kind: str, v: str) -> str | None:
    if "\n" in v or "\r" in v:
        return "no line breaks"
    if kind == "number" and not v.isdigit():
        return "must be a number"
    if kind.startswith("select:") and v not in kind[7:].split(","):
        return "invalid choice"
    if kind == "time" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
        return "must look like 12:30"
    if key == "sched_times" and not all(re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", t) for t in re.split(r"[,; ]+", v) if t):
        return "times like 18:00 or 09:30, 18:00"
    if key == "sched_days" and not all(d[:3] in schedule.DAYS for d in re.split(r"[,; ]+", v.lower()) if d):
        return "days like mon,tue,wed"
    if key == "sched_tz":
        try:
            ZoneInfo(v)
        except Exception:
            return "unknown time zone (example: UTC or Asia/Karachi)"
    return None


def save(values: dict) -> list[str]:
    clean, errs = {}, []
    for k, v in values.items():
        if k not in KIND:
            continue
        v = str(v if v is not None else "").strip()
        e = _check(k, KIND[k], v)
        if e:
            errs.append(f"{k}: {e}")
        else:
            clean[k] = v
    if errs:
        return errs
    st = _stored()
    st.update(clean)
    PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return []


def fields() -> list[dict]:
    st, out = _stored(), []
    for key, label, kind, default, hint, group, env in FIELDS:
        value = str(st[key]) if key in st else ((os.getenv(env) or "").strip() if env and os.getenv(env) else default)
        if kind.startswith("select:") and value not in kind[7:].split(","):
            value = default
        out.append({"key": key, "label": label, "kind": kind, "hint": hint, "group": group, "value": value})
    return out


# ───────────── what is going on ─────────────
def _now_s() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def budget_left() -> dict | None:
    """Tokens left today on the models that have a DAILY_TOKENS limit (a model that is waiting for its reset counts as 0). None = no model has one."""
    specs: list[str] = []
    for t in ("research", "topics", "factcheck", "judge", "hook", "script", "storyboard"):
        try:
            specs += [s for s in _llm._models_for(t) if s not in specs]
        except RuntimeError:
            pass
    left, n, resets = 0, 0, []
    for s in specs:
        tl = _llm._token_limit(s)
        if not tl:
            continue
        n += 1
        resets.append(_llm._next_reset(s))
        if _llm._blocked_until(s) <= time.time() and _llm._used_today(s) < _llm._daily_limit(s) - _llm.SAFETY_MARGIN:
            left += max(0, tl - _llm._tokens_today(s))
    return {"left": left, "models": n, "resets": min(resets)} if n else None


def video_cost() -> int:
    """What a video costs in tokens: the median of the last five finished ones (100000 until there are any)."""
    xs = sorted(r[0] for r in store.db().execute("SELECT tokens FROM jobs WHERE tokens > 0 AND status IN ('ready','uploaded') ORDER BY id DESC LIMIT 5"))
    return xs[len(xs) // 2] if xs else 100000

def ahead() -> int:
    """Videos made and not yet published: finished ones plus the scheduled ones."""
    con = store.db()
    ready = con.execute("SELECT COUNT(*) FROM jobs WHERE status='ready'").fetchone()[0]
    sched = con.execute("SELECT COUNT(*) FROM jobs WHERE status='uploaded' AND publish_at > ?", (_now_s(),)).fetchone()[0]
    return ready + sched


def failed_today() -> int:
    return store.db().execute("SELECT COUNT(*) FROM jobs WHERE status='dropped' AND source='assistant' "
                              "AND date(updated,'unixepoch','localtime')=date('now','localtime')").fetchone()[0]


def next_job(cfg: dict):
    marks = ",".join("?" * len(WORKING))
    q = f"SELECT * FROM jobs WHERE status IN ({marks})" + ("" if cfg["use_my_queue"] == "1" else " AND source='assistant'")
    row = store.db().execute(q + " ORDER BY (error IS NOT NULL), id LIMIT 1", WORKING).fetchone()
    return dict(row) if row else None


def status() -> dict:
    cfg, con = load(), store.db()
    cur = next_job({**cfg, "use_my_queue": "1"})
    ready = [dict(r) for r in con.execute("SELECT id, topic, score, note FROM jobs WHERE status='ready' ORDER BY id")]
    sched = [dict(r) for r in con.execute("SELECT id, topic, publish_at FROM jobs WHERE status='uploaded' AND publish_at > ? ORDER BY publish_at", (_now_s(),))]
    z = ZoneInfo(schedule.settings()["tz"])
    slots = [{"utc": schedule.iso(s), "local": s.astimezone(z).strftime("%a %d %b %H:%M")} for s in schedule.next_slots(3)]
    try:
        last = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = None
    return {"enabled": cfg["enabled"] == "1", "mode": cfg["mode"], "working_on": {k: cur[k] for k in ("id", "topic", "status")} if cur else None,
            "ready": ready,"budget": budget_left(), "scheduled": sched, "target": int(cfg["buffer"]), "next_slots": slots, "last_run": last}


# ───────────── the work ─────────────
def work_job(job_id: int, cfg: dict, notes: list[str]) -> str:
    """Run one video stage by stage. -> 'ready' | 'dropped' | 'stopped' (provider busy or out of budget) | the final status."""
    cap, max_fail, fails = int(cfg["tokens_per_video"]), int(cfg["stage_failures"]), 0
    while True:
        job = store.get_job(job_id)
        st = job["status"]
        if st == "ready":
            return "ready"
        if st not in WORKING:
            return st
        if int(job.get("tokens") or 0) > cap:
            store.set_job(job_id, status="dropped", error=f"assistant: this video used more than {cap} tokens")
            notes.append(f"Dropped job {job_id} ({job['topic']}): more than {cap} tokens spent.")
            return "dropped"
        t0 = time.time()
        stop = run_pipeline(1, job_id, FLOW[FLOW.index(st) + 1])
        after = store.get_job(job_id)
        store.set_job(job_id, tokens=int(after.get("tokens") or 0) + tokens_between(t0, time.time()))
        if stop in ("budget", "overload"):
            notes.append(f"Stopped on job {job_id}: {'the AI budget is used up' if stop == 'budget' else 'the AI provider is overloaded'}. The next run continues.")
            return "stopped"
        if after["status"] == st:                                  # the step failed and the video is still alive
            fails += 1
            if fails >= max_fail:
                store.set_job(job_id, status="dropped", error=f"assistant: the step '{st}' failed {fails} times: {str(after.get('error') or '')[:300]}")
                notes.append(f"Dropped job {job_id} ({job['topic']}): step '{st}' failed {fails} times.")
                return "dropped"
        else:
            fails = 0
        if store.get_job(job_id)["status"] == "dropped":
            notes.append(f"Dropped job {job_id} ({job['topic']}): {str(store.get_job(job_id).get('error') or '')[:200]}")
            return "dropped"


def new_topic_job(cfg: dict, notes: list[str]):
    from . import topics
    from .llm import BudgetExceeded
    for _ in range(max(1, int(cfg["topic_tries"]))):
        try:
            ideas = topics.suggest(1)
        except BudgetExceeded as e:
            notes.append(f"No topic: the AI budget is used up ({str(e)[:80]}).")
            return None
        except (Exception, SystemExit) as e:
            notes.append(f"The topic agent failed: {str(e)[:150]}")
            continue
        if ideas:
            jid = store.add_job(ideas[0].topic, styles.default_key())
            store.set_job(jid, source="assistant")
            notes.append(f"New topic: {ideas[0].topic}")
            return jid
    notes.append("No suitable topic was found this run.")
    return None


def publish_ready(cfg: dict, notes: list[str]) -> str:
    """Quality-check every finished video and upload it as the mode says. -> 'ok' | 'auth' | 'upload_error'."""
    if cfg["mode"] == "manual":
        return "ok"
    for r in store.db().execute("SELECT * FROM jobs WHERE status='ready' ORDER BY id").fetchall():
        job = dict(r)
        sc, why = quality.score(job)
        if cfg["hold_below"] == "1" and sc < int(cfg["min_score"]):
            store.set_job(job["id"], score=sc, note=f"hold: score {sc} is below {cfg['min_score']}: " + "; ".join(why))
            notes.append(f"Held job {job['id']} ({job['topic']}): quality score {sc}. {'; '.join(why)[:200]}")
            continue
        store.set_job(job["id"], score=sc, note=None)
        try:
            urls = uploader.upload_ready(1, job["id"], mode="schedule" if cfg["mode"] == "schedule" else "private")
        except uploader.AuthError as e:
            notes.append(f"YOUTUBE LOGIN PROBLEM: {e}")
            return "auth"
        except uploader.UploadError as e:
            notes.append(f"UPLOAD FAILED: {e}")
            return "upload_error"
        for u in urls:
            notes.append(f"Uploaded ({cfg['mode']}): {u}  (quality score {sc})")
    return "ok"


def _cycle(cfg: dict, notes: list[str], made: list[int]) -> int:
    code = {"auth": 2, "upload_error": 3}
    while True:
        r = publish_ready(cfg, notes)
        if r != "ok":
            return code[r]
        job = next_job(cfg)
        if job is None:
            if ahead() >= int(cfg["buffer"]):
                notes.append(f"{ahead()} video(s) are ready or scheduled: nothing to make.")
                return 0
            if failed_today() >= int(cfg["failed_per_day"]):
                notes.append(f"{failed_today()} videos failed today: the assistant stops for today.")
                return 0
            if cfg["budget_gate"] == "1":
                b, need = budget_left(), video_cost()
                if b and b["left"] < need:
                    notes.append(f"Not starting a new video: about {b['left']} tokens are left today and a video needs about {need}. "
                                 f"The next run after {time.strftime('%a %H:%M', time.localtime(b['resets']))} continues.")
                    return 0
            jid = new_topic_job(cfg, notes)
            if jid is None:
                return 0
            job = store.get_job(jid)
        res = work_job(job["id"], cfg, notes)
        if res == "stopped":
            return 0
        if res == "ready":
            made.append(job["id"])


# ───────────── entry points ─────────────
def _log_to_file() -> None:
    if sys.stdout is None or sys.stderr is None:           # started by the Task Scheduler without a console
        (REPO / "logs").mkdir(exist_ok=True)
        f = open(REPO / "logs" / "daily.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f


def _keep_awake() -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        except Exception:
            pass

def _refresh_stats(cfg: dict, notes: list[str]) -> None:
    if cfg["learn"] != "1":
        return
    try:
        from . import analytics
        if analytics.stale(12):
            r = analytics.refresh()
            if r["updated"]:
                notes.append(f"Channel stats refreshed for {r['updated']} video(s).")
    except Exception as e:
        notes.append(f"Stats refresh skipped: {type(e).__name__}: {str(e)[:100]}")

def _acquire() -> bool:
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 4 * 3600:
        return False
    LOCK.write_text(str(os.getpid()))
    return True


def _save_state(notes: list[str], made: list[int], code: int) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "made": made, "code": code, "notes": [n[:300] for n in notes][-12:]}), encoding="utf-8")


def run_once(force: bool = False) -> int:
    _log_to_file()
    _keep_awake()
    print(time.strftime("=== assistant run %Y-%m-%d %H:%M:%S ==="))
    cfg = load()
    if cfg["enabled"] != "1" and not force:
        print("the assistant is switched off (dashboard, Assistant tab)")
        return 0
    if not _acquire():
        print("another run is active (lock younger than 4 h). Exiting.")
        return 0
    os.environ.update(env_overrides())
    notes, made, code = [], [], 0
    try:
        _refresh_stats(cfg, notes)
        code = _cycle(cfg, notes, made)
    except Exception:
        notes.append("CRASH:\n" + traceback.format_exc())
        code = 1
    finally:
        LOCK.unlink(missing_ok=True)
    _save_state(notes, made, code)
    print("\n".join(notes) or "nothing to do")
    if notes or made:
        notify.send(f"[assistant] {len(made)} video(s) made" + ("" if code == 0 else f" (problem, code {code})"), "\n".join(notes) or "done")
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even when the assistant is switched off")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(json.dumps(status(), indent=2, default=str))
        return 0
    return run_once(a.force)


if __name__ == "__main__":
    sys.exit(main())