"""LLM wrapper: per-task model routing, usage log (SQLite), daily request budget guard."""
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


class BudgetExceeded(RuntimeError):
    pass


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


def _model_for(task: str) -> str:
    m = os.getenv(f"GEMINI_MODEL_{task.upper()}") or os.getenv("GEMINI_MODEL")
    if not m:
        raise RuntimeError("Set GEMINI_MODEL (and optionally GEMINI_MODEL_<TASK>) in .env")
    return m


def _limit_for(model: str) -> int:
    for part in os.getenv("DAILY_LIMITS", "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() == model:
                return int(v)
    return int(os.getenv("DEFAULT_DAILY_LIMIT", "20"))


def _used_today(model: str) -> int:
    with _con() as con:
        return con.execute("SELECT COUNT(*) FROM llm_calls WHERE day=? AND model=?",
                           (_today(), model)).fetchone()[0]


def _log(model: str, task: str, resp, ok: bool) -> None:
    um = getattr(resp, "usage_metadata", None)
    tin = getattr(um, "prompt_token_count", None) or 0
    tout = getattr(um, "candidates_token_count", None) or 0
    with _con() as con:
        con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) VALUES(?,?,?,?,?,?,?)",
                    (_today(), time.time(), model, task, tin, tout, int(ok)))


def _call(prompt: str, cfg, task: str, retries: int = 2):
    model = _model_for(task)
    limit = _limit_for(model)
    for attempt in range(retries):
        used = _used_today(model)
        if used >= limit - SAFETY_MARGIN:
            raise BudgetExceeded(f"{model}: {used}/{limit} requests used today. Resume after the daily reset.")
        try:
            resp = _get_client().models.generate_content(model=model, contents=prompt, config=cfg)
            _log(model, task, resp, True)
            return resp
        except Exception as e:
            _log(model, task, None, False)
            if attempt == retries - 1:
                raise
            wait = 30 * (attempt + 1)
            print(f"[llm] {model} error ({type(e).__name__}); retrying in {wait}s")
            time.sleep(wait)


def generate_structured(prompt: str, schema, system: str | None = None,
                        temperature: float = 0.8, task: str = "script"):
    cfg = types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json",
        response_schema=schema, temperature=temperature)
    return schema.model_validate_json(_call(prompt, cfg, task).text)


def generate_text(prompt: str, system: str | None = None, temperature: float = 0.6,
                  max_output_tokens: int = 16000, task: str = "storyboard") -> str:
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=temperature, max_output_tokens=max_output_tokens)
    return _call(prompt, cfg, task).text or ""


def usage_report() -> None:
    with _con() as con:
        rows = con.execute(
            "SELECT model, COUNT(*), SUM(in_tokens), SUM(out_tokens), SUM(1-ok) "
            "FROM llm_calls WHERE day=? GROUP BY model", (_today(),)).fetchall()
    print(f"Quota day (Pacific): {_today()}")
    for m, n, i, o, f in rows or []:
        print(f"  {m}: {n}/{_limit_for(m)} calls, {i or 0} in / {o or 0} out tokens, {f or 0} failed")
    if not rows:
        print("  no calls logged today")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["usage"]:
        usage_report()
    elif len(a) == 3 and a[0] == "seed":   # python -m shorts_agent.llm seed <model> <n>
        for _ in range(int(a[2])):
            with _con() as con:
                con.execute("INSERT INTO llm_calls(day, ts, model, task, in_tokens, out_tokens, ok) "
                            "VALUES(?,?,?,?,0,0,1)", (_today(), time.time(), a[1], "seed"))
        usage_report()
    else:
        print("usage: python -m shorts_agent.llm usage | seed <model> <n>")