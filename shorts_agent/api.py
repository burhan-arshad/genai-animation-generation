"""FastAPI dashboard + control API. Local use only: binds to 127.0.0.1, no authentication."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from . import brand, store, styles
from .config import PROJECTS_ROOT, REPO
from .pipeline import FLOW, STAGE_NAME

WEB = Path(__file__).resolve().parent / "web"
LOG = REPO / "logs" / "worker.log"
app = FastAPI(title="shorts-agent")
WORKER: dict = {"proc": None, "cmd": None, "started": None}
COMMANDS = {
    "run": ["-m", "shorts_agent.pipeline", "run", "--limit", "1"],
    "daily": ["-m", "shorts_agent.daily"],
    "upload": ["-m", "shorts_agent.uploader", "run"],
}


def _project(job: dict) -> Path:
    return PROJECTS_ROOT / job["slug"]


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _running() -> bool:
    p = WORKER["proc"]
    return p is not None and p.poll() is None


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


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
            "qa": _read_json(p / "qa.json"), "events": events,
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
    style: str = "history"


@app.post("/api/jobs")
def add_job(b: NewJob):
    topic = b.topic.strip()
    if len(topic) < 5:
        raise HTTPException(400, "topic too short")
    try:
        styles.set_active(b.style)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": store.add_job(topic, b.style)}


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
    except Exception as e:
        raise HTTPException(502, str(e)[:300])
    ids = [store.add_job(i.topic, os.getenv("STYLE", "history")) for i in ideas] if b.queue else []
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
    if b.cmd == "run" and b.job:
        args += ["--job", str(b.job)]
    LOG.parent.mkdir(exist_ok=True)
    f = open(LOG, "wb")
    f.write(f"$ python {' '.join(args)}\n".encode())
    f.flush()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, *args], cwd=REPO, stdout=f, stderr=subprocess.STDOUT, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    f.close()
    WORKER.update(proc=proc, cmd=b.cmd, started=time.time())
    return {"started": b.cmd}


@app.get("/api/worker")
def worker():
    p = WORKER["proc"]
    done = p is not None and p.poll() is not None
    return {"running": _running(), "cmd": WORKER["cmd"], "started": WORKER["started"],
            "returncode": p.poll() if done else None}


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


# ───────────── usage + brand ─────────────
@app.get("/api/usage")
def usage():
    from .llm import _con, _daily_limit, _today
    with _con() as con:
        rows = con.execute("SELECT model, SUM(ok), SUM(1-ok), SUM(in_tokens), SUM(out_tokens) "
                           "FROM llm_calls WHERE day=? GROUP BY model", (_today(),)).fetchall()
    return {"day": _today(), "models": [{"model": m, "ok": o or 0, "failed": f or 0, "in": i or 0, "out": t or 0,
                                         "limit": _daily_limit(m)} for m, o, f, i, t in rows]}


@app.get("/api/brand")
def get_brand():
    return {"text": json.dumps(brand.load(), indent=2)}


class BrandText(BaseModel):
    text: str


@app.put("/api/brand")
def put_brand(b: BrandText):
    try:
        data = json.loads(b.text)
        merged = brand._merge(brand.DEFAULTS, data)
        ch = merged["character"]
        if ch["preset"] not in ch["presets"]:
            raise ValueError("character.preset must be one of the keys of character.presets")
        if ch["appear"] not in ("first", "first_last", "none"):
            raise ValueError("character.appear must be first, first_last or none")
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, str(e))
    brand.PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"saved": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))