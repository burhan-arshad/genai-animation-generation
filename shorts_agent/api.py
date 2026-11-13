"""FastAPI dashboard + control API. Settings, niches, brand and YouTube are all managed from the web UI.
Local by default (127.0.0.1). To expose it online set HOST=0.0.0.0 AND DASHBOARD_PASSWORD in .env (and put HTTPS in front)."""
from __future__ import annotations

import base64
import json
import os
import re
import secrets as pysecrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from . import brand, niche, settings, store, styles
from .config import HOME, REPO, _path
from .pipeline import FLOW, STAGE_NAME
from .uploader import CLIENT, TOKEN

WEB = Path(__file__).resolve().parent / "web"
LOG = REPO / "logs" / "worker.log"
app = FastAPI(title="shorts-agent")
WORKER: dict = {"proc": None, "cmd": None, "started": None, "stopped": False}
COMMANDS = {
    "run": ["-m", "shorts_agent.pipeline", "run", "--limit", "1"],
    "daily": ["-m", "shorts_agent.daily"],
    "upload": ["-m", "shorts_agent.uploader", "run"],
    "login": ["-m", "shorts_agent.uploader", "login"],
}
VOICES = ["am_adam", "am_michael", "bf_emma", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"]
PROTECTED = {"history", "inventions"}


@app.middleware("http")
async def gate(request: Request, call_next):
    pw = os.getenv("DASHBOARD_PASSWORD")
    if pw:
        ok = False
        h = request.headers.get("authorization", "")
        if h.lower().startswith("basic "):
            try:
                given = base64.b64decode(h[6:]).decode("utf-8").partition(":")[2]
                ok = pysecrets.compare_digest(given.encode(), pw.encode())
            except Exception:
                ok = False
        if not ok:
            return Response("Password required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="shorts-agent"'})
    return await call_next(request)


def _root() -> Path:
    return _path("PROJECTS_ROOT", HOME / "faceless-shorts")


def _project(job: dict) -> Path:
    return _root() / job["slug"]


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _running() -> bool:
    p = WORKER["proc"]
    return p is not None and p.poll() is None


def _kill_tree(proc) -> None:
    """Stop the worker and everything it started (ffmpeg, node...)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _rm_files(job: dict) -> None:
    slug = job.get("slug")
    if not slug:
        return
    root = _root().resolve()
    p = (root / slug).resolve()
    if p.parent == root and p.exists():          # never delete anything outside the projects folder
        shutil.rmtree(p, ignore_errors=True)


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


# ───────────── settings ─────────────
class Values(BaseModel):
    values: dict[str, str]


@app.get("/api/settings")
def get_settings():
    return settings.read()


@app.put("/api/settings")
def put_settings(b: Values):
    errs = settings.update(b.values)
    if errs:
        raise HTTPException(400, "; ".join(errs))
    return {"saved": True}


@app.post("/api/settings/test")
def test_ai():
    from . import llm
    llm._client = None
    try:
        spec = llm._models_for("script")[0]
    except Exception as e:
        return {"ok": False, "msg": str(e)}
    ok, msg = llm.ping(spec)
    return {"ok": ok, "msg": f"{spec}: {msg}"}


@app.get("/api/health")
def health():
    """Runs the doctor in a fresh process, so it sees the newest .env."""
    p = subprocess.run([sys.executable, "-m", "shorts_agent.doctor"], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=90, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = []
    for line in p.stdout.splitlines():
        m = re.match(r"\[( OK |WARN|FAIL)\] (.*)", line)
        if m:
            label, _, detail = m.group(2).partition(": ")
            out.append({"level": m.group(1).strip().lower(), "label": label, "detail": detail})
    return out


# ───────────── niches ─────────────
@app.get("/api/niches")
def niches():
    out = []
    for n in niche.available():
        d = _read_json(niche.DIR / f"{n}.json") or {}
        out.append({"name": n, "label": d.get("label", ""), "mode": (d.get("props") or {}).get("mode", "library"),
                    "protected": n in PROTECTED})
    return out


@app.get("/api/niches/{name}")
def niche_text(name: str):
    p = niche.DIR / f"{name}.json"
    if name not in niche.available():
        raise HTTPException(404, "no such niche")
    return {"text": p.read_text(encoding="utf-8")}


class Text(BaseModel):
    text: str


@app.put("/api/niches/{name}")
def niche_save(name: str, b: Text):
    if name not in niche.available():
        raise HTTPException(404, "no such niche")
    try:
        data = json.loads(b.text)
    except ValueError as e:
        raise HTTPException(400, f"Not valid JSON: {e}")
    errs = settings.save_niche(name, data)
    if errs:
        raise HTTPException(400, "; ".join(errs))
    return {"saved": True}


class NewNiche(BaseModel):
    name: str
    label: str
    theme: str
    topics: str
    objects: str = ""
    avoid: str = ""


@app.post("/api/niches")
def niche_create(b: NewNiche):
    name = b.name.strip().lower()
    if name in niche.available():
        raise HTTPException(400, "a niche with this name already exists")
    if not (b.label.strip() and b.theme.strip() and b.topics.strip()):
        raise HTTPException(400, "fill in the description, what to draw and the topics")
    errs = settings.save_niche(name, settings.build_niche(name, b.label.strip(), b.theme.strip(), b.topics.strip(), b.objects, b.avoid))
    if errs:
        raise HTTPException(400, "; ".join(errs))
    return {"created": name}


@app.delete("/api/niches/{name}")
def niche_delete(name: str):
    if name in PROTECTED:
        raise HTTPException(400, "built-in niches cannot be deleted")
    if name == (os.getenv("NICHE") or "history"):
        raise HTTPException(400, "this niche is active: switch to another one first")
    if name not in niche.available():
        raise HTTPException(404, "no such niche")
    (niche.DIR / f"{name}.json").unlink()
    niche.load.cache_clear()
    return {"deleted": name}


# ───────────── jobs ─────────────
@app.get("/api/jobs")
def jobs():
    out = []
    for r in store.db().execute("SELECT * FROM jobs ORDER BY id DESC"):
        d = dict(r)
        d["has_video"] = (_project(d) / "renders" / "final_norm.mp4").exists()
        out.append(d)
    return out


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    p = _project(job)
    fc = _read_json(p / "factcheck.json") or {}
    claims = fc["history"][-1]["claims"] if fc.get("history") else []
    events = [dict(e) for e in store.db().execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,))]
    for e in events:
        e["stage_name"] = STAGE_NAME.get(e["stage"], e["stage"])
    return {"job": job, "script": _read_json(p / "script.json"), "fact_status": fc.get("status"),
            "claims": [{k: v for k, v in c.items() if k != "evidence"} for c in claims],
            "qa": _read_json(p / "qa.json"), "vision": _read_json(p / "vision.json"), "events": events,
            "has_video": (p / "renders" / "final_norm.mp4").exists()}


@app.get("/api/jobs/{job_id}/video")
def video(job_id: int):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    for name in ("final_norm.mp4", "final.mp4"):
        f = _project(job) / "renders" / name
        if f.exists():
            return FileResponse(f, media_type="video/mp4")
    raise HTTPException(404, "no video yet")


class NewJob(BaseModel):
    topic: str
    style: str | None = None      # ignored: new jobs always use the active niche


@app.post("/api/jobs")
def add_job(b: NewJob):
    topic = b.topic.strip()
    if len(topic) < 5:
        raise HTTPException(400, "topic too short")
    return {"id": store.add_job(topic, styles.default_key())}


class Clear(BaseModel):
    scope: str                  # failed | uploaded | waiting | all
    files: bool = True


SCOPES = {"failed": ("dropped", "rejected"), "uploaded": ("uploaded",), "waiting": ("queued",)}


@app.post("/api/jobs/clear")
def jobs_clear(b: Clear):
    if _running():
        raise HTTPException(409, "Stop the running work first")
    if b.scope != "all" and b.scope not in SCOPES:
        raise HTTPException(400, "unknown scope")
    rows = [dict(r) for r in store.db().execute("SELECT * FROM jobs")]
    if b.scope != "all":
        rows = [r for r in rows if r["status"] in SCOPES[b.scope]]
    if b.files:
        for r in rows:
            _rm_files(r)
    store.delete_jobs([r["id"] for r in rows])
    return {"deleted": len(rows)}


@app.delete("/api/jobs/{job_id}")
def job_delete(job_id: int, files: bool = True):
    if _running():
        raise HTTPException(409, "Stop the running work first")
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if files:
        _rm_files(job)
    store.delete_jobs([job_id])
    return {"deleted": 1}


class Action(BaseModel):
    action: str
    status: str | None = None


@app.post("/api/jobs/{job_id}/action")
def job_action(job_id: int, b: Action):
    if not store.get_job(job_id):
        raise HTTPException(404, "no such job")
    if b.action == "reject":
        store.set_job(job_id, status="rejected")
    elif b.action == "retry":
        store.set_job(job_id, error=None, tries=0)
    elif b.action == "reset":
        if b.status not in FLOW:
            raise HTTPException(400, "bad status")
        store.set_job(job_id, status=b.status, error=None, tries=0)
    else:
        raise HTTPException(400, "unknown action")
    return {"ok": True}


class Suggest(BaseModel):
    n: int = 3
    queue: bool = True


@app.post("/api/topics/suggest")
def suggest(b: Suggest):
    from . import topics
    try:
        ideas = topics.suggest(max(1, min(b.n, 6)))
    except (Exception, SystemExit) as e:
        raise HTTPException(502, str(e)[:300])
    ids = [store.add_job(i.topic, styles.default_key()) for i in ideas] if b.queue else []
    return {"ideas": [i.model_dump() for i in ideas], "queued": ids}


# ───────────── worker (long jobs run in a separate process) ─────────────
class Start(BaseModel):
    cmd: str
    job: int | None = None


@app.post("/api/worker/start")
def worker_start(b: Start):
    if b.cmd not in COMMANDS:
        raise HTTPException(400, "unknown command")
    if _running():
        raise HTTPException(409, "a worker is already running")
    args = list(COMMANDS[b.cmd])
    if b.cmd in ("run", "upload") and b.job:
        args += ["--job", str(b.job)]
    LOG.parent.mkdir(exist_ok=True)
    f = open(LOG, "wb")
    f.write(f"$ python {' '.join(args)}\n".encode())
    f.flush()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, *args], cwd=REPO, stdout=f, stderr=subprocess.STDOUT, env=env, **kw)
    f.close()
    WORKER.update(proc=proc, cmd=b.cmd, started=time.time(), stopped=False)
    return {"started": b.cmd}


@app.get("/api/worker")
def worker():
    p = WORKER["proc"]
    done = p is not None and p.poll() is not None
    return {"running": _running(), "cmd": WORKER["cmd"], "started": WORKER["started"],
            "returncode": p.poll() if done else None, "stopped": WORKER["stopped"]}


@app.post("/api/worker/stop")
def worker_stop():
    if not _running():
        raise HTTPException(409, "nothing is running")
    _kill_tree(WORKER["proc"])
    WORKER["stopped"] = True
    (REPO / "daily.lock").unlink(missing_ok=True)
    with open(LOG, "ab") as f:
        f.write(b"\n[stopped by user]\n")
    return {"stopped": True}


@app.get("/api/worker/log")
def worker_log(offset: int = 0):
    if not LOG.exists():
        return {"text": "", "offset": 0}
    if offset > LOG.stat().st_size:
        offset = 0
    with open(LOG, "rb") as f:
        f.seek(offset)
        data = f.read(65536)
    return {"text": data.decode("utf-8", "replace"), "offset": offset + len(data)}


# ───────────── YouTube ─────────────
@app.get("/api/youtube")
def youtube():
    return {"client": CLIENT.exists(), "token": TOKEN.exists()}


@app.post("/api/youtube/client")
def youtube_client(b: Text):
    try:
        data = json.loads(b.text)
    except ValueError:
        raise HTTPException(400, "This is not a valid JSON file")
    if not isinstance(data, dict) or not ({"installed", "web"} & set(data)):
        raise HTTPException(400, "This does not look like a Google OAuth client file (client_secret.json)")
    CLIENT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"saved": True}


@app.post("/api/youtube/logout")
def youtube_logout():
    TOKEN.unlink(missing_ok=True)
    return {"ok": True}


# ───────────── usage + brand + voices ─────────────
@app.get("/api/usage")
def usage():
    from .llm import _con, _daily_limit, _today
    with _con() as con:
        rows = con.execute("SELECT model, SUM(ok), SUM(1-ok), SUM(in_tokens), SUM(out_tokens) "
                           "FROM llm_calls WHERE day=? GROUP BY model", (_today(),)).fetchall()
    return {"day": _today(), "models": [{"model": m, "ok": o or 0, "failed": f or 0, "in": i or 0, "out": t or 0,
                                         "limit": _daily_limit(m)} for m, o, f, i, t in rows]}


@app.get("/api/voices")
def voices():
    found = {p.stem[6:] for p in (REPO / "brand" / "assets").glob("voice_*.wav")}
    return sorted(found | set(VOICES))


@app.get("/api/voices/{name}/audio")
def voice_audio(name: str):
    f = REPO / "brand" / "assets" / f"voice_{name}.wav"
    if not re.fullmatch(r"[a-z]{2}_[a-z]+", name) or not f.exists():
        raise HTTPException(404, "no preview for this voice")
    return FileResponse(f, media_type="audio/wav")


@app.get("/api/brand")
def get_brand():
    return {"text": json.dumps(brand.load(), indent=2)}


@app.put("/api/brand")
def put_brand(b: Text):
    try:
        data = json.loads(b.text)
        merged = brand._merge(brand.DEFAULTS, data)
        ch = merged["character"]
        if ch["preset"] not in ch["presets"]:
            raise ValueError("character.preset must be one of the keys of character.presets")
        if ch["appear"] not in ("first", "first_last", "none"):
            raise ValueError("character.appear must be first, first_last or none")
        float(merged["voice"]["speed"])
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, str(e))
    brand.PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"saved": True}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost") and not os.getenv("DASHBOARD_PASSWORD"):
        raise SystemExit("Set DASHBOARD_PASSWORD in .env before exposing the dashboard (HOST is not local).")
    uvicorn.run(app, host=host, port=int(os.getenv("PORT", "8000")))