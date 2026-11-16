"""Topic gates: is the topic specific, does Wikipedia know it, and does the research evidence really match it?"""
from __future__ import annotations

import re

STOP = set("the a an of in on at to for and or with from by is was were that this its their how why what when who first last year years "
           "day days new old great famous story strange true event events thing things time people history".split())


def key_tokens(topic: str) -> list[str]:
    toks = [w for w in re.findall(r"[a-z0-9]+", str(topic).lower()) if w not in STOP and (len(w) >= 4 or (w.isdigit() and len(w) == 4))]
    return list(dict.fromkeys(toks))


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def match_score(topic: str, texts: list[str]) -> float:
    toks = key_tokens(topic)
    if not toks:
        return 1.0
    blob = " ".join(texts).lower()
    return sum(1 for t in toks if _stem(t) in blob) / len(toks)


def evidence_ok(topic: str, items: list[dict], need: float = 0.6) -> tuple[bool, float]:
    """The research pages must be about THIS topic (at least one title shares a key word, 60% of the key words appear)."""
    if not any(e.get("title") for e in items):
        return True, 1.0
    titles = [e.get("title", "") for e in items]
    s = match_score(topic, titles + [e.get("text", "")[:400] for e in items])
    return (s >= need and match_score(topic, titles) > 0), s


def script_misses(topic: str, script_text: str) -> list[str]:
    """Key words of the topic (not years) the script never mentions; [] when at least half are there."""
    toks = [t for t in key_tokens(topic) if not t.isdigit()]
    low = script_text.lower()
    miss = [t for t in toks if _stem(t) not in low]
    return miss if toks and len(miss) > len(toks) / 2 else []


def check_topic(topic: str) -> str:
    """'' = fine, otherwise the reason. Network trouble never blocks."""
    if len(key_tokens(topic)) < 2:
        return "The topic is too vague: name the specific event, place or person (and the year)."
    try:
        from .retrieval import wikipedia_facts
        items = wikipedia_facts(topic, pages=3)
    except Exception:
        return ""
    if items and not evidence_ok(topic, items)[0]:
        return "The best Wikipedia pages are about something else: use the exact name of the event."
    return ""