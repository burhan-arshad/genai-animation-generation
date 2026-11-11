"""LLM layer: per-task model chains, error classification, usage log, daily + per-minute budget guard."""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
DB = Path(__file__).resolve().parent.parent / "usage.db"
SAFETY_MARGIN = 2
_client = None
_cool: dict[str, float] = {}      # model -> time until which we skip it after a 429
LAST: dict = {}                    # model and finish reason of the most recent successful call (for diagnostics)

class BudgetExceeded(RuntimeError):
    """Quota hit on every model in the chain: pause and resume later."""


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
        id INTEGER PRIMARY KEY, day TEXT, ts REAL, model TEXT, task TEXT,
        in_tokens INTEGER, out_tokens INTEGER, ok INTEGER)""")
    return con


def _today() -> str:  # Google resets daily quota at midnight Pacific
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _models_for(task: str) -> list[str]:
    key = task.upper()
    base = key[:-5] if key.endswith("_HARD") else key
    raw = (os.getenv(f"GEMINI_MODEL_{key}") or os.getenv(f"GEMINI_MODEL_{base}") or os.getenv("GEMINI_MODEL") or "")
    models = list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))
    if not models:
        raise RuntimeError(f"Set GEMINI_MODEL or GEMINI_MODEL_{base} in .env")
    return models


def _env_limit(var: str, model: str, default: int) -> int:
    for part in os.getenv(var, "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() == model:
                return int(v)
    return default


def _daily_limit(model: str) -> int:
    return _env_limit("DAILY_LIMITS", model, int(os.getenv("DEFAULT_DAILY_LIMIT", "20")))


def _rpm_limit(model: str) -> int:
    return _env_limit("RPM_LIMITS", model, int(os.getenv("DEFAULT_RPM_LIMIT", "5")))


def _used_today(model: str) -> int:
    with _con() as con:
        return con.execute("SELECT COUNT(*) FROM llm_calls WHERE day=? AND model=? AND ok=1",
                           (_today(), model)).fetchone()[0]


def _recent(model: str) -> list[float]:
    with _con() as con:
        return [r[0] for r in con.execute("SELECT ts FROM llm_calls WHERE model=? AND ts>? ORDER BY ts",
                                          (model, time.time() - 60))]


def _log(model: str, task: str, resp, ok: bool) -> None:
    um = getattr(resp, "usage_metadata", None)
    tin = getattr(um, "prompt_token_count", None) or 0
    tout = getattr(um, "candidates_token_count", None) or 0
    with _con() as con:
        con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) VALUES(?,?,?,?,?,?,?)",
                    (_today(), time.time(), model, task, tin, tout, int(ok)))

def _finish(resp) -> str:
    try:
        return str(resp.candidates[0].finish_reason)
    except Exception:
        return "?"

def _classify(e: Exception) -> str:
    """'quota' (429) | 'transient' (5xx / network) | 'fatal' (bad request, auth, not found)."""
    code = getattr(e, "code", None)
    if code == 429:
        return "quota"
    if code is None or (isinstance(code, int) and code >= 500):
        return "transient"
    return "fatal"


def _try_model(model: str, prompt: str, cfg, task: str):
    """Returns (response, None) or (None, error). 5xx/network: up to 3 tries with backoff. 429: stop and cool the model down."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = _get_client().models.generate_content(model=model, contents=prompt, config=cfg)
            _log(model, task, resp, True)
            LAST["model"], LAST["finish"] = model, _finish(resp)
            return resp, None
        except Exception as e:
            _log(model, task, None, False)
            kind = _classify(e)
            if kind == "fatal":
                raise
            if kind == "quota":
                _cool[model] = time.time() + 60
                print(f"[llm] {model} -> 429, cooling down 60s, trying the next model")
                return None, BudgetExceeded(f"{model}: Google returned 429 (check aistudio.google.com/rate-limit)")
            last = e
            wait = 5 * 2 ** attempt
            print(f"[llm] {model} transient error ({type(e).__name__}); retry in {wait}s")
            time.sleep(wait)
    return None, last


def _call(prompt: str, cfg, task: str):
    chain = _models_for(task)
    last: Exception | None = None
    for _ in range(4):
        soonest: float | None = None
        for model in chain:
            now = time.time()
            if _cool.get(model, 0) > now:
                soonest = min(soonest or 1e18, _cool[model])
                continue
            used, limit = _used_today(model), _daily_limit(model)
            if used >= limit - SAFETY_MARGIN:
                last = BudgetExceeded(f"{model}: {used}/{limit} used today")
                continue
            recent, rpm = _recent(model), _rpm_limit(model)
            if len(recent) >= rpm:                                   # per-minute budget used: skip, do not waste a 429
                soonest = min(soonest or 1e18, recent[-rpm] + 61)
                continue
            resp, err = _try_model(model, prompt, cfg, task)
            if resp is not None:
                return resp
            last = err
            if model in _cool:
                soonest = min(soonest or 1e18, _cool[model])
        if soonest is None:
            break
        wait = min(max(soonest - time.time(), 1), 65)
        print(f"[llm] every model is rate-limited; waiting {wait:.0f}s")
        time.sleep(wait)
    raise last or BudgetExceeded("no model available for task " + task)


def generate_structured(prompt: str, schema, system: str | None = None,
                        temperature: float = 0.8, task: str = "script", images: list[bytes] | None = None):
    cfg = types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json",
        response_schema=schema, temperature=temperature)
    contents = prompt if not images else [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in images] + [prompt]
    return schema.model_validate_json(_call(contents, cfg, task).text)


def generate_text(prompt: str, system: str | None = None, temperature: float = 0.6,
                  max_output_tokens: int = 32000, task: str = "storyboard",
                  grounded: bool = False) -> str:
    extra = {"tools": [types.Tool(google_search=types.GoogleSearch())]} if grounded else {}
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=temperature,
        max_output_tokens=max_output_tokens, **extra)
    return _call(prompt, cfg, task).text or ""


def usage_report() -> None:
    with _con() as con:
        rows = con.execute(
            "SELECT model, SUM(ok), SUM(in_tokens), SUM(out_tokens), SUM(1-ok) "
            "FROM llm_calls WHERE day=? GROUP BY model", (_today(),)).fetchall()
    print(f"Quota day (Pacific): {_today()}")
    for m, n, i, o, f in rows:
        print(f"  {m}: {n or 0}/{_daily_limit(m)} ok calls, {i or 0} in / {o or 0} out tokens, {f or 0} failed")
    if not rows:
        print("  no calls logged today")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["usage"]:
        usage_report()
    elif len(a) == 3 and a[0] == "seed":
        for _ in range(int(a[2])):
            with _con() as con:
                con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) "
                            "VALUES(?,?,?,?,0,0,1)", (_today(), time.time(), a[1], "seed"))
        usage_report()
    else:
        print("usage: python -m shorts_agent.llm usage | seed <model> <n>")