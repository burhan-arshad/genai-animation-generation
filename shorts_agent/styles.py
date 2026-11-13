"""Per-style configuration. Base styles come from the engine pack; every niche pack (niches/*.json) becomes a style on top of one."""
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


STYLES: dict[str, Style] = {
    "inside-out": Style(
        key="inside-out", voice="am_michael", speed=1.0, lead=0.4, outro=0.9, gap=0.28,
        music="bed", music_options=("bed",), caps_max_words=3, min_words=85, max_words=115,
        caps_example='text: "Well, it slides down your throat and lands right in your stomach,"\n'
                     'caps: "WELL, IT *SLIDES | DOWN YOUR *THROAT | RIGHT IN YOUR *STOMACH" (UPPERCASE)',
        write_rules="""- Talk like a person to a friend: full flowing sentences with connecting words ("Well,", "but", "so").
- 90-110 words. Each entry in `lines` is one CUT (1.5-3.5 s): split sentences into 1-3 lines at natural pauses.
- Structure: hook question, escalation, a myth or surprise, a twist, a punchy last line that loops back to the hook.
- Write numbers as spoken words in `text`. Accurate science, no gore.""",
        board_rules="""- Reuse the kit (K.man, K.room, K.xray, K.pill, K.tag, K.redX, K.warning, K.stopwatch, K.calendar, K.stomach, K.makeGut...).
  For things the kit lacks (lungs, balloon, brain...) define NEW local helpers at the top of shots.js in the same flat style:
  flat fills from palette C, one darker shade, one light highlight, ink outlines only on graphics.
- One visual mode per shot. X-ray means the WHOLE body is x-ray (K.man xray: true) on K.xray(t). Cyan only inside the body,
  red only for danger, yellow for highlights.
- Keep key action between y 250 and 1250 (captions cover y 1250-1550). The last line: the hero looks at the camera."""),
    "paper-atlas": Style(
        key="paper-atlas", voice="bm_george", speed=1.0, lead=0.4, outro=1.1, gap=0.3,
        music="bed", music_options=("bed", "tension"), caps_max_words=4, min_words=85, max_words=115,
        caps_example='text: "In sixteen sixty-six, a tiny bakery fire burned down most of London."\n'
                     'caps: "In *1666, | a tiny *bakery fire | burned down *London." (normal case, digits allowed)',
        write_rules="""- Calm, curious, vivid documentary narration; full flowing sentences with connecting words.
- 95-110 words. Each entry in `lines` is one CUT (2-4 s): split sentences into 1-3 lines at natural pauses.
- Structure: surprising outcome first (hook), where and when, how it unfolded (cause and effect), the turning point,
  the consequences, a punchy last line that echoes the hook.
- Tell it with objects, places and consequences. Nothing graphic: no gore, no described violence, no invented quotes or dialogue.
- Write years and numbers as spoken words in `text` ("sixteen sixty-six"); `caps` may use digits.""",
        board_rules="""- Everything is cut paper: draw shapes with K.cut(pathFn, colour) and the P_* helpers (K.P_rr, K.P_circ, K.P_poly) so they get
  the paper edge and shadow. Palette = K.P. Crimson only for routes, targets, fire and the key word; gold only for dates, crowns, seals.
- Maps first: where, then who, then what. Open every new era with a gold date ribbon K.ribbon(text, x, y, scale).
- For real places draw a simplified outline in shots.js (like londonMap in the example); K.map() is for invented coastlines.
- Use K.figure (roles king, queen, sailor, scholar, guard, merchant, worker), K.hall(), K.harbor(t, shipX), K.ship, K.slip for
  names and numbers, K.seal, K.timeline, K.dashedRoute.
- Night = the same parchment under a navy wash (see nightPage in the example). Define new objects (houses, flames, smoke,
  barrels...) as local helpers at the top of shots.js using K.cut.
- No battles or violence on screen: show objects, places and consequences.
- Captions are drawn by the engine on a torn strip at y 1640; keep timelines and labels above y 1450."""),
}

# The scenery library API (overlay/<niche>/src/core/props.js). Always imported as SC so it can never be shadowed by the shots array S.
SCENERY_API = """

SCENERY LIBRARY (always use it): `import * as SC from './core/props.js';`
- Every shot after the intro is a FULLY ANIMATED SCENE of what happens in the story, never a talking head. Build each scene with
  SC.stage({ sky: 'day'|'dusk'|'night'|'storm'|'dawn', ground: 'grass'|'street'|'dirt'|'snow'|'sand', groundY: 800..1000, hills: true|false,
  skyline: true, mountains: true }, t) and then place props. A prop's y is its ground contact: use values from groundY+40 to groundY+480
  (lower on screen = closer = larger scale). Keep key action above y 1500.
- Scale guide: houses s 1.2-2.0 (a house is about 375 px tall at s=1), trees s 1.0-2.0, church/castle s 0.9-1.4, vehicles s 1.0-1.6,
  crowd people h 220-300 (people are about 0.6x the height of a house at the same scale). Fill the frame: big near props (a fence, barrels,
  a tree at s 1.8-2.2) at the left and right edges, mid-size buildings in the middle, a small far skyline. No large empty sky or empty ground.
- Props: SC.house(x,y,s,{kind:'timber'|'brick'|'cottage', lit, smoke, t}), SC.tree(x,y,s,'oak'|'pine'|'bare',t,seed), SC.church, SC.castle,
  SC.factory(x,y,s,t), SC.train(x,y,s,t), SC.cart(x,y,s,t), SC.crowd(x,y,width,n,seed,t,{moving,h}), SC.lamp, SC.fence, SC.barrel, SC.crate,
  SC.flame(x,y,s,t), SC.smoke(x,y,s,t), SC.rain(t), SC.snow(t), SC.nightWash(alpha). Also K.figure (roles king, queen, sailor, scholar,
  guard, merchant, worker, only for story characters), K.ship, K.harbor, K.map, K.ribbon, K.slip, K.timeline, K.seal.
- Layer 3 depths (far skyline/hills, mid buildings, near people/props). Make things move during the shot (pass t; vehicles travel with lt;
  smoke rises; flames flicker; trees sway).
- Gold date ribbon (K.ribbon) opens each new era; K.slip carries names and numbers."""


def _host_rules(appear: str) -> str:
    if appear == "none":
        return "\n\nNO HOST CHARACTER: never draw a person as a host and never import hero.js."
    last = (" The host is also added automatically to the LAST shot (bottom right): keep x > 600, y > 800 of the last shot free of "
            "important objects." if appear == "first_last" else "")
    return f"""

CHANNEL HOST (added automatically by the engine, NEVER draw him yourself): a human host is drawn on top of the FIRST shot (S01),
standing on the right side, and then he is gone.{last}
- Shot S01 is the intro backdrop of the topic: SC.stage plus 3-4 era-correct props that hint at the story (buildings, trees, a cart,
  barrels), packed into the LEFT 60% of the frame (x < 650). Keep the right 40% (x > 650, y > 700) free for the host: only sky and ground there.
  Do not draw any person in S01.
- Never import hero.js or host.js and never call H.hero."""


def _from_niche(key: str) -> Style:
    n = niche.load(key)
    base = STYLES[n.get("engine", "paper-atlas")]
    w = n["writing"]
    return replace(base, key=key, engine=n.get("engine", "paper-atlas"), use_brand=True, hero=True, niche=key,
                   music_options=tuple(w.get("music_options", base.music_options)),
                   min_words=int(w.get("min_words", base.min_words)), max_words=int(w.get("max_words", base.max_words)),
                   write_rules=w["rules"],
                   board_rules=base.board_rules + SCENERY_API + n.get("storyboard", {}).get("rules", ""))


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
        from .brand import appear, load
        b = load()
        v = b["voice"]
        st = replace(st, voice=v["name"], speed=float(v["speed"]), music=v.get("music", st.music),
                     write_rules=st.write_rules + "\n" + b["audience"]["writing_note"],
                     board_rules=st.board_rules + (_host_rules(appear()) if st.hero else ""))
    return st
