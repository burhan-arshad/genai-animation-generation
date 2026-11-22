"""Schemas + deterministic validation for script.json (style-aware)."""
from __future__ import annotations

import re

from pydantic import BaseModel

from .styles import Style, active


class Line(BaseModel):
    text: str
    caps: str = ""


class ScriptDraft(BaseModel):
    title: str
    sources: list[str]
    lines: list[Line]


def to_script_json(draft: ScriptDraft, style: Style | None = None, music: str | None = None) -> dict:
    st = style or active()
    lines = [l.model_dump() if st.caps_mode == "chunks" else {"text": l.text} for l in draft.lines]
    return {"title": draft.title, "voice": st.voice, "speed": st.speed, "lead": st.lead,
            "outro": st.outro, "gap": st.gap, "music": music or st.music,
            "sources": draft.sources, "lines": lines}


def check_script(d: ScriptDraft, st: Style | None = None) -> list[str]:
    """Human-readable problems; empty list = valid."""
    st = st or active()
    problems: list[str] = []
    if not st.min_lines <= len(d.lines) <= st.max_lines:
        problems.append(f"Need {st.min_lines}-{st.max_lines} lines, got {len(d.lines)}.")
    words = sum(len(l.text.split()) for l in d.lines)
    if not st.min_words <= words <= st.max_words:
        problems.append(f"Narration has {words} words; target is {st.min_words}-{st.max_words}.")
    if len(d.sources) < 2:
        problems.append("Need at least 2 sources.")
    for i, l in enumerate(d.lines):
        if re.search(r"\d", l.text):
            problems.append(f"Line {i}: write numbers as spoken words in 'text' (no digits).")
        if st.caps_mode != "chunks":
            continue
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


# ───────────── numbers: the narration is spoken, so digits become words in code (the LLM keeps forgetting) ─────────────
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_UNITS_AFTER = re.compile(r"\s*(?:feet|foot|ft|inch|inches|miles?|pounds?|lbs|tons?|people|men|women|years?|days?|hours?|dollars?|cents?|percent|times|degrees|miles|kilometers?|meters?|acres?)\b", re.I)


def _below_100(n: int) -> str:
    return _ONES[n] if n < 20 else _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")


def cardinal(n: int) -> str:
    if n < 100:
        return _below_100(n)
    if n < 1000:
        return _ONES[n // 100] + " hundred" + (" " + _below_100(n % 100) if n % 100 else "")
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= size:
            rest = n % size
            return cardinal(n // size) + " " + name + (" " + cardinal(rest) if rest else "")
    return str(n)


def _year(n: int) -> str:
    if 2000 <= n <= 2009:
        return "two thousand" + (" " + _ONES[n - 2000] if n > 2000 else "")
    if n < 1100 or n % 100 == 0 and n % 1000 == 0:
        return cardinal(n)
    hi, lo = n // 100, n % 100
    if lo == 0:
        return cardinal(hi) + " hundred"
    return cardinal(hi) + " " + ("oh " + _ONES[lo] if lo < 10 else _below_100(lo))


def _ordinal(words: str) -> str:
    head, sep, last = words.rpartition(" ")
    parts = last.rsplit("-", 1)
    w = parts[-1]
    irregular = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
    w = irregular.get(w) or (w[:-1] + "ieth" if w.endswith("y") else w + "th")
    return (head + sep if head else "") + ("-".join(parts[:-1] + [w]) if len(parts) > 1 else w)


def _digits(s: str) -> str:
    return " ".join(_ONES[int(c)] for c in s if c.isdigit())


_NUM = re.compile(r"(\$)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(st|nd|rd|th|s|%)?(?![\d])")


def speak_numbers(text: str) -> str:
    """'In 1869, 10 men paid $25 for the 3rd show' -> 'In eighteen sixty-nine, ten men paid twenty-five dollars for the third show'."""
    def one(m: re.Match) -> str:
        dollar, whole, frac, suf = m.group(1), m.group(2), m.group(3), m.group(4)
        n = int(whole.replace(",", ""))
        after = text[m.end():m.end() + 20]
        if suf in ("st", "nd", "rd", "th") and not frac:
            return _ordinal(cardinal(n))
        if suf == "s" and not frac and 1100 <= n <= 2090 and n % 10 == 0 and "," not in whole:
            w = _year(n)
            return (w[:-1] + "ies" if w.endswith("y") else w + "s")
        if suf == "%":
            return (cardinal(n) + (" point " + _digits(frac) if frac else "")) + " percent"
        if dollar:
            out = cardinal(n) + (" dollar" if n == 1 else " dollars")
            if frac and int(frac[:2].ljust(2, "0")):
                out += " and " + cardinal(int(frac[:2].ljust(2, "0"))) + " cents"
            return out
        if frac:
            return cardinal(n) + " point " + _digits(frac)
        if 1000 <= n <= 2099 and "," not in whole and not _UNITS_AFTER.match(after):
            return _year(n) + ("" if suf != "s" else "s")
        return cardinal(n) + ("s" if suf == "s" else "")
    return _NUM.sub(one, text)


def repair_numbers(d: ScriptDraft) -> ScriptDraft:
    """Spoken text must not contain digits: fix it in code instead of burning LLM retries."""
    for l in d.lines:
        l.text = speak_numbers(l.text)
    return d
