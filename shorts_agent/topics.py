"""Topic agent: proposes safe, well-documented US/Europe history topics; code filters duplicates, risky themes and thin evidence."""
from __future__ import annotations

import argparse
import os
import re

from pydantic import BaseModel

from . import store
from .llm import generate_structured
from .retrieval import wikipedia_facts

BLOCK = re.compile(
    r"genocide|massacre|holocaust|terror|suicide|\brape|torture|execut|assassinat|slave|nazi|\bisis\b|9/11|covid|pandemic|"
    r"vaccin|election|president|prime minister|trump|biden|religio|crusade|abortion|\bdrug|cocaine|opium|\bsex\b|murder|"
    r"serial killer|\bbomb|war crime|concentration camp|\bcult\b|\bplague|epidemic|cholera|disease|cancer|saccharin|sweeten|medic|health|\bdiet|poison|toxic|nutrition", re.I)
STOP = set("the a an of in on at to for and or with from by is was were that this its their how why what when who".split())
FORMATS = ["a strange accident or disaster with a surprising cause (non-graphic)",
           "an unexpected invention or discovery",
           "a clever loophole, law or ban that backfired",
           "an engineering or construction feat",
           "a famous myth versus what really happened",
           "an odd tradition, record or coincidence"]

SYSTEM = """You propose topics for 40-second history Shorts for viewers in the United States and Europe.
Each topic is ONE specific, well-documented event, place or invention that has its own Wikipedia article, told as a surprising true story
(cause and effect, not a list of facts). Rules:
- Year between 1500 and 1990; region is exactly 'United States' or 'Europe'.
- Nothing graphic, political, religious, medical, criminal, about war atrocities or about living people. No contested claims.
- `topic` is a plain noun phrase with the year, e.g. 'The Great Molasses Flood of 1919'.
- Be varied: different centuries, countries and kinds of events. Never repeat or closely resemble a topic that was already used."""


class Idea(BaseModel):
    topic: str
    year: int
    region: str
    angle: str


class IdeaList(BaseModel):
    ideas: list[Idea]


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def _reject(i: Idea, used_tok: list[set[str]]) -> str | None:
    if not 1500 <= i.year <= 1990:
        return "year out of range"
    if i.region.strip() not in ("United States", "Europe"):
        return "region"
    if BLOCK.search(i.topic + " " + i.angle):
        return "blocked theme"
    a = _tokens(i.topic)
    if any(a and len(a & b) / len(a | b) >= 0.6 for b in used_tok):
        return "duplicate"
    if len(wikipedia_facts(i.topic)) < 4:
        return "thin evidence"
    return None


def suggest(n: int = 3) -> list[Idea]:
    used = [r[0] for r in store.db().execute("SELECT topic FROM jobs")]
    fmt = FORMATS[len(used) % len(FORMATS)]
    prompt = ("Topics already used (do not repeat):\n" + ("\n".join(f"- {t}" for t in used[-60:]) or "(none yet)")
              + f"\n\nPreferred kind of story this time: {fmt}.\nPropose 12 topics.")
    ideas = generate_structured(prompt, IdeaList, system=SYSTEM, temperature=0.9, task="topics").ideas
    used_tok, ok = [_tokens(t) for t in used], []
    for i in ideas:
        why = _reject(i, used_tok)
        print(f"[topics] {'skip' if why else 'ok  '} {i.topic} ({i.year}, {i.region})" + (f" - {why}" if why else ""))
        if not why:
            ok.append(i)
            used_tok.append(_tokens(i.topic))
        if len(ok) >= n:
            break
    return ok


def enqueue(n: int = 3, style: str | None = None) -> list[int]:
    style = style or os.getenv("STYLE", "history")
    ids = [store.add_job(i.topic, style) for i in suggest(n)]
    print("[topics] queued jobs:", ids or "none (no valid topic found)")
    return ids


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--dry", action="store_true", help="only print, do not queue")
    a = ap.parse_args()
    suggest(a.n) if a.dry else enqueue(a.n)