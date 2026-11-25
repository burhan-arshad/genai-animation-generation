"""Quick model test.   python -m shorts_agent.bench [task ...] [--big TOKENS]
Without --big: one small structured task on every model that appears in the chains (does it answer valid JSON?).
With --big N : about N tokens of input and the size guards switched off: shows which models REALLY accept a big request
               (the script, judge and storyboard prompts are 6-12K tokens)."""
from __future__ import annotations

import os
import sys
import time

from pydantic import BaseModel

from . import llm

TASKS = ["research", "topics", "factcheck", "voice", "judge", "script", "storyboard"]
TEXT = ("The Great Molasses Flood happened in Boston in January 1919. A storage tank burst and a wave of molasses "
        "about 25 feet high killed 21 people.")
SYSTEM = "Extract 3 checkable factual claims from the TEXT TO ANALYSE. Return JSON only."
NOTE = ("Background note {i}: the flood happened in the North End of Boston on a warm January afternoon, and the molasses "
        "moved through the streets faster than people could run.\n")


class Claim(BaseModel):
    claim: str
    queries: list[str]


class Claims(BaseModel):
    claims: list[Claim]


def main() -> None:
    if "--free" in sys.argv[1:]:                              # list the free OpenRouter models (no key needed)
        import httpx
        data = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json().get("data", [])
        free = [m for m in data if str(m.get("id", "")).endswith(":free") or str((m.get("pricing") or {}).get("prompt")) in ("0", "0.0")]
        free.sort(key=lambda m: -(m.get("context_length") or 0))
        for m in free[:40]:
            sp = m.get("supported_parameters") or []
            print(f"{m['id']:<62} ctx {m.get('context_length')}  json {'yes' if ('response_format' in sp or 'structured_outputs' in sp) else 'no'}")
        return
    a = sys.argv[1:]
    big = 0
    if "--big" in a:
        i = a.index("--big")
        big = int(a[i + 1])
        del a[i:i + 2]
    if big:                                                   # test the provider's real limit, not our own guard
        for k in [k for k in os.environ if k.startswith("PROVIDER_") and k.endswith("_MAX_INPUT_TOKENS")]:
            os.environ.pop(k)
    specs: dict[str, list[str]] = {}
    for t in (a or TASKS):
        try:
            for s in llm._models_for(t):
                specs.setdefault(s, []).append(t)
        except RuntimeError as e:
            print(f"[{t}] {e}")
    pad = "".join(NOTE.format(i=i) for i in range(int(big * 3.2) // len(NOTE))) if big else ""
    prompt = (pad + "\nTEXT TO ANALYSE:\n" if big else "") + TEXT
    print(f"{'BIG request, about ' + str(big) + ' tokens in' if big else 'small request'}: {len(specs)} model(s)\n")
    for spec, used in specs.items():
        t0 = time.time()
        try:
            text, (i, o), _ = llm._dispatch(spec, llm._req(prompt, SYSTEM, 0.0, 2500 if big else 800, Claims, None, False))
            n = len(Claims.model_validate_json(llm._extract_json(text)).claims)
            print(f"  OK   {spec:<42} {time.time() - t0:5.1f}s  {n} claims  tokens {i}/{o}   (used by: {', '.join(used)})")
        except Exception as e:
            print(f"  FAIL {spec:<42} {type(e).__name__}: {str(e)[:150]}")


if __name__ == "__main__":
    main()