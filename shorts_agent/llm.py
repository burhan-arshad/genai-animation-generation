"""LLM layer: provider-agnostic model chains (Gemini and any OpenAI-compatible API), health-aware failover,
usage log, daily and per-minute budget guards, and a memory of every quota that ran out (usage.db), with the time it comes back.

A model is written as `gemini-3.5-flash-lite` (Gemini) or `provider:model` (any OpenAI-compatible API, e.g.
`groq:openai/gpt-oss-120b`; configure PROVIDER_<NAME>_URL and PROVIDER_<NAME>_KEY in .env).
A chain is a comma-separated list tried in order, e.g. GEMINI_MODEL_SCRIPT=a,b,groq:c .
Optional per provider: PROVIDER_<NAME>_MAX_TOKENS, _MAX_INPUT_TOKENS (a bigger request goes to the next model), _JSON_MODE=0,
_EXTRA='{"json":"fields"}' (or per model: '{"model-name":{"json":"fields"}}'), _RESET_TZ (the time zone whose midnight resets the daily limits).
Daily limits: DAILY_LIMITS (calls) and DAILY_TOKENS (tokens), both as model:number,...
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()
DB = Path(__file__).resolve().parent.parent / "usage.db"
SAFETY_MARGIN = 2
LAST: dict = {}                      # model spec and finish reason of the latest successful call
ALL_TASKS = ["research", "topics", "factcheck", "judge", "voice", "hook", "script", "storyboard", "storyboard_hard"]
_client = None
_cool: dict[str, float] = {}         # spec -> skip until (short rests, this process only)
_bad: dict[str, float] = {}          # spec -> skip until (not configured, or a fatal error such as a bad key or unknown model)
_warned: set[str] = set()            # things already reported in this process


class BudgetExceeded(RuntimeError):
    """Quota hit on every model in the chain: pause and resume later."""


class ProviderError(RuntimeError):
    def __init__(self, code: int, msg: str, retry_after: float = 0):
        super().__init__(f"HTTP {code}: {msg}")
        self.code = code
        self.retry_after = retry_after


class Skip(Exception):
    """This model cannot serve the request (not configured / unsupported): move on."""


class TooBig(Exception):
    """The request is larger than this provider's free limit: use another model for this call (the model itself is fine)."""


# ───────────── usage log, blocks and provider headers (usage.db) ─────────────
def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
        id INTEGER PRIMARY KEY, day TEXT, ts REAL, model TEXT, task TEXT,
        in_tokens INTEGER, out_tokens INTEGER, ok INTEGER)""")
    con.execute("CREATE TABLE IF NOT EXISTS llm_blocks(spec TEXT PRIMARY KEY, until REAL, kind TEXT, note TEXT, ts REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS llm_limits(spec TEXT PRIMARY KEY, rem_req INTEGER, limit_req INTEGER, rem_tok INTEGER, "
                "limit_tok INTEGER, reset_req TEXT, reset_tok TEXT, ts REAL)")
    return con


def _prov(spec: str) -> str:
    return _split(spec)[0]


def _reset_tz(spec: str) -> ZoneInfo:
    """Gemini's quota day ends at midnight Pacific time; Groq and most others use midnight UTC."""
    P = re.sub(r"\W", "_", _prov(spec)).upper()
    name = os.getenv(f"PROVIDER_{P}_RESET_TZ") or ("America/Los_Angeles" if _prov(spec) == "gemini" else "UTC")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _today(spec: str | None = None) -> str:
    return datetime.now(_reset_tz(spec) if spec else ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def _next_reset(spec: str) -> float:
    now = datetime.now(_reset_tz(spec))
    return (now + timedelta(days=1)).replace(hour=0, minute=2, second=0, microsecond=0).timestamp()


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %H:%M")             # this computer's time


def _log(spec: str, task: str, tin: int, tout: int, ok: bool) -> None:
    with _con() as con:
        con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) VALUES(?,?,?,?,?,?,?)",
                    (_today(spec), time.time(), spec, task, tin or 0, tout or 0, int(ok)))


def _used_today(spec: str) -> int:
    with _con() as con:
        return con.execute("SELECT COUNT(*) FROM llm_calls WHERE day=? AND model=? AND ok=1", (_today(spec), spec)).fetchone()[0]


def _tokens_today(spec: str) -> int:
    with _con() as con:
        return int(con.execute("SELECT COALESCE(SUM(in_tokens + out_tokens), 0) FROM llm_calls WHERE day=? AND model=?", (_today(spec), spec)).fetchone()[0])


def tokens_between(t0: float, t1: float) -> int:
    """Tokens (in + out, every call) logged between two moments: used to cap what one video may cost."""
    with _con() as con:
        r = con.execute("SELECT COALESCE(SUM(in_tokens + out_tokens), 0) FROM llm_calls WHERE ts BETWEEN ? AND ?", (t0, t1)).fetchone()
    return int(r[0] or 0)


def _recent(spec: str) -> list[float]:
    with _con() as con:
        return [r[0] for r in con.execute("SELECT ts FROM llm_calls WHERE model=? AND ts>? ORDER BY ts",
                                          (spec, time.time() - 60))]


def _block(spec: str, until: float, kind: str, note: str = "") -> None:
    """Remember (across runs) that a model is out of quota until `until`."""
    with _con() as con:
        con.execute("INSERT OR REPLACE INTO llm_blocks(spec, until, kind, note, ts) VALUES(?,?,?,?,?)", (spec, until, kind, note[:300], time.time()))


def _blocked_until(spec: str) -> float:
    with _con() as con:
        r = con.execute("SELECT until FROM llm_blocks WHERE spec=?", (spec,)).fetchone()
    return float(r[0]) if r and float(r[0]) > time.time() else 0.0


def clear_blocks() -> None:
    with _con() as con:
        con.execute("DELETE FROM llm_blocks")
    _cool.clear()
    _bad.clear()
    _warned.clear()


def clear_counters() -> None:
    """Forget the calls of the last 36 hours (for when this program counts more than the provider does)."""
    with _con() as con:
        con.execute("DELETE FROM llm_calls WHERE ts > ?", (time.time() - 36 * 3600,))
    _warned.clear()


def _note_limits(spec: str, h) -> None:
    """Groq tells the truth in its response headers: requests left today (RPD) and tokens left this minute (TPM)."""
    g = h.get
    if not (g("x-ratelimit-remaining-requests") or g("x-ratelimit-remaining-tokens")):
        return
    toi = lambda v: int(float(v)) if v not in (None, "") and re.fullmatch(r"\d+(\.\d+)?", str(v)) else None
    try:
        with _con() as con:
            con.execute("INSERT OR REPLACE INTO llm_limits(spec, rem_req, limit_req, rem_tok, limit_tok, reset_req, reset_tok, ts) VALUES(?,?,?,?,?,?,?,?)",
                        (spec, toi(g("x-ratelimit-remaining-requests")), toi(g("x-ratelimit-limit-requests")), toi(g("x-ratelimit-remaining-tokens")),
                         toi(g("x-ratelimit-limit-tokens")), g("x-ratelimit-reset-requests"), g("x-ratelimit-reset-tokens"), time.time()))
    except Exception:
        pass


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


def _token_limit(spec: str) -> int:
    """Tokens a model may use per day (DAILY_TOKENS=model:number,...); 0 = not tracked."""
    return _env_limit("DAILY_TOKENS", spec, 0)


def _rpm_limit(spec: str) -> int:
    return _env_limit("RPM_LIMITS", spec, int(os.getenv("DEFAULT_RPM_LIMIT", "5")))


def _unhealthy_until(spec: str) -> float:
    """Circuit breaker derived from the log: the last two calls failed -> skip the model for BREAKER seconds after the last failure.
    Rate limits (429) do not count: they only mean 'wait a little', not 'the model is broken'.
    After the pause one probe call decides: success closes the breaker, another failure opens it again."""
    with _con() as con:
        rows = con.execute("SELECT ts, ok FROM llm_calls WHERE model=? AND task NOT LIKE '%:429' ORDER BY id DESC LIMIT 2", (spec,)).fetchall()
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


def _seconds(s: str) -> float:
    """'6m30s' -> 390, '2m59.56s' -> 179.56, '448ms' -> 0.448, '1h2m3s' -> 3723."""
    return sum(float(v) * {"h": 3600, "ms": 0.001, "m": 60, "s": 1}[u] for v, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", s))


def _quota_wait(spec: str, e: Exception) -> tuple[str, float]:
    """What a 429 means: ('none', 24 h) the plan has no quota for this model (limit 0) | ('day', until the reset) | ('minute', a short wait)."""
    text = str(e)
    ra = float(getattr(e, "retry_after", 0) or 0)
    m = re.search(r"(?:try again in|retryDelay['\"]?\s*:\s*['\"]?)\s*([0-9hms.]+)", text)
    hinted = _seconds(m.group(1)) if m else 0.0
    if re.search(r"limit:\s*0\b", text):
        return "none", 86400.0
    if re.search(r"PerDay|per[ _]day|\bRPD\b|\bTPD\b", text, re.I):
        if _prov(spec) == "gemini":
            return "day", max(60.0, _next_reset(spec) - time.time())
        wait = ra or hinted
        return "day", (wait + 1) if wait else max(60.0, _next_reset(spec) - time.time())
    wait = ra or hinted
    return "minute", (wait + 1) if wait else 60.0


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
    max_in = int(os.getenv(f"PROVIDER_{P}_MAX_INPUT_TOKENS", "0") or 0)       # free-tier size guard
    est = (len(system) + len(req["prompt"])) / 3.2
    if max_in and est > max_in:
        raise TooBig(f"request is about {int(est)} tokens, over PROVIDER_{P}_MAX_INPUT_TOKENS={max_in}")
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": req["prompt"]}]
    body = {"model": name, "messages": msgs, "temperature": req["temperature"],
            "max_tokens": min(req["max_tokens"] or 8000, int(os.getenv(f"PROVIDER_{P}_MAX_TOKENS", "8000")))}
    if req["schema"] is not None and os.getenv(f"PROVIDER_{P}_JSON_MODE", "1") != "0":
        body["response_format"] = {"type": "json_object"}
    extra = (os.getenv(f"PROVIDER_{P}_EXTRA") or "").strip()                    # e.g. {"reasoning_effort":"low"}, or one entry per model
    if extra:
        try:
            ex = json.loads(extra)
            per = ex.get(name)
            body.update(per if isinstance(per, dict) else {k: v for k, v in ex.items() if not isinstance(v, dict)})
        except (ValueError, AttributeError):
            raise Skip(f"PROVIDER_{P}_EXTRA is not valid JSON")
    r = httpx.post(url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body,
                   timeout=float(os.getenv("LLM_TIMEOUT_MS", "180000")) / 1000)
    _note_limits(f"{provider}:{name}", r.headers)
    if r.status_code != 200:
        try:
            wait = float(r.headers.get("retry-after", 0))
        except ValueError:
            wait = 0.0
        raise ProviderError(r.status_code, r.text[:300], wait)
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
    """One model, a few quick tries. Returns (text, None) or (None, error). Never sleeps long: failing over is cheaper."""
    last: Exception | None = None
    tries = max(1, int(os.getenv("LLM_TRIES", "2")))
    for attempt in range(tries):
        try:
            text, (tin, tout), finish = _dispatch(spec, req)
            _log(spec, task, tin, tout, True)
            LAST.update(model=spec, finish=finish)
            return text, None
        except Skip as e:
            _bad[spec] = time.time() + 3600
            print(f"[llm] {spec}: skipped ({e})")
            return None, e
        except TooBig as e:
            print(f"[llm] {spec}: {e}: using another model for this call")
            return None, e
        except Exception as e:
            if getattr(e, "code", None) == 413:           # too large for this model: not the model's fault
                print(f"[llm] {spec}: 413 request too large, trying the next model")
                return None, e
            kind = _classify(e)
            _log(spec, task + (":429" if kind == "quota" else ""), 0, 0, False)
            if kind == "quota":
                qk, wait = _quota_wait(spec, e)
                until = time.time() + wait
                _cool[spec] = until
                if qk in ("day", "none") or wait >= 300:
                    _block(spec, until, qk, str(e))               # remembered by the next runs too
                if qk == "none":
                    print(f"[llm] {spec}: limit 0, this model has no quota on your plan (skipped for 24 h)")
                elif qk == "day":
                    print(f"[llm] {spec}: daily limit reached, usable again at {_when(until)} (this computer's time)")
                else:
                    print(f"[llm] {spec}: 429, waiting {wait:.0f}s, trying the next model")
                return None, BudgetExceeded(f"{spec}: provider returned 429")
            if kind == "fatal":
                _bad[spec] = time.time() + 600
                print(f"[llm] {spec}: {str(e)[:140]} (skipping this model for 10 min)")
                return None, e
            last = e
            if attempt < tries - 1:
                time.sleep(4 * (attempt + 1))
    print(f"[llm] {spec}: {type(last).__name__}, switching model")
    return None, last


def _call(req: dict, task: str, validate=None):
    chain = _models_for(task)
    last: Exception | None = None
    est = int((len(req["system"] or "") + len(req["prompt"])) / 3.2) + min(req["max_tokens"] or 3000, 3000)
    for _ in range(max(1, int(os.getenv("LLM_ROUNDS", "4")))):
        soonest, attempted = float("inf"), False
        for spec in chain:
            now = time.time()
            blocked = max(_cool.get(spec, 0), _bad.get(spec, 0), _unhealthy_until(spec), _blocked_until(spec))
            if blocked > now:
                soonest = min(soonest, blocked)
                if blocked - now > 300 and spec not in _warned:
                    _warned.add(spec)
                    print(f"[llm] {spec}: out of quota until {_when(blocked)} (this computer's time), skipping it")
                continue
            used, limit = _used_today(spec), _daily_limit(spec)
            if used >= limit - SAFETY_MARGIN:
                if spec not in _warned:
                    _warned.add(spec)
                    print(f"[llm] {spec}: daily budget used ({used}/{limit}), resumes {_when(_next_reset(spec))}; raise it in DAILY_LIMITS if the provider allows more")
                last = BudgetExceeded(f"{spec}: {used}/{limit} used today")
                continue
            tl = _token_limit(spec)
            if tl and _tokens_today(spec) + est > tl * 0.97:
                if "t:" + spec not in _warned:
                    _warned.add("t:" + spec)
                    print(f"[llm] {spec}: daily token budget used ({_tokens_today(spec)}/{tl}), resumes {_when(_next_reset(spec))}")
                last = BudgetExceeded(f"{spec}: {_tokens_today(spec)}/{tl} tokens used today")
                continue
            recent, rpm = _recent(spec), _rpm_limit(spec)
            if len(recent) >= rpm:                                  # per-minute budget used: skip instead of wasting a 429
                soonest = min(soonest, recent[-rpm] + 61)
                continue
            attempted = True
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
            blocked = max(_cool.get(spec, 0), _bad.get(spec, 0), _unhealthy_until(spec), _blocked_until(spec))
            if blocked > time.time():
                soonest = min(soonest, blocked)
        if soonest == float("inf"):
            break
        if not attempted and soonest - time.time() > 600:           # nothing can be tried for a long time: say when, do not sleep for minutes
            last = BudgetExceeded("every model is out of quota or resting; the first one is usable again at " + _when(soonest) + " (this computer's time)")
            print("[llm] " + str(last))
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


def usage_rows() -> list[dict]:
    """Every configured model with today's use, its waiting state, its daily reset (this computer's time) and what the provider said last."""
    now = time.time()
    specs: list[str] = []
    for t in ALL_TASKS:
        try:
            specs += [s for s in _models_for(t) if s not in specs]
        except RuntimeError:
            pass
    out = []
    with _con() as con:
        for (m,) in con.execute("SELECT DISTINCT model FROM llm_calls WHERE ts > ?", (now - 3 * 86400,)).fetchall():
            if m not in specs:
                specs.append(m)
        blocks = {r[0]: r[1:] for r in con.execute("SELECT spec, until, kind, note FROM llm_blocks WHERE until > ?", (now,)).fetchall()}
        lim = {r[0]: r[1:] for r in con.execute("SELECT spec, rem_req, limit_req, rem_tok, limit_tok, ts FROM llm_limits").fetchall()}
        for s in sorted(set(specs) | set(blocks)):
            ok, bad, tin, tout = con.execute(
                "SELECT COALESCE(SUM(ok),0), COALESCE(SUM(1-ok),0), COALESCE(SUM(in_tokens),0), COALESCE(SUM(out_tokens),0) FROM llm_calls WHERE day=? AND model=?",
                (_today(s), s)).fetchone()
            b = blocks.get(s)
            prov = ""
            if s in lim:
                rr, lr, rt, lt, ts = lim[s]
                bits = []
                if rr is not None:
                    bits.append(f"{rr}" + (f"/{lr}" if lr else "") + " requests left today")
                if rt is not None:
                    bits.append(f"{rt}" + (f"/{lt}" if lt else "") + " tokens left this minute")
                prov = " · ".join(bits) + f" (at {datetime.fromtimestamp(ts):%H:%M})" if bits else ""
            out.append({"model": s, "ok": int(ok), "failed": int(bad), "in": int(tin), "out": int(tout), "limit": _daily_limit(s),
                        "tokens_today": int(tin) + int(tout), "tokens_limit": _token_limit(s),
                        "waiting_until": b[0] if b else None, "waiting_kind": b[1] if b else "", "waiting_note": (b[2] or "")[:160] if b else "",
                        "resets_at": _next_reset(s), "provider": prov})
    return out


def usage_report() -> None:
    rows = usage_rows()
    print("Daily limits reset at midnight Pacific time for Gemini and at midnight UTC for Groq. Times are this computer's time.")
    for r in rows:
        status = f"WAITING until {_when(r['waiting_until'])} ({r['waiting_kind']})" if r["waiting_until"] else "ready"
        tok = f"{r['tokens_today']}" + (f"/{r['tokens_limit']}" if r["tokens_limit"] else "")
        print(f"  {r['model']}: {r['ok']}/{r['limit']} ok calls, {tok} tokens, {r['failed']} failed | {status} | daily reset {_when(r['resets_at'])}")
        if r["provider"]:
            print(f"      provider says: {r['provider']}")
    if not rows:
        print("  no models configured")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a in (["usage"], ["limits"]):
        usage_report()
    elif a == ["clear"]:
        clear_blocks()
        print("waiting states cleared: every model will be tried again")
    elif len(a) == 3 and a[0] == "seed":
        for _ in range(int(a[2])):
            _log(a[1], "seed", 0, 0, True)
        usage_report()
    else:
        print("usage: python -m shorts_agent.llm limits | clear | seed <model> <n>")