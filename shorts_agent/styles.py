"""Per-style configuration. The engine pack ships the 'tall-tale' style; every niche pack (niches/*.json) becomes a style on top of it."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace

from . import niche


@dataclass(frozen=True)
class Style:
    key: str
    voice: str
    speed: float
    lead: float
    outro: float
    gap: float
    music: str
    music_options: tuple
    caps_max_words: int
    caps_example: str
    min_words: int
    max_words: int
    write_rules: str
    board_rules: str
    engine: str = ""
    use_brand: bool = False
    hero: bool = False
    niche: str = ""
    caps_mode: str = "chunks"       # "chunks": script carries caption chunks | "auto": the engine makes one-word captions
    min_lines: int = 8
    max_lines: int = 14
    overlay: str = ""               # folder under overlay/ copied into every project
    props_mode: str = "library"     # parked: generated niche props come in the next phase
    props_theme: str = ""
    props_required: tuple = ()
    props_note: str = ""


TALL_RULES = """- Upbeat, cheeky storyteller talking to a friend: short punchy sentences with connecting words ("See,", "So", "But").
- Each entry in `lines` is one CUT of 1.5-3 s (about 4-9 words): one picture per line. Tiny reaction beats are welcome ("Oops.").
- Structure: open on the most surprising fact (the hook), then "See, ..." rewind and explain the trick step by step, a turning point, and end on a punchline that flips the start.
- Funny but true, never mean. Nothing graphic. No invented quotes or dialogue.
- Write every year and number as spoken words in `text` ("nineteen fourteen", "seventy-three miles")."""

TALL_BOARD = """- Tall Tale look: flat cartoon cut-out people in a sunny 3D world. The camera moves in every shot; new shot every 1.5-3 s.
- Faces do the acting: mood changes on the beat (smug = clever, shock = reveal, laugh = payoff, worried = trouble).
- Open wide on the place, push in on big moments, punch in on the reveal word, end on a reaction or a punchline gag.
- The narration spells out numbers, so show years, numbers, names and signs as callouts."""

TALL_TALE = Style(
    key="tall-tale", voice="am_michael", speed=1.05, lead=0.3, outro=1.2, gap=0.18,
    music="bounce", music_options=("bounce", "bed", "tension"), caps_max_words=2, caps_example="",
    min_words=100, max_words=145, write_rules=TALL_RULES, board_rules=TALL_BOARD,
    engine="tall-tale", caps_mode="auto", min_lines=10, max_lines=24, overlay="tall-tale")

STYLES: dict[str, Style] = {"tall-tale": TALL_TALE}


def _from_niche(key: str) -> Style:
    n = niche.load(key)
    base = STYLES.get(n.get("engine", ""), TALL_TALE)        # every engine name falls back to tall-tale
    w = n["writing"]
    pr = n.get("props") or {}
    return replace(base, key=key, use_brand=True, hero=True, niche=key,
                   music_options=tuple(w.get("music_options", base.music_options)),
                   min_words=int(w.get("min_words", base.min_words)), max_words=int(w.get("max_words", base.max_words)),
                   write_rules=base.write_rules + "\n" + w["rules"],
                   board_rules=base.board_rules + n.get("storyboard", {}).get("rules", ""),
                   props_mode=pr.get("mode", "library"), props_theme=pr.get("theme", ""),
                   props_required=tuple(pr.get("required", [])), props_note=pr.get("style_note", ""))


for _name in niche.available():
    try:
        STYLES[_name] = _from_niche(_name)
    except (Exception, SystemExit) as _e:          # a broken niche file must not break the others
        print(f"[styles] niche '{_name}' skipped: {_e}")

_active: str | None = None


def default_key() -> str:
    """The niche (or raw style) used when a job does not name one: NICHE, else STYLE, else history."""
    return os.getenv("NICHE") or os.getenv("STYLE") or "history"


def set_active(key: str) -> None:
    global _active
    if key not in STYLES:
        raise ValueError(f"unknown style or niche {key!r}; choose from {list(STYLES)}")
    _active = key


def active() -> Style:
    key = _active or default_key()
    if key not in STYLES:
        raise ValueError(f"unknown style or niche {key!r}; choose from {list(STYLES)}")
    st = STYLES[key]
    if st.use_brand:
        from .brand import load
        b = load()
        v = b["voice"]
        st = replace(st, voice=v["name"], speed=float(v["speed"]), music=v.get("music", st.music),
                     write_rules=st.write_rules + "\n" + b["audience"]["writing_note"])
    return st