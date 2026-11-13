"""LLM layer: provider-agnostic model chains (Gemini and any OpenAI-compatible API), health-aware failover,
usage log, daily and per-minute budget guards.

A model is written as `gemini-3.5-flash-lite` (Gemini) or `provider:model` (any OpenAI-compatible API, e.g.
`groq:llama-3.3-70b-versatile`; configure PROVIDER_<NAME>_URL and PROVIDER_<NAME>_KEY in .env).
A chain is a comma-separated list tried in order, e.g. GEMINI_MODEL_SCRIPT=a,b,groq:c .
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()
DB = Path(__file__).resolve().parent.parent / "usage.db"
SAFETY_MARGIN = 2
LAST: dict = {}                      # model spec and finish reason of the latest successful call
_client = None
_cool: dict[str, float] = {}         # spec -> skip until (after a 429)
_bad: dict[str, float] = {}          # spec -> skip until (not configured, or a fatal error such as a bad key or unknown model)


class BudgetExceeded(RuntimeError):
    """Quota hit on every model in the chain: pause and resume later."""


class ProviderError(RuntimeError):
    def __init__(self, code: int, msg: str):
        super().__init__(f"HTTP {code}: {msg}")
        self.code = code


class Skip(Exception):
    """This model cannot serve the request (not configured / unsupported): move on."""


# ───────────── usage log ─────────────
def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
        id INTEGER PRIMARY KEY, day TEXT, ts REAL, model TEXT, task TEXT,
        in_tokens INTEGER, out_tokens INTEGER, ok INTEGER)""")
    return con


def _today() -> str:  # Google resets the daily quota at midnight Pacific
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def _log(spec: str, task: str, tin: int, tout: int, ok: bool) -> None:
    with _con() as con:
        con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) VALUES(?,?,?,?,?,?,?)",
                    (_today(), time.time(), spec, task, tin or 0, tout or 0, int(ok)))


def _used_today(spec: str) -> int:
    with _con() as con:
        return con.execute("SELECT COUNT(*) FROM llm_calls WHERE day=? AND model=? AND ok=1", (_today(), spec)).fetchone()[0]


def _recent(spec: str) -> list[float]:
    with _con() as con:
        return [r[0] for r in con.execute("SELECT ts FROM llm_calls WHERE model=? AND ts>? ORDER BY ts",
                                          (spec, time.time() - 60))]


# ───────────── chains and limits ─────────────
def _split(spec: str) -> tuple[str, str]:
    if ":" in spec:
        provider, _, name = spec.partition(":")
        return provider.strip().lower(), name.strip()
    return "gemini", spec.strip()


def _models_for(task: str) -> list[str]:
    key = task.upper()
    base = key[:-5] if key.endswith("_HARD") else key
    raw = (os.getenv(f"GEMINI_MODEL_{key}") or os.getenv(f"GEMINI_MODEL_{base}") or os.getenv("GEMINI_MODEL") or "")
    models = list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))
    if not models:
        raise RuntimeError(f"Set GEMINI_MODEL or GEMINI_MODEL_{base} in .env")
    return models


def _env_limit(var: str, spec: str, default: int) -> int:
    for part in os.getenv(var, "").split(","):
        if ":" in part:
            k, v = part.rsplit(":", 1)
            if k.strip() == spec and v.strip().isdigit():
                return int(v)
    return default


def _daily_limit(spec: str) -> int:
    return _env_limit("DAILY_LIMITS", spec, int(os.getenv("DEFAULT_DAILY_LIMIT", "20")))


def _rpm_limit(spec: str) -> int:
    return _env_limit("RPM_LIMITS", spec, int(os.getenv("DEFAULT_RPM_LIMIT", "5")))


def _unhealthy_until(spec: str) -> float:
    """Circuit breaker derived from the log: the last two calls failed -> skip the model for BREAKER seconds after the last failure.
    After that one probe call decides: success closes the breaker, another failure opens it again."""
    with _con() as con:
        rows = con.execute("SELECT ts, ok FROM llm_calls WHERE model=? ORDER BY id DESC LIMIT 2", (spec,)).fetchall()
    if len(rows) == 2 and not rows[0][1] and not rows[1][1]:
        until = rows[0][0] + float(os.getenv("LLM_BREAKER_SECONDS", "180"))
        return until if until > time.time() else 0.0
    return 0.0


def _classify(e: Exception) -> str:
    """'quota' (429) | 'transient' (5xx, timeouts, network) | 'fatal' (bad request, bad key, unknown model)."""
    code = getattr(e, "code", None)
    if code == 429:
        return "quota"
    if code is None or (isinstance(code, int) and code >= 500):
        return "transient"
    return "fatal"


def _extract_json(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    a, b = t.find("{"), t.rfind("}")
    return t[a:b + 1] if a != -1 and b > a else t


# ───────────── providers ─────────────
def _http_options(types):
    ms = int(os.getenv("LLM_TIMEOUT_MS", "180000"))
    try:                                          # our own failover handles retries: no hidden SDK retries
        return types.HttpOptions(timeout=ms, retry_options=types.HttpRetryOptions(attempts=1))
    except Exception:
        return types.HttpOptions(timeout=ms)


def _gemini(model: str, req: dict):
    global _client
    from google import genai
    from google.genai import types
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise Skip("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key, http_options=_http_options(types))
    kw = {"tools": [types.Tool(google_search=types.GoogleSearch())]} if req["grounded"] else {}
    if req["schema"] is not None:
        cfg = types.GenerateContentConfig(system_instruction=req["system"], temperature=req["temperature"],
                                          response_mime_type="application/json", response_schema=req["schema"], **kw)
    else:
        cfg = types.GenerateContentConfig(system_instruction=req["system"], temperature=req["temperature"],
                                          max_output_tokens=req["max_tokens"], **kw)
    contents = req["prompt"]
    if req["images"]:
        contents = [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in req["images"]] + [req["prompt"]]
    resp = _client.models.generate_content(model=model, contents=contents, config=cfg)
    um = getattr(resp, "usage_metadata", None)
    try:
        finish = str(resp.candidates[0].finish_reason)
    except Exception:
        finish = "?"
    return resp.text or "", (getattr(um, "prompt_token_count", 0), getattr(um, "candidates_token_count", 0)), finish


def _openai(provider: str, name: str, req: dict):
    P = re.sub(r"\W", "_", provider).upper()
    url, key = os.getenv(f"PROVIDER_{P}_URL"), os.getenv(f"PROVIDER_{P}_KEY")
    if not (url and key):
        raise Skip(f"PROVIDER_{P}_URL / PROVIDER_{P}_KEY are not set")
    if req["images"] or req["grounded"]:
        raise Skip("images and grounding are only supported on Gemini models")
    system = req["system"] or ""
    if req["schema"] is not None:
        system += ("\n\nReturn ONLY one JSON object (no prose, no markdown fences) that matches this JSON schema:\n"
                   + json.dumps(req["schema"].model_json_schema()))
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": req["prompt"]}]
    body = {"model": name, "messages": msgs, "temperature": req["temperature"],
            "max_tokens": min(req["max_tokens"] or 8000, int(os.getenv(f"PROVIDER_{P}_MAX_TOKENS", "8000")))}
    if req["schema"] is not None:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body,
                   timeout=float(os.getenv("LLM_TIMEOUT_MS", "180000")) / 1000)
    if r.status_code != 200:
        raise ProviderError(r.status_code, r.text[:300])
    j = r.json()
    ch = (j.get("choices") or [{}])[0]
    u = j.get("usage") or {}
    return ((ch.get("message") or {}).get("content") or "",
            (u.get("prompt_tokens", 0), u.get("completion_tokens", 0)), str(ch.get("finish_reason", "?")))


def _dispatch(spec: str, req: dict):
    provider, name = _split(spec)
    return _gemini(name, req) if provider == "gemini" else _openai(provider, name, req)


# ───────────── failover ─────────────
def _try_model(spec: str, req: dict, task: str):
    """One model, at most two quick tries. Returns (text, None) or (None, error). Never sleeps long: failing over is cheaper."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            text, (tin, tout), finish = _dispatch(spec, req)
            _log(spec, task, tin, tout, True)
            LAST.update(model=spec, finish=finish)
            return text, None
        except Skip as e:
            _bad[spec] = time.time() + 3600
            print(f"[llm] {spec}: skipped ({e})")
            return None, e
        except Exception as e:
            _log(spec, task, 0, 0, False)
            kind = _classify(e)
            if kind == "quota":
                _cool[spec] = time.time() + 60
                print(f"[llm] {spec}: 429, trying the next model")
                return None, BudgetExceeded(f"{spec}: provider returned 429")
            if kind == "fatal":
                _bad[spec] = time.time() + 600
                print(f"[llm] {spec}: {str(e)[:140]} (skipping this model for 10 min)")
                return None, e
            last = e
            if attempt == 0:
                time.sleep(3)
    print(f"[llm] {spec}: {type(last).__name__}, switching model")
    return None, last


def _call(req: dict, task: str, validate=None):
    chain = _models_for(task)
    last: Exception | None = None
    for _ in range(4):
        soonest = float("inf")
        for spec in chain:
            blocked = max(_cool.get(spec, 0), _bad.get(spec, 0), _unhealthy_until(spec))
            if blocked > time.time():
                soonest = min(soonest, blocked)
                continue
            used, limit = _used_today(spec), _daily_limit(spec)
            if used >= limit - SAFETY_MARGIN:
                last = BudgetExceeded(f"{spec}: {used}/{limit} used today")
                continue
            recent, rpm = _recent(spec), _rpm_limit(spec)
            if len(recent) >= rpm:                                  # per-minute budget used: skip instead of wasting a 429
                soonest = min(soonest, recent[-rpm] + 61)
                continue
            out, err = _try_model(spec, req, task)
            if out is not None:
                if validate is None:
                    return out
                try:
                    return validate(out)
                except Exception as e:
                    print(f"[llm] {spec} returned unusable output ({type(e).__name__}); trying the next model")
                    last = e
                    continue
            last = err or last
            blocked = max(_cool.get(spec, 0), _bad.get(spec, 0), _unhealthy_until(spec))
            if blocked > time.time():
                soonest = min(soonest, blocked)
        if soonest == float("inf"):
            break
        wait = min(max(soonest - time.time(), 1), 65)
        print(f"[llm] every model is busy or cooling down; waiting {wait:.0f}s")
        time.sleep(wait)
    raise last or BudgetExceeded("no model available for task " + task)


# ───────────── public API ─────────────
def _req(prompt, system, temperature, max_tokens, schema, images, grounded) -> dict:
    return dict(prompt=prompt, system=system, temperature=temperature, max_tokens=max_tokens,
                schema=schema, images=images, grounded=grounded)


def generate_structured(prompt: str, schema, system: str | None = None, temperature: float = 0.8,
                        task: str = "script", images: list[bytes] | None = None):
    return _call(_req(prompt, system, temperature, None, schema, images, False), task,
                 validate=lambda t: schema.model_validate_json(_extract_json(t)))


def generate_text(prompt: str, system: str | None = None, temperature: float = 0.6, max_output_tokens: int = 32000,
                  task: str = "storyboard", grounded: bool = False) -> str:
    return _call(_req(prompt, system, temperature, max_output_tokens, None, None, grounded), task) or ""


def ping(spec: str) -> tuple[bool, str]:
    """One tiny request straight to a model (used by `doctor --ping`). Not counted in the usage log."""
    try:
        text, _, _ = _dispatch(spec, _req("Reply with the single word OK.", None, 0.0, 20, None, None, False))
        return True, text.strip()[:40] or "(empty reply)"
    except Skip as e:
        return False, f"not configured: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:140]}"


def usage_report() -> None:
    with _con() as con:
        rows = con.execute("SELECT model, SUM(ok), SUM(in_tokens), SUM(out_tokens), SUM(1-ok) "
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
            _log(a[1], "seed", 0, 0, True)
        usage_report()
    else:
        print("usage: python -m shorts_agent.llm usage | seed <model> <n>")
