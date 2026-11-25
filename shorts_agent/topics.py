"""Topic agent: picks documented cases (a curated list, Wikipedia searches or 'On this day') and code checks that they can be researched and fact-checked."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import random
import re

from pydantic import BaseModel

from . import niche, store, styles
from .llm import generate_structured
from .retrieval import _http, web_evidence, wikipedia_facts
from .topicgate import evidence_ok

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
    items = wikipedia_facts(i.topic)
    if len(items) < int(cfg.get("min_evidence", 4)):
        return "thin evidence"
    if not evidence_ok(i.topic, items)[0]:
        return "wikipedia does not match"
    dense = sum(1 for e in items if len(re.findall(r"\d", e["text"])) >= 4)      # paragraphs with numbers or dates: what the fact-check can verify
    if dense < int(os.getenv("TOPIC_MIN_FACTS", "3")):
        return "too few checkable facts"
    if os.getenv("TAVILY_API_KEY") and os.getenv("TOPIC_WEB_PROBE", "1") != "0" and not web_evidence(i.topic, n=2):
        return "no second reliable source"
    return None


def feed_candidates(cfg: dict, days: int = 3) -> list[dict]:
    """Real events from Wikipedia's 'On this day' pages for today +- `days` (no key needed). [] when the feed is unreachable."""
    out, seen = [], set()
    lo, hi = cfg.get("year_min"), cfg.get("year_max")
    today = dt.date.today()
    for k in range(-days, days + 1):
        d = today + dt.timedelta(days=k)
        try:
            r = _http.get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{d.month:02d}/{d.day:02d}")
            events = r.json().get("events", []) if r.status_code == 200 else []
        except Exception:
            continue
        for ev in events:
            year, text = ev.get("year"), re.sub(r"\s+", " ", str(ev.get("text", ""))).strip()
            if not isinstance(year, int) or len(text) < 30 or text in seen:
                continue
            if lo is not None and hi is not None and not lo <= year <= hi:
                continue
            seen.add(text)
            out.append({"year": year, "text": text[:170]})
    return out


def search_candidates(cfg: dict, k: int = 5) -> list[dict]:
    """Real Wikipedia articles found by searching for the niche's themes (cfg 'search_queries'). [] when offline."""
    qs = list(cfg.get("search_queries") or [])
    random.shuffle(qs)
    out, seen = [], set()
    for q in qs[:k]:
        try:
            r = _http.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "list": "search", "srsearch": q, "srlimit": 10, "sroffset": random.choice([0, 0, 10, 20]),
                "srnamespace": 0, "format": "json"})
            hits = r.json()["query"]["search"] if r.status_code == 200 else []
        except Exception:
            continue
        for h in hits:
            t = str(h.get("title", ""))
            if not t or t in seen or t.lower().startswith(("list of", "timeline", "lists of")):
                continue
            seen.add(t)
            out.append({"title": t, "text": html.unescape(re.sub(r"<[^>]+>", "", str(h.get("snippet", ""))))[:140]})
    return out


def seed_candidates(cfg: dict, used_tok: list[set[str]], k: int = 24) -> list[dict]:
    """The niche's curated cases ('Name|year|region') that were not made yet."""
    out = []
    for s in cfg.get("seeds") or []:
        parts = [p.strip() for p in str(s).split("|")]
        if not parts or not parts[0]:
            continue
        year = int(parts[1]) if len(parts) > 1 and re.fullmatch(r"-?\d{1,4}", parts[1]) else 0
        topic = parts[0] if (not year or str(year) in parts[0]) else f"{parts[0]} ({year})"
        a = _tokens(topic)
        if any(a and len(a & b) / len(a | b) >= 0.6 for b in used_tok):
            continue
        out.append({"topic": topic, "year": year, "region": parts[2] if len(parts) > 2 else ""})
    random.shuffle(out)
    return out[:k]


def suggest(n: int = 3, key: str | None = None) -> list[Idea]:
    key = key or styles.default_key()
    cfg = niche.load(key)["topics"]
    block = re.compile(cfg["block_regex"], re.I)
    used = [r[0] for r in store.db().execute("SELECT topic FROM jobs")]
    used_tok = [_tokens(t) for t in used]
    formats = cfg.get("formats") or ["a surprising true story"]
    prompt = ("Topics already used (do not repeat):\n" + ("\n".join(f"- {t}" for t in used[-60:]) or "(none yet)")
              + f"\n\nPreferred kind of story this time: {formats[len(used) % len(formats)]}.\nPropose 12 topics.")
    seeds = seed_candidates(cfg, used_tok)
    if seeds:
        prompt += ("\n\nCURATED CASES (well documented, safe, each has a Wikipedia article). Prefer these. For a curated case use its exact topic text, year and region:\n"
                   + "\n".join(f"- {s['topic']} [{s['year']}, {s['region']}]" for s in seeds))
    by_search = bool(cfg.get("search_queries"))
    cands = search_candidates(cfg) if by_search else feed_candidates(cfg)
    random.shuffle(cands)
    if cands and by_search:
        prompt += ("\n\nMORE REAL WIKIPEDIA ARTICLES (search results). Use one only when it is clearly a documented, non-violent mystery with a twist; skip generic pages, "
                   "people's deaths, crimes against people, politics and anything graphic. Name the case and the year it began in `topic`.\n"
                   + "\n".join(f"- {c['title']}: {c['text']}" for c in cands[:30]))
    elif cands:
        prompt += ("\n\nREAL EVENTS from Wikipedia's 'On this day' pages (around today's date). Choose ONLY from these, so every topic is a real, well documented event. "
                   "Pick the most surprising, specific and visual ones: a twist, a strange cause, a number a viewer remembers. Skip famous wars, politics and anything generic. "
                   "Write each pick as a plain `topic` that names the event AND the year, give its `year` and `region`.\n"
                   + "\n".join(f"- {c['year']}: {c['text']}" for c in cands[:50]))
    print(f"[topics] {len(seeds)} curated case(s) left, {len(cands)} real candidate(s) found")
    try:
        from . import analytics
        prompt += "\n\n" + analytics.lessons()
    except Exception:
        pass
    ideas = generate_structured(prompt, IdeaList, system=cfg["system"], temperature=0.9, task="topics").ideas
    ok = []
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