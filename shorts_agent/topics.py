"""Topic agent: proposes safe, well-documented topics for the active niche. Code filters duplicates, risky themes and thin evidence."""
from __future__ import annotations

import argparse
import re

from pydantic import BaseModel

from . import niche, store, styles
from .llm import generate_structured
from .retrieval import wikipedia_facts

# Baseline that no niche file can weaken
GLOBAL_BLOCK = re.compile(r"genocide|massacre|holocaust|terror|suicide|\brape|torture|child abuse|sexual", re.I)
STOP = set("the a an of in on at to for and or with from by is was were that this its their how why what when who".split())


class Idea(BaseModel):
    topic: str
    year: int
    region: str
    angle: str


class IdeaList(BaseModel):
    ideas: list[Idea]


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def reject_reason(i: Idea, cfg: dict, block: re.Pattern, used_tok: list[set[str]]) -> str | None:
    lo, hi = cfg.get("year_min"), cfg.get("year_max")
    if lo is not None and hi is not None and not lo <= i.year <= hi:
        return "year out of range"
    regions = cfg.get("regions")
    if regions and i.region.strip() not in regions:
        return "region"
    text = i.topic + " " + i.angle
    if GLOBAL_BLOCK.search(text) or block.search(text):
        return "blocked theme"
    a = _tokens(i.topic)
    if any(a and len(a & b) / len(a | b) >= 0.6 for b in used_tok):
        return "duplicate"
    if len(wikipedia_facts(i.topic)) < int(cfg.get("min_evidence", 4)):
        return "thin evidence"
    return None


def suggest(n: int = 3, key: str | None = None) -> list[Idea]:
    key = key or styles.default_key()
    cfg = niche.load(key)["topics"]
    block = re.compile(cfg["block_regex"], re.I)
    used = [r[0] for r in store.db().execute("SELECT topic FROM jobs")]
    formats = cfg.get("formats") or ["a surprising true story"]
    prompt = ("Topics already used (do not repeat):\n" + ("\n".join(f"- {t}" for t in used[-60:]) or "(none yet)")
              + f"\n\nPreferred kind of story this time: {formats[len(used) % len(formats)]}.\nPropose 12 topics.")
    ideas = generate_structured(prompt, IdeaList, system=cfg["system"], temperature=0.9, task="topics").ideas
    used_tok, ok = [_tokens(t) for t in used], []
    for i in ideas:
        why = reject_reason(i, cfg, block, used_tok)
        print(f"[topics] {'skip' if why else 'ok  '} {i.topic} ({i.year}, {i.region})" + (f" - {why}" if why else ""))
        if not why:
            ok.append(i)
            used_tok.append(_tokens(i.topic))
        if len(ok) >= n:
            break
    return ok


def enqueue(n: int = 3, key: str | None = None) -> list[int]:
    key = key or styles.default_key()
    ids = [store.add_job(i.topic, key) for i in suggest(n, key)]
    print("[topics] queued jobs:", ids or "none (no valid topic found)")
    return ids


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--niche", default=None)
    ap.add_argument("--dry", action="store_true", help="only print, do not queue")
    a = ap.parse_args()
    suggest(a.n, a.niche) if a.dry else enqueue(a.n, a.niche)
