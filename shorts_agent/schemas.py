"""Schemas + deterministic validation for script.json (style-aware)."""
from __future__ import annotations

import re

from pydantic import BaseModel

from .styles import Style, active


class Line(BaseModel):
    text: str
    caps: str


class ScriptDraft(BaseModel):
    title: str
    sources: list[str]
    lines: list[Line]


def to_script_json(draft: ScriptDraft, style: Style | None = None, music: str | None = None) -> dict:
    st = style or active()
    return {"title": draft.title, "voice": st.voice, "speed": st.speed, "lead": st.lead,
            "outro": st.outro, "gap": st.gap, "music": music or st.music,
            "sources": draft.sources, "lines": [l.model_dump() for l in draft.lines]}


def check_script(d: ScriptDraft, st: Style | None = None) -> list[str]:
    """Human-readable problems; empty list = valid."""
    st = st or active()
    problems: list[str] = []
    if not 8 <= len(d.lines) <= 14:
        problems.append(f"Need 8-14 lines, got {len(d.lines)}.")
    words = sum(len(l.text.split()) for l in d.lines)
    if not st.min_words <= words <= st.max_words:
        problems.append(f"Narration has {words} words; target is {st.min_words}-{st.max_words}.")
    if len(d.sources) < 2:
        problems.append("Need at least 2 sources.")
    for i, l in enumerate(d.lines):
        if re.search(r"\d", l.text):
            problems.append(f"Line {i}: write numbers as spoken words in 'text' (digits only in caps).")
        chunks = [c.strip() for c in l.caps.split("|") if c.strip()]
        if not chunks:
            problems.append(f"Line {i}: caps is empty.")
        for c in chunks:
            toks = c.split()
            if not 1 <= len(toks) <= st.caps_max_words:
                problems.append(f"Line {i}: caption chunk '{c}' must be 1-{st.caps_max_words} words.")
            if sum(1 for t in toks if t.startswith("*")) != 1:
                problems.append(f"Line {i}: chunk '{c}' must have exactly one *highlighted word.")
    return problems


def _fix_chunk(c: str, max_words: int) -> list[str]:
    toks = c.split()
    if not toks:
        return []
    plain = [t.lstrip("*") for t in toks]
    star_at = next((i for i, t in enumerate(toks) if t.startswith("*")), None)
    out = []
    for g in range(0, len(plain), max_words):
        group = plain[g:g + max_words]
        if star_at is not None and g <= star_at < g + max_words:
            k = star_at - g
        else:
            k = max(range(len(group)), key=lambda i: len(group[i].strip("?!.,")))
        group[k] = "*" + group[k]
        out.append(" ".join(group))
    return out


def repair_caps(d: ScriptDraft, max_words: int | None = None) -> ScriptDraft:
    """Fix mechanical caption problems in code instead of burning LLM retries."""
    mw = max_words or active().caps_max_words
    for l in d.lines:
        l.caps = " | ".join(x for c in l.caps.split("|") for x in _fix_chunk(c.strip(), mw))
    return d