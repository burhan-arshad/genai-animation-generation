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
    props_mode: str = "library"          # "library" = fixed scenery (props.js) | "generate" = LLM designs the props per video
    props_theme: str = ""
    props_required: tuple = ()
    props_note: str = ""


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

# Generic cut-paper rules for niches whose props are generated (the base paper-atlas rules are history/map flavoured)
PAPER_CORE = """
- Everything is cut paper: draw shapes with K.cut(pathFn, colour) and the P_* helpers (K.P_rr, K.P_circ, K.P_poly) so they get the paper
  edge and shadow. Use the niche palette NC from niche_props.js; K.ribbon / K.slip / K.timeline / K.seal are available for labels, names and numbers.
- Captions are drawn by the engine on a torn strip at y 1640; keep labels and key action above y 1450.
- Nothing graphic: show objects, places and consequences."""

GENERATED_API = """

SCENERY LIBRARY OF THIS VIDEO (generated for this topic, shown above as src/core/niche_props.js, ALWAYS import it as NP):
`import * as NP from './core/niche_props.js';`
- Use ONLY names that are really exported there, always as NP.name(x, y, s, t, o): x = centre, y = ground contact, s = scale, t = film time,
  o = options. NP.backdrop(t, { variant: 'a' | 'b' | 'c' }) draws the whole background: call it FIRST in every shot and vary the variant.
- Optional effects from './core/props.js', imported EXACTLY as `import * as SC from './core/props.js';`: ONLY SC.cloud(x,y,s,color),
  SC.smoke(x,y,s,t), SC.flame(x,y,s,t), SC.rain(t), SC.snow(t), SC.nightWash(alpha). Every other SC function is historical scenery: never use it.
- K.figure roles are period costumes: avoid them unless the story needs a period person; prefer people props from NP.
- Every shot after the intro is a FULLY ANIMATED SCENE of what happens in the story, never a talking head. Build 3 depths (far backdrop,
  mid props, near props), fill the frame (big near props at the left and right edges), pass t so things move (spin, sway, twinkle, drift).
  Keep key action above y 1500."""


def _host_rules(appear: str, mode: str = "library") -> str:
    if appear == "none":
        return "\n\nNO HOST CHARACTER: never draw a person as a host and never import hero.js."
    last = (" The host is also added automatically to the LAST shot (bottom right): keep x > 600, y > 800 of the last shot free of "
            "important objects." if appear == "first_last" else "")
    if mode == "generate":
        s01 = ("- Shot S01 is the intro backdrop of the topic: NP.backdrop plus 3-4 NP props that hint at the story, packed into the LEFT 60% of\n"
               "  the frame (x < 650). Keep the right 40% (x > 650, y > 700) free for the host: only background there.\n"
               "  Do not draw any person in S01.")
    else:
        s01 = ("- Shot S01 is the intro backdrop of the topic: SC.stage plus 3-4 era-correct props that hint at the story (buildings, trees, a cart,\n"
               "  barrels), packed into the LEFT 60% of the frame (x < 650). Keep the right 40% (x > 650, y > 700) free for the host: only sky and ground there.\n"
               "  Do not draw any person in S01.")
    return f"""

CHANNEL HOST (added automatically by the engine, NEVER draw him yourself): a human host is drawn on top of the FIRST shot (S01),
standing on the right side, and then he is gone.{last}
{s01}
- Never import hero.js or host.js and never call H.hero."""


def _from_niche(key: str) -> Style:
    n = niche.load(key)
    base = STYLES[n.get("engine", "paper-atlas")]
    w = n["writing"]
    pr = n.get("props") or {}
    mode = pr.get("mode", "library")
    rules = n.get("storyboard", {}).get("rules", "")
    board = (PAPER_CORE + GENERATED_API + rules) if mode == "generate" else (base.board_rules + SCENERY_API + rules)
    return replace(base, key=key, engine=n.get("engine", "paper-atlas"), use_brand=True, hero=True, niche=key,
                   music_options=tuple(w.get("music_options", base.music_options)),
                   min_words=int(w.get("min_words", base.min_words)), max_words=int(w.get("max_words", base.max_words)),
                   write_rules=w["rules"], board_rules=board,
                   props_mode=mode, props_theme=pr.get("theme", ""), props_required=tuple(pr.get("required", [])),
                   props_note=pr.get("style_note", ""))

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
                     board_rules=st.board_rules + (_host_rules(appear(), st.props_mode) if st.hero else ""))
    return st

def delete_jobs(ids: list[int]) -> None:
    if not ids:
        return
    con = db()
    marks = ",".join("?" * len(ids))
    con.execute(f"DELETE FROM events WHERE job_id IN ({marks})", ids)
    con.execute(f"DELETE FROM jobs WHERE id IN ({marks})", ids)
    con.commit()
