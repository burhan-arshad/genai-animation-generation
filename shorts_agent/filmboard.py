"""Film storyboard: the LLM directs a cinematic short (cast, sets, objects, shots with acting) as plain data; this module checks it,
resolves every spoken word to a time, adds the host's intro and outro, and writes data/story.json for the 'film' engine.
build_shots / sync_overlay / contact_sheet are the entry points used by pipeline.py and preview.py; a niche whose engine is not 'film'
is passed on to the old Tall Tale storyboard (storyboard_agent.py), so both engines keep working."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from . import brand, styles
from .config import REPO, SKILL_DIR
from .director import Timing
from .gemini_voice import MOOD_FOR, load_plan
from .llm import BudgetExceeded, generate_structured

# ───────────── vocabulary (the engine's names: see engine/styles/film/example/src/core/*.js) ─────────────
PROPS = ["house", "shop", "barn", "tent", "tree", "pine", "bush", "fence", "lamp", "signpost", "sign", "poster", "crate", "barrel", "table", "desk",
         "chair", "bookshelf", "book", "openbook", "scroll", "letter", "coin", "coins", "key", "bell", "bucket", "shovel", "hammer", "chisel", "ladder",
         "lightbulb", "globe", "clock", "telescope", "podium", "flag", "ticket", "stone_block", "stone_giant", "pit", "mound", "wagon", "ship", "train",
         "rails", "fire", "smoke", "water", "crowd", "rubble", "sparkle"]
ARMS = ["down", "hip", "present", "point", "point_up", "wave", "both_up", "chin", "cheeks", "shrug", "hold", "reach", "cross", "clap"]
BOTH_ARMS = {"both_up", "cheeks", "shrug", "clap", "cross"}
MOODS = ["neutral", "happy", "smug", "laugh", "shock", "worried", "angry", "sad", "sly", "proud", "tired", "dizzy", "think"]
HATS = ["none", "cap", "tophat", "bowler", "crown", "helmet", "bonnet", "turban", "beret", "sailor"]
HAIRS = ["messy", "side", "curly", "short", "bald", "long", "bun"]
NECKS = ["none", "scarf", "bowtie", "tie", "collar"]
PATTERNS = ["plain", "vest", "stripes", "check", "apron", "overalls"]
EXTRAS = ["glasses", "blush", "mustache", "beard", "freckles", "monocle"]
SKINS = ["#E0A97A", "#F1C9A0", "#C98B5E", "#9C6240", "#6F4430"]
SET_KINDS = ["field", "street", "room", "city", "sea", "desert", "mountain", "map", "card"]
TIMES = ["day", "dusk", "night", "dawn", "sepia", "storm"]
CAMERAS = ["static", "push_in", "pull_out", "pan_left", "pan_right", "drift", "crane_down", "crane_up", "punch_in", "handheld"]
FRAMINGS = ["establishing", "wide", "full", "medium", "close", "extreme_close"]
TRANSITIONS = ["cut", "fade", "dissolve", "whip", "wipe", "flash", "iris"]
EFFECTS = ["none", "shake", "quake", "flash", "storm", "dutch"]
FXS = ["none", "dust", "rain", "snow", "embers", "confetti", "leaves", "fireflies"]
ACTS = ["", "jump", "shake", "bow", "pop", "nod"]
MOVES = ["pop", "rise", "drop", "slide_l", "slide_r", "grow", "shake", "spin", "none"]
STYLES_C = ["label", "pop", "stamp"]
SHAPES = ["rect", "circle", "ellipse", "poly", "line", "text"]
MAX_SHOT = 6.2
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ───────────── the story object the LLM writes ─────────────
class Look(BaseModel):
    id: str
    body: str
    pattern: str
    patCol: str
    hat: str
    hatCol: str
    neck: str
    neckCol: str
    extra: list[str]
    hair: str
    hairStyle: str
    skin: str
    dress: bool
    kid: bool


class Dress(BaseModel):
    item: str
    x: float
    d: int
    s: float


class SetDef(BaseModel):
    id: str
    kind: str
    time: str
    sign: str
    deck: bool
    dress: list[Dress]


class Part(BaseModel):
    shape: str
    x: float
    y: float
    w: float
    h: float
    rot: float
    color: str
    text: str
    pts: list[list[float]]


class CustomProp(BaseModel):
    name: str
    span: float
    parts: list[Part]


class Beat(BaseModel):
    word: str
    mood: str
    arms: str
    act: str
    face: str


class Actor(BaseModel):
    who: str
    x0: float
    x1: float
    d: int
    face: str
    mood: str
    arms: str
    legs: str
    talk: bool
    held: str
    beats: list[Beat]


class PropPlace(BaseModel):
    name: str
    x: float
    d: int
    s: float
    word: str
    move: str
    c: str
    text: str


class Callout(BaseModel):
    text: str
    word: str
    style: str


class ShotDraft(BaseModel):
    line: int
    word: str
    set: str
    framing: str
    camera: str
    focus_x: float
    transition: str
    effect: str
    fx: str
    actors: list[Actor]
    props: list[PropPlace]
    callouts: list[Callout]
    note: str


class StoryDraft(BaseModel):
    title: str
    place: str
    date: str
    intro_lines: int
    outro_lines: int
    intro_prop: str
    outro_stamp: str
    cast: list[Look]
    sets: list[SetDef]
    custom_props: list[CustomProp]
    shots: list[ShotDraft]


# ───────────── cleaning helpers ─────────────
def _id(s) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(s or "").strip().lower().replace(" ", "_").replace("-", "_"))[:24]


def _hex(c, default: str) -> str:
    c = str(c or "").strip()
    return c if HEX.match(c) else default


def _num(v, lo, hi, default) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _pick(v, allowed, default):
    v = str(v or "").strip().lower()
    return v if v in allowed else default


def _norm(w) -> str:
    return re.sub(r"[^a-z0-9']+", "", str(w).lower())


def clean_look(l: Look, warns: list[str]) -> dict:
    return {"body": _hex(l.body, "#3FA7A0"), "pattern": _pick(l.pattern, PATTERNS, "plain"), "patCol": _hex(l.patCol, "#6B422B"),
            "hat": _pick(l.hat, HATS, "none"), "hatCol": _hex(l.hatCol, "#8C5A3A"), "neck": _pick(l.neck, NECKS, "none"), "neckCol": _hex(l.neckCol, "#F26B5B"),
            "extra": [e for e in dict.fromkeys(str(x).strip().lower() for x in l.extra) if e in EXTRAS][:3], "hair": _hex(l.hair, "#2B2118"),
            "hairStyle": _pick(l.hairStyle, HAIRS, "short"), "skin": l.skin if l.skin in SKINS else _hex(l.skin, SKINS[0]), "dress": bool(l.dress), "kid": bool(l.kid)}


def clean_custom(c: CustomProp, warns: list[str]) -> dict | None:
    name = _id(c.name)
    parts = []
    for p in c.parts[:18]:
        sh = _pick(p.shape, SHAPES, "")
        if not sh:
            continue
        pts = [[_num(a, -60, 160, 0), _num(b, -60, 160, 0)] for a, b in [(q + [0, 0])[:2] for q in p.pts[:20]]]
        if sh in ("poly", "line") and len(pts) < (3 if sh == "poly" else 2):
            continue
        parts.append({"shape": sh, "x": _num(p.x, -60, 60, 0), "y": _num(p.y, -10, 160, 0), "w": _num(p.w, 0.5, 160, 10), "h": _num(p.h, 0.5, 160, 10),
                      "rot": _num(p.rot, -360, 360, 0), "color": _hex(p.color, "#8C5A3A"), "text": re.sub(r"[^A-Za-z0-9 !?.,'$%:/-]", "", p.text)[:24], "pts": pts})
    if not name or len(parts) < 3:
        warns.append(f"custom object '{c.name}' dropped (needs at least 3 valid parts)")
        return None
    return {"name": name, "span": round(_num(c.span, 60, 700, 300), 1), "parts": parts}


def split_title(title: str) -> str:
    words = title.replace("|", " ").split()
    if len(words) <= 2:
        return " | ".join(words) if len(words) == 2 else title
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " | ".join([" ".join(words[:best]), " ".join(words[best:])])


# ───────────── draft -> story.json ─────────────
def build(d: StoryDraft, tm: Timing, hero_ok: bool = True, hook: dict | None = None, appear: str = "first_last", plan: dict | None = None,
          cold: float = 0.0, loop: bool = False) -> tuple[dict, list[str], list[str]]:
    """hook = script.json "hook" (on-screen hook text and end question); appear = brand.json host setting; plan = the narrator's emotion per line;
    cold = seconds of cold open before the host appears; loop = repeat the opening picture in the last second."""
    problems: list[str] = []
    warns: list[str] = []
    hook, plan = hook or {}, plan or {}
    n = len(tm.lines)
    intro = int(_num(d.intro_lines, 1, 3, 2))
    outro = int(_num(d.outro_lines, 1, 2, 1))
    if appear == "none":
        intro = outro = 0
    elif appear == "first":
        outro = 0
    if intro + outro >= n:
        intro, outro = (1, 1) if appear == "first_last" else (1 if appear == "first" else 0, 0)
    loop_s = 1.0 if (loop and appear != "none" and tm.dur > 12) else 0.0
    mood_of = lambda i, default: MOOD_FOR.get((plan.get(i) or {}).get("emotion", ""), default)
    hook_text = re.sub(r"\s+", " ", str(hook.get("text") or "")).strip()[:30] or re.sub(r"[^A-Za-z0-9 ?!'-]", "", d.title).upper()[:28]
    end_q = re.sub(r"\s+", " ", str(hook.get("end_question") or "")).strip()[:26]

    custom: dict[str, dict] = {}
    for c in d.custom_props[:8]:
        cc = clean_custom(c, warns)
        if cc and cc["name"] not in PROPS:
            custom[cc["name"]] = cc
    known = set(PROPS) | set(custom)
    cast = {}
    for l in d.cast[:8]:
        i = _id(l.id)
        if i and i not in ("hero", "host"):
            cast[i] = clean_look(l, warns)
    sets: dict[str, dict] = {}
    for s in d.sets[:8]:
        i = _id(s.id)
        if not i:
            continue
        dress = [{"item": _id(x.item), "x": round(_num(x.x, 0, 100, 50), 1), "d": int(_num(x.d, 0, 2, 1)), "s": round(_num(x.s, 0.3, 3, 1), 2)}
                 for x in s.dress[:10] if _id(x.item) in known]
        sets[i] = {"kind": _pick(s.kind, SET_KINDS, "field"), "time": _pick(s.time, TIMES, "day"), "sign": re.sub(r"[^A-Za-z0-9 !?.,'&-]", "", s.sign)[:14].upper(),
                   "deck": bool(s.deck), "dress": dress}
    if not sets:
        problems.append("Define at least one set.")
    sets["study"] = {"kind": "study", "time": "night", "dress": []}
    first_set = next(iter(sets))

    shots: list[dict] = []
    lo_line, hi_line = intro, n - outro                  # story shots cover lines [lo_line, hi_line)
    t_lo = tm.start(lo_line) if lo_line < n else tm.dur
    t_hi = tm.start(hi_line) if hi_line < n else tm.dur - loop_s

    def stamp(line: int, word: str) -> float:
        lo, hi = tm.start(line), tm.end(line)
        t = tm.find(word, lo, hi) if word else None
        return round(t if t is not None else lo, 3)

    drafts = []
    for sd in d.shots[:60]:
        if not lo_line <= sd.line < hi_line:
            warns.append(f"shot on line {sd.line} is outside the story lines {lo_line}-{hi_line - 1}: dropped")
            continue
        drafts.append((stamp(sd.line, sd.word), sd))
    drafts.sort(key=lambda x: x[0])
    clean_d = []
    for t, sd in drafts:
        if clean_d and t - clean_d[-1][0] < 0.8:
            warns.append(f"shot at {t:.1f}s starts less than 0.8 s after the previous one: dropped")
            continue
        clean_d.append((t, sd))
    if clean_d:
        clean_d[0] = (t_lo, clean_d[0][1])
    else:
        problems.append("No usable story shots.")
    starts = [t for t, _ in clean_d]
    for ln in range(lo_line, hi_line):
        s0, e0 = tm.start(ln), tm.end(ln)
        last = max([t for t in starts if t <= s0 + 0.05] or [t_lo])
        if e0 - last > 5.5:
            problems.append(f"Line {ln} has no shot of its own: add a shot for it (every line needs one; a line longer than 3 s gets two).")
            break

    for k, (t, sd) in enumerate(clean_d):
        end = clean_d[k + 1][0] if k + 1 < len(clean_d) else t_hi
        sh = {"set": _id(sd.set) if _id(sd.set) in sets and _id(sd.set) != "study" else first_set, "framing": _pick(sd.framing, FRAMINGS, "medium"),
              "camera": _pick(sd.camera, CAMERAS, "push_in"), "focus_x": round(_num(sd.focus_x, 10, 90, 50), 1), "transition": _pick(sd.transition, TRANSITIONS, "cut"),
              "effect": _pick(sd.effect, EFFECTS, "none"), "fx": _pick(sd.fx, FXS, "none"), "note": re.sub(r"\s+", " ", sd.note)[:90], "at": t, "end": round(end, 3),
              "actors": [], "props": [], "callouts": []}
        sh["effect"] = "" if sh["effect"] == "none" else sh["effect"]
        sh["fx"] = "" if sh["fx"] == "none" else sh["fx"]
        for a in sd.actors[:4]:
            who = _id(a.who)
            if who not in cast:
                warns.append(f"shot {k + 1}: unknown character '{a.who}' dropped")
                continue
            arms = _pick(a.arms, ARMS, "down")
            arm = {"l": arms, "r": arms} if arms in BOTH_ARMS else {"l": "down", "r": arms}
            beats = []
            for b in a.beats[:6]:
                bt = tm.find(b.word, t, end)
                if bt is None:
                    warns.append(f"shot {k + 1}: beat word '{b.word}' is not spoken in this shot: dropped")
                    continue
                ba = _pick(b.arms, ARMS, "")
                beat = {"t": round(bt, 3)}
                if _pick(b.mood, MOODS, ""):
                    beat["mood"] = _pick(b.mood, MOODS, "")
                if ba:
                    beat["arms"] = {"l": ba, "r": ba} if ba in BOTH_ARMS else {"l": "down", "r": ba}
                if _pick(b.act, ACTS, ""):
                    beat["act"] = _pick(b.act, ACTS, "")
                if _pick(b.face, ["l", "r"], ""):
                    beat["face"] = _pick(b.face, ["l", "r"], "")
                if len(beat) > 1:
                    beats.append(beat)
            sh["actors"].append({"who": who, "x0": round(_num(a.x0, -20, 120, 40), 1), "x1": round(_num(a.x1, -20, 120, a.x0), 1), "d": int(_num(a.d, 0, 2, 1)),
                                 "face": _pick(a.face, ["l", "r"], ""), "mood": _pick(a.mood, MOODS, "neutral"), "arms": arm, "legs": _pick(a.legs, ["stand", "sit", "walk", "run"], "stand"),
                                 "talk": bool(a.talk), "held": {"r": _id(a.held)} if _id(a.held) in known else {}, "beats": sorted(beats, key=lambda b: b["t"])})
        for p in sd.props[:8]:
            nm = _id(p.name)
            if nm not in known:
                warns.append(f"shot {k + 1}: unknown object '{p.name}' dropped")
                continue
            t0 = tm.find(p.word, t, end) if p.word else None
            sh["props"].append({"name": nm, "x": round(_num(p.x, 0, 100, 50), 1), "d": int(_num(p.d, 0, 2, 1)), "s": round(_num(p.s, 0.2, 4, 1), 2), "t0": round(t0 if t0 is not None else t, 3),
                                "move": _pick(p.move, MOVES, "pop"), "c": _hex(p.c, "") or "", "text": re.sub(r"[^A-Za-z0-9 !?.,'$%:/&-]", "", p.text)[:20]})
        for c in sd.callouts[:2]:
            txt = re.sub(r"\s+", " ", re.sub(r"[<>]", "", c.text)).strip()[:26]
            if txt:
                ct = tm.find(c.word, t, end) if c.word else None
                sh["callouts"].append({"text": txt, "t": round(ct if ct is not None else t + 0.3, 3), "style": _pick(c.style, STYLES_C, "label"), "dur": 2.4})
        shots.append(sh)

    # long shots are split: the same picture seen from another camera
    out = []
    for sh in shots:
        dur = sh["end"] - sh["at"]
        if dur <= MAX_SHOT:
            out.append(sh)
            continue
        parts = int(dur // 4.2) or 1
        cuts = [sh["at"] + dur * i / parts for i in range(parts)] + [sh["end"]]
        alt = {"push_in": "pull_out", "pull_out": "push_in", "pan_left": "pan_right", "pan_right": "pan_left", "static": "drift", "drift": "push_in", "crane_down": "push_in", "crane_up": "pull_out", "punch_in": "drift", "handheld": "drift"}
        for i in range(parts):
            c = json.loads(json.dumps(sh))
            c["at"], c["end"] = round(cuts[i], 3), round(cuts[i + 1], 3)
            if i:
                c["camera"] = alt[sh["camera"]] if i % 2 else sh["camera"]
                c["transition"] = "cut"
                c["callouts"] = [x for x in c["callouts"] if c["at"] <= x["t"] < c["end"]]
                c["effect"] = ""
            else:
                c["callouts"] = [x for x in c["callouts"] if x["t"] < c["end"]]
            out.append(c)
    shots = out

    # ---- the host: intro and outro ----
    hero_shots = []
    prop = _id(d.intro_prop)
    prop = prop if prop in known else "scroll"
    poses = [("happy", "present", "full", "push_in", 30), ("smug", "point", "medium", "drift", 32), ("think", "chin", "medium", "push_in", 34)]
    first_end = tm.start(1) if n > 1 else tm.dur
    cold = max(0.0, min(cold, first_end - 2.0)) if (intro and appear != "none") else 0.0
    if cold >= 0.8:                                           # cold open: the key picture and a question, before the host walks in
        hero_shots.append({"set": "study", "framing": "panel", "camera": "punch_in", "focus_x": 50, "transition": "cut", "effect": "flash", "fx": "dust",
                           "note": "cold open: the key picture and a question", "at": 0.0, "end": round(cold, 3), "actors": [], "props": [],
                           "callouts": [{"text": hook_text, "t": 0.12, "style": "pop", "dur": round(cold - 0.15, 2), "y": 300}], "panel": {"prop": prop, "s": 1.0}})
    else:
        cold = 0.0
    for i in range(intro):
        s0 = (cold if i == 0 else tm.start(i))
        e0 = tm.start(i + 1) if i + 1 < n else tm.dur
        mood, arm, fr, cam, hx = poses[i % 3]
        mood = mood_of(i, mood)
        sh = {"set": "study", "framing": fr, "camera": cam, "focus_x": 50 if i == 0 else 44, "transition": "cut", "effect": "", "fx": "dust", "note": "host introduces the story", "at": round(s0, 3), "end": round(e0, 3),
              "actors": [{"who": "hero", "x0": hx, "x1": hx, "d": 1, "face": "r", "mood": mood, "arms": {"l": "down", "r": arm}, "legs": "stand", "talk": True, "held": {}, "beats": []}],
              "props": [], "callouts": [], "panel": {"prop": prop, "s": 1.0}}
        if i == 0:                                         # the host walks in, waves, then presents the picture
            a0 = sh["actors"][0]
            a0.update({"x0": -14, "x1": hx, "t0": round(s0 + 0.1, 3), "t1": round(s0 + 1.5, 3), "face": "r"})
            a0["beats"] = [{"t": round(s0 + 1.55, 3), "arms": {"l": "down", "r": "wave"}}, {"t": round(s0 + 3.0, 3), "arms": {"l": "down", "r": "present"}, "act": "pop"}]
        if i == 0:
            sh["callouts"].append({"text": split_title(d.title), "t": round(s0 + 0.9, 3), "style": "title", "dur": min(4.0, e0 - s0 - 0.2), "y": 210})
        if i == 1 and (d.place or d.date):
            sh["callouts"].append({"text": " · ".join(x for x in (d.place.strip()[:18], d.date.strip()[:14]) if x), "t": round(s0 + 0.4, 3), "style": "label", "dur": min(3.0, e0 - s0 - 0.2), "y": 210})
        hero_shots.append(sh)
    outro_shots = []
    for i in range(outro):
        ln = n - outro + i
        s0, e0 = tm.start(ln), (tm.start(ln + 1) if ln + 1 < n else tm.dur - loop_s)
        sh = {"set": "study", "framing": "medium" if i == 0 else "close", "camera": "push_in", "focus_x": 44, "transition": "fade" if i == 0 else "cut", "effect": "", "fx": "dust", "note": "host closes the story", "at": round(s0, 3), "end": round(e0, 3),
              "actors": [{"who": "hero", "x0": 32, "x1": 32, "d": 1, "face": "r", "mood": mood_of(ln, "proud"), "arms": {"l": "down", "r": "hip"}, "legs": "stand", "talk": True, "held": {}, "beats": []}],
              "props": [], "callouts": [], "panel": {"prop": prop, "s": 1.0}}
        sh["actors"][0]["beats"] = [{"t": round(s0 + 0.2, 3), "act": "nod"}, {"t": round(max(s0 + 0.3, e0 - 1.6), 3), "mood": "happy", "act": "pop"}]
        if i == outro - 1 and end_q:
            sh["callouts"].append({"text": end_q, "t": round(s0 + 0.5, 3), "style": "label", "dur": round(max(1.0, e0 - s0 - 0.6), 2), "y": 210})
        if i == outro - 1 and d.outro_stamp.strip():
            sh["callouts"].append({"text": re.sub(r"[^A-Za-z0-9 !?]", "", d.outro_stamp).strip().upper()[:12], "t": round(max(s0 + 0.3, e0 - 1.6), 3), "style": "stamp", "dur": 1.5, "x": 730, "y": 380})
        outro_shots.append(sh)

    if appear != "first_last" and shots and end_q:
        last = shots[-1]
        last["callouts"].append({"text": end_q, "t": round(max(last["at"] + 0.4, last["end"] - 2.2), 3), "style": "label", "dur": 2.0, "y": 210})
    # the first story shot follows the host's intro with a transition
    if shots and shots[0]["transition"] == "cut":
        shots[0]["transition"] = "whip"
    if outro_shots and shots:
        outro_shots[0]["transition"] = "fade"

    allshots = hero_shots + shots + outro_shots
    if loop_s and allshots:                                   # the last second repeats the opening picture: the video replays into itself
        allshots[-1]["end"] = round(tm.dur - loop_s, 3)
        allshots.append({"set": "study", "framing": "panel", "camera": "drift", "focus_x": 50, "transition": "flash", "effect": "", "fx": "dust", "note": "loop: back to the opening picture",
                         "at": round(tm.dur - loop_s, 3), "end": round(tm.dur, 3), "actors": [], "props": [], "callouts": [{"text": hook_text, "t": round(tm.dur - loop_s, 3) - 0.6, "style": "pop", "dur": loop_s + 0.6, "y": 300}],
                         "panel": {"prop": prop, "s": 1.0}})
    for i, s in enumerate(allshots):
        s["id"] = f"S{i + 1:02d}"
    if allshots:
        allshots[0]["at"] = 0.0
        allshots[-1]["end"] = round(tm.dur, 3)
        if not any(sh_["at"] < 0 for sh_ in allshots):
            allshots[0]["at"] = 0.0

    # ---- checks the LLM must pass ----
    body = [s for s in shots]
    if body:
        if sum(1 for s in body if s["props"] or sets.get(s["set"], {}).get("dress")) < 0.8 * len(body):
            problems.append("Most shots must show objects (props or set dress) that the line talks about: a viewer with the sound off must understand the story.")
        if sum(1 for s in body if s["actors"]) < 0.6 * len(body):
            problems.append("People must be in at least 60% of the shots.")
        acting = sum(1 for s in body if any(a["beats"] or a["arms"]["r"] != "down" or a["x0"] != a["x1"] for a in s["actors"]))
        if acting < 0.5 * len(body):
            problems.append("Characters must act: in at least half of the shots give them a beat (mood on a spoken word), a gesture (arms) or a walk (x0 != x1).")
        if len({s["camera"] for s in body}) < 4:
            problems.append("Use at least 4 different camera moves.")
        if len({s["framing"] for s in body}) < 3:
            problems.append("Use at least 3 different framings.")
        if sum(1 for s in body if s["framing"] in ("close", "extreme_close")) > 0.3 * len(body):
            problems.append("At most 30% of the shots may be close-ups.")
        for a, b in zip(body, body[1:]):
            if (a["set"], a["framing"], a["camera"]) == (b["set"], b["framing"], b["camera"]):
                problems.append(f"Shots {a['id']} and {b['id']} repeat set + framing + camera move: change one of them.")
                break
        if sum(1 for s in body for p in s["props"] if p["move"] not in ("pop", "none")) < 2:
            problems.append("Give at least two objects a motion (rise, drop, slide_l, slide_r, shake, spin).")
        if not any(s["callouts"] for s in body):
            problems.append("Add callouts (years, numbers, names, signs) to at least two shots.")
    if len(cast) < 1:
        problems.append("Define at least one character in `cast`.")

    story = {"title": d.title, "meta": {"place": d.place, "date": d.date}, "duration": round(tm.dur, 3), "cast": cast, "sets": sets, "custom": custom, "shots": allshots}
    return story, problems, warns


# ───────────── prompt ─────────────
SYSTEM = f"""You direct a cinematic 40-60 second history short for a channel whose host, 'the History Student', appears ONLY at the start and the end.
The host's intro and outro are added by the engine. YOU direct everything in between as a FILM: scenes with places, people who act, objects that move,
a camera that moves in every shot, cuts and transitions. The host's voice keeps talking over your scenes. You never write code: you return ONE JSON
object that matches the schema.

THE MOST IMPORTANT RULE: a viewer with the sound off must understand the story from the pictures. In every shot put on screen the people, place and
OBJECTS the line talks about. Reveal an object on its spoken word (`word` in props). Tell the story as scenes, like a movie: an argument is two people
talking, a carving is a sculptor with a hammer and a stone, a burial is a shovel and a mound, a discovery is diggers and a pit, a crowd is `crowd`.
Never show a result before the narration reaches it.

STAGE: x runs 0..100 (percent of the stage width, 0 = far left, 100 = far right). Characters stand at x 15..85. `focus_x` is where the camera looks.
d = depth: 0 behind, 1 normal, 2 in front of the others. Big scenery (house, barn, tent, tree, ship, train) goes at d 0 with s 1-1.6; small objects
(book, coin, tools) go beside the actors at d 1-2 with s 0.5-1; the main object of the story is large (s 1.3-2.2) and stays in frame. A person is about
as tall as a door.
CAST (2-6 characters for THIS story; never 'hero' or 'host'): id (lowercase letters), body/hatCol/neckCol/hair colours as #RRGGBB, pattern {', '.join(PATTERNS)},
hat {', '.join(HATS)}, neck {', '.join(NECKS)}, extra (any of {', '.join(EXTRAS)}), hairStyle {', '.join(HAIRS)}, skin one of {', '.join(SKINS)}, dress true
for a woman's dress, kid true for a child. Clothes must fit the era and the people, with clearly different colours. Unused text = "".
SETS (2-6, one per place or time of the story): kind {', '.join(SET_KINDS)}; time {', '.join(TIMES)} (use sepia for a flashback, night for a mystery, dusk for an ending, storm for a disaster);
sign = a short shop name for `street`; deck true for a ship deck; dress = scenery items {{item, x, d, s}} from the objects below.
OBJECTS (built in): {', '.join(PROPS)}.
CUSTOM OBJECTS: for the story's own special things that are not in that list (an invention, a machine, a document) design them in `custom_props`:
name, span (width in px, 150-500) and parts of plain shapes in a 100x100 box (x -50..50 left to right, y 0..100 from the ground up):
rect/circle/ellipse (x, y = centre, w, h), poly/line (pts = [[x,y],...]), text (text, h = size). 6-14 parts, 2-4 colours, a recognisable silhouette.
Then use the name in `props` or `intro_prop`.
SHOTS: at least one per story line, in order (a line longer than 3 s gets two: the second has `word` = the first spoken word of its second half).
`line` = script line index, `word` = a spoken word of that line where the shot starts ("" = the start of the line). Each shot: set, framing {', '.join(FRAMINGS)},
camera {', '.join(CAMERAS)}, transition {', '.join(TRANSITIONS)}, effect {', '.join(EFFECTS)}, fx {', '.join(FXS)}, actors, props, callouts, note (what the viewer sees).
ACTING: every actor has a start mood and arms pose ({', '.join(ARMS)}; both-arm poses: {', '.join(sorted(BOTH_ARMS))}), legs {{stand, sit, walk, run}}, x0 -> x1
(different = the person walks), face l|r (which way they look), talk true for whoever speaks, `held` = an object name in the hand, and `beats` = changes on a spoken
word: {{word, mood, arms, act (jump, shake, bow, pop, nod or ""), face}}. Give beats in most shots (shock when the object appears, joy on the payoff, worry in trouble).
Moods: {', '.join(MOODS)}. Objects MOVE: give some a move ({', '.join(MOVES)}).
RICHNESS: build every picture in layers: scenery at d 0 (house, barn, tree, lamp, fence), the main action at d 1, small things (a book, coins, a tool, a crate) in front at d 2.
Put an object in a person's hand with `held` when they use it. A scene with only two people and nothing else is a mistake. Let a reveal feel like an event: the object
drops or rises with a `move`, the person reacts on the same word with a beat (shock, jump), and a callout names it. Use time of day to carry the story (dawn = start, dusk = end).
DIRECTION: no two neighbouring shots with the same set + framing + camera move; use at least 4 camera moves and 3 framings; close-ups only for reactions (max 30%).
Open the story with a wide or establishing shot of the place. Transitions: cut by default; fade/dissolve when time passes, wipe/whip when the place changes, flash on an impact.
Effects: shake or quake for impacts and earthquakes, storm for storms, flash for a bang, dutch (a tilted camera) for lies, danger, unease and the moment a trick is exposed. fx: dust (indoors), rain, snow, embers (fire), confetti (celebration), leaves.
CALLOUTS (max two per shot, 26 characters): years, numbers, names, signs as digits ("1869", "10 FEET", "CARDIFF, N.Y."); style label (place/date tag), pop (one big word),
stamp (rubber stamp: HOAX, BANNED).
INTRO/OUTRO: intro_lines = how many of the first script lines the host says alone (1-3: the hook), outro_lines = how many of the last lines (1-2: the punchline).
intro_prop = the ONE object that best shows the story (a built-in or custom object), outro_stamp = one short word for the end ("HOAX", "TRUE", "BANNED", "" for none).
title = the short title, place = "Cardiff, New York", date = "1869" (short, for the host's title card).
Facts: show only what the narration says. Nothing graphic."""


def build_prompt(script: dict, tm: Timing, topic: str, year, plan: dict | None = None, appear: str = "first_last") -> str:
    lines = "\n".join(f"{i}: [{l['start']:.1f}-{l['end']:.1f}s] {l['text']}" for i, l in enumerate(tm.lines))
    ex = json.dumps(EXAMPLE, ensure_ascii=False)
    host = {"first_last": "The host says the first `intro_lines` lines (the hook) and the last `outro_lines` lines (the punchline) on camera; you direct the lines in between.",
            "first": "The host appears only at the start (`intro_lines` = 1-3). Set `outro_lines` to 0: the last line is part of YOUR story, direct it too.",
            "none": "There is no host in this video: set `intro_lines` and `outro_lines` to 0 and direct EVERY line as a scene."}.get(appear, "")
    emo = ""
    if plan:
        emo = ("\nNARRATOR'S EMOTION PER LINE (the voice actor performs it: make the people on screen feel the same, so a viewer SEES what he hears. "
               "shocked -> a shock beat and a jump; amused -> laugh or smug; tense -> worried; curious -> think; excited, awe -> happy with arms up; triumphant -> proud; "
               "deadpan -> neutral or tired):\n" + "\n".join(f"{i}: {d['emotion']}, energy {d['energy']}, {d['note']}" for i, d in sorted(plan.items())))
    return (f"{SYSTEM}\n\n{host}\nThe video opens with a 2-second cold open (the `intro_prop` picture huge on screen with the hook as a question) and ends with a 1-second loop back to it: "
            "choose the single most striking object or picture of the story as `intro_prop`.\n\n"
            f"EXAMPLE of a good story object (another topic, copy the way of working, never the content):\n{ex}\n\nTOPIC: {topic}\nTITLE: {script['title']}\nYEAR: {year or 'unknown'}\n"
            f"SCRIPT (index: [start-end] text):\n{lines}\n{emo}\n\nWrite the story object for THIS script.")


def _beat(word, mood="", arms="", act="", face=""):
    return {"word": word, "mood": mood, "arms": arms, "act": act, "face": face}


def _actor(who, x0, x1=None, d=1, face="", mood="neutral", arms="down", legs="stand", talk=False, held="", beats=()):
    return {"who": who, "x0": x0, "x1": x0 if x1 is None else x1, "d": d, "face": face, "mood": mood, "arms": arms, "legs": legs, "talk": talk, "held": held, "beats": list(beats)}


def _prop(name, x, d=1, s=1.0, word="", move="pop", c="", text=""):
    return {"name": name, "x": x, "d": d, "s": s, "word": word, "move": move, "c": c, "text": text}


def _shot(line, word, set, framing, camera, focus_x, transition="cut", effect="none", fx="none", actors=(), props=(), callouts=(), note=""):
    return {"line": line, "word": word, "set": set, "framing": framing, "camera": camera, "focus_x": focus_x, "transition": transition, "effect": effect, "fx": fx,
            "actors": list(actors), "props": list(props), "callouts": list(callouts), "note": note}


def _look(id, body, pattern="plain", patCol="#6B422B", hat="none", hatCol="#8C5A3A", neck="none", neckCol="#F26B5B", extra=(), hair="#2B2118", hairStyle="short", skin="#E0A97A", dress=False, kid=False):
    return {"id": id, "body": body, "pattern": pattern, "patCol": patCol, "hat": hat, "hatCol": hatCol, "neck": neck, "neckCol": neckCol, "extra": list(extra), "hair": hair,
            "hairStyle": hairStyle, "skin": skin, "dress": dress, "kid": kid}


EXAMPLE = {
    "title": "The Girl Who Was Mailed", "place": "Idaho", "date": "1914", "intro_lines": 1, "outro_lines": 1, "intro_prop": "letter", "outro_stamp": "BANNED",
    "cast": [_look("may", "#7FC8E8", kid=True, hat="bonnet", hatCol="#F4EAD0", hair="#7A4A2A", hairStyle="long", dress=True, extra=["freckles"]),
             _look("clerk", "#4FB3A9", pattern="vest", patCol="#2B5E73", hat="cap", hatCol="#2F8F5B", neck="bowtie", neckCol="#C8283A", extra=["mustache"], hair="#4A3020", hairStyle="short")],
    "sets": [{"id": "post", "kind": "room", "time": "day", "sign": "", "deck": False, "dress": [{"item": "desk", "x": 70, "d": 0, "s": 1.0}, {"item": "bookshelf", "x": 12, "d": 0, "s": 0.9}]}],
    "custom_props": [{"name": "mail_sack", "span": 220, "parts": [{"shape": "rect", "x": 0, "y": 35, "w": 70, "h": 70, "rot": 0, "color": "#B5885A", "text": "", "pts": []},
                                                                {"shape": "rect", "x": 0, "y": 72, "w": 74, "h": 10, "rot": 0, "color": "#8C5A3A", "text": "", "pts": []},
                                                                {"shape": "text", "x": 0, "y": 38, "w": 10, "h": 14, "rot": 0, "color": "#2B1A10", "text": "U.S. MAIL", "pts": []}]}],
    "shots": [_shot(1, "", "post", "wide", "pull_out", 50, "whip", "none", "dust",
                    [_actor("clerk", 68, face="l", mood="worried", arms="hip", talk=True, beats=[_beat("stamps", "shock", "both_up", "jump")]), _actor("may", 30, 40, legs="walk", face="r", mood="happy")],
                    [_prop("mail_sack", 55, 1, 1.4, "mail", "rise"), _prop("letter", 22, 2, 0.8, "stamps", "drop")], [{"text": "IDAHO 1914", "word": "", "style": "label"}], "May and a clerk at the post office counter")],
}


# ───────────── fallback and entry points ─────────────
def fallback(tm: Timing, script: dict) -> StoryDraft:
    """A plain but valid film when the LLM cannot deliver: the host narrates over simple scenes."""
    n = len(tm.lines)
    sets = [{"id": "a", "kind": "field", "time": "day", "sign": "", "deck": False, "dress": [{"item": "tree", "x": 15, "d": 0, "s": 1.0}, {"item": "house", "x": 80, "d": 0, "s": 1.0}]},
            {"id": "b", "kind": "street", "time": "dusk", "sign": "HISTORY", "deck": False, "dress": [{"item": "lamp", "x": 30, "d": 0, "s": 1.0}]}]
    cams = ["push_in", "pan_right", "pull_out", "drift", "pan_left", "crane_down"]
    frs = ["wide", "medium", "full", "medium", "wide", "full"]
    moods = ["happy", "think", "smug", "shock", "worried", "proud"]
    shots = []
    for i in range(1, n - 1):
        shots.append(_shot(i, "", "ab"[i % 2], frs[i % 6], cams[i % 6], 50, "cut" if i % 3 else "dissolve", "none", "dust",
                           [_actor("narrator", 40 + (i % 3) * 8, face="r" if i % 2 else "l", mood=moods[i % 6], arms=["present", "point", "hip", "chin", "shrug", "wave"][i % 6], talk=True)],
                           [_prop("scroll", 70, 1, 1.0, "", "pop")], [], "plain scene (safe mode)"))
    cast = [_look("narrator", "#3FA7A0", neck="scarf", extra=["glasses"], hairStyle="messy")]
    return StoryDraft.model_validate({"title": script["title"], "place": "", "date": "", "intro_lines": 1, "outro_lines": 1, "intro_prop": "scroll", "outro_stamp": "", "cast": cast, "sets": sets,
                                      "custom_props": [], "shots": shots})


def engine_dir(st: styles.Style) -> Path:
    return SKILL_DIR / "styles" / (st.engine or "film") / "example"


def sync_overlay(project: Path, st: styles.Style) -> None:
    """Re-copy the film engine's code (src/, index.html) into the project and regenerate brand.js from brand/brand.json."""
    if (st.engine or "") != "film":
        from . import storyboard_agent
        return storyboard_agent.sync_overlay(project, st)
    src = engine_dir(st)
    shutil.copytree(src / "src", project / "src", dirs_exist_ok=True)
    shutil.copy(src / "index.html", project / "index.html")
    brand.write_js(project)


def contact_sheet(project: Path, story: dict, out: Path) -> None:
    from . import storyboard_agent
    storyboard_agent.contact_sheet(project, story, out)


def write_metrics(project: Path, story: dict, attempt: int, safe: bool) -> None:
    body = [s for s in story["shots"] if s["set"] != "study"]
    (project / "metrics.json").write_text(json.dumps({
        "shots": len(story["shots"]), "shots_with_props": sum(1 for s in body if s["props"]), "custom_objects": len(story["custom"]),
        "custom_used": len({p["name"] for s in body for p in s["props"]} & set(story["custom"])), "rounds": attempt, "safe_mode": safe,
        "effects": sum(1 for s in body if s.get("effect")), "moving_objects": sum(1 for s in body for p in s["props"] if p["move"] not in ("pop", "none")),
        "acting_shots": sum(1 for s in body if any(a["beats"] for a in s["actors"])), "relevance": None, "relevance_bad_shots": None}, indent=1), encoding="utf-8")


def write_props_json(project: Path, story: dict) -> None:
    """The dashboard lists the story's own objects from props.json."""
    (project / "props.json").write_text(json.dumps({"props": [{"name": n, "desc": "custom object (" + str(len(c["parts"])) + " parts)", "span": c["span"]} for n, c in story["custom"].items()]}, indent=1), encoding="utf-8")


def build_shots(project: Path) -> None:
    st = styles.active()
    if (st.engine or "") != "film":
        from . import storyboard_agent
        return storyboard_agent.build_shots(project)
    from .storyboard_agent import read, run_check, story_year, topic_of
    sync_overlay(project, st)
    max_tries = max(1, min(3, int(os.getenv("STORYBOARD_ROUNDS", "2") or 2)))
    tm = Timing.load(project)
    script = json.loads(read(project / "script.json"))
    topic, year = topic_of(project, script), story_year(project)
    try:
        appear = brand.appear()
    except ValueError:
        appear = "first_last"
    hook, plan = script.get("hook") or {}, load_plan(project)
    opts = {"hook": hook, "appear": appear, "plan": plan, "cold": float(os.getenv("FILM_COLD_OPEN") or 2), "loop": (os.getenv("FILM_LOOP") or "1") != "0"}
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    base = build_prompt(script, tm, topic, year, plan, appear)
    prompt, problems, last = base, [], None
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 2 else "storyboard_hard"
        draft = generate_structured(prompt, StoryDraft, system="You output only the JSON story object.", temperature=0.6, task=task)
        (logs / f"story_attempt{attempt}.json").write_text(draft.model_dump_json(indent=1), encoding="utf-8")
        story, problems, warns = build(draft, tm, **opts)
        for w in warns:
            print("   warning:", w)
        print(f"[storyboard] attempt {attempt} ({task}): {len(problems)} problem(s), {len(warns)} warning(s)")
        if not problems:
            (project / "data").mkdir(exist_ok=True)
            (project / "data" / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
            ok, out = run_check(project)
            (logs / f"check_attempt{attempt}.txt").write_text(out, encoding="utf-8")
            print(f"[storyboard] render check {'OK' if ok else 'FAILED'}")
            if ok:
                (project / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
                write_props_json(project, story)
                write_metrics(project, story, attempt, False)
                return
            problems = [f"The engine could not draw your story. Output (tail):\n{out[-1200:]}"]
        last = story if not last else last
        prompt = f"{base}\n\nYour previous story object:\n{draft.model_dump_json()}\n\nIt has these problems. Fix them and return the FULL corrected story object:\n- " + "\n- ".join(problems)
    # nothing passed: a plain film is better than no film
    print("[storyboard] the director could not deliver a clean story: SAFE MODE (plain scenes with the host narrating)")
    story, _, _ = build(fallback(tm, script), tm, **opts)
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
    ok, out = run_check(project)
    if not ok:
        raise RuntimeError("the film engine could not draw even the plain story:\n" + out[-800:])
    (project / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
    write_props_json(project, story)
    write_metrics(project, story, max_tries, True)
