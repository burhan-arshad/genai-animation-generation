"""Schemas + deterministic validation for script.json."""
from __future__ import annotations

import re
from pydantic import BaseModel


class Line(BaseModel):
    text: str   # what the voice says
    caps: str   # caption chunks: "WHAT *HAPPENS | IF YOU *SWALLOW"


class ScriptDraft(BaseModel):
    """Only the fields the LLM is allowed to write."""
    title: str
    sources: list[str]
    lines: list[Line]


FIXED_FIELDS = {
    "voice": "am_michael", "speed": 1.0, "lead": 0.4,
    "outro": 0.9, "gap": 0.28, "music": "bed",
}


def to_script_json(draft: ScriptDraft) -> dict:
    return {
        "title": draft.title,
        **FIXED_FIELDS,
        "sources": draft.sources,
        "lines": [l.model_dump() for l in draft.lines],
    }


def check_script(d: ScriptDraft, min_words: int = 85, max_words: int = 115) -> list[str]:
    """Return a list of human-readable problems. Empty list = valid."""
    problems: list[str] = []

    if not 8 <= len(d.lines) <= 14:
        problems.append(f"Need 8-14 lines, got {len(d.lines)}.")

    words = sum(len(l.text.split()) for l in d.lines)
    if not min_words <= words <= max_words:
        problems.append(f"Narration has {words} words; target is {min_words}-{max_words}.")

    if len(d.sources) < 2:
        problems.append("Need at least 2 real, specific sources.")

    for i, l in enumerate(d.lines):
        if re.search(r"\d", l.text):
            problems.append(f"Line {i}: write numbers as words in 'text' (e.g. 'seven').")
        chunks = [c.strip() for c in l.caps.split("|") if c.strip()]
        if not chunks:
            problems.append(f"Line {i}: caps is empty.")
        for c in chunks:
            toks = c.split()
            if not 1 <= len(toks) <= 3:
                problems.append(f"Line {i}: caption chunk '{c}' must be 1-3 words.")
            stars = sum(1 for t in toks if t.startswith("*"))
            if stars != 1:
                problems.append(f"Line {i}: chunk '{c}' must have exactly one *highlighted word.")
    return problems


def _fix_chunk(c: str) -> list[str]:
    """Make one caption chunk valid: <=3 words, exactly one *highlighted word per piece."""
    toks = c.split()
    if not toks:
        return []
    plain = [t.lstrip("*") for t in toks]
    star_at = next((i for i, t in enumerate(toks) if t.startswith("*")), None)
    out = []
    for g in range(0, len(plain), 3):
        group = plain[g:g + 3]
        if star_at is not None and g <= star_at < g + 3:
            k = star_at - g
        else:  # no star here: highlight the longest word
            k = max(range(len(group)), key=lambda i: len(group[i].strip("?!.,")))
        group[k] = "*" + group[k]
        out.append(" ".join(group))
    return out


def repair_caps(d: ScriptDraft) -> ScriptDraft:
    """Fix mechanical caption problems in code instead of burning LLM retries."""
    for l in d.lines:
        l.caps = " | ".join(x for c in l.caps.split("|") for x in _fix_chunk(c.strip()))
    return d