"""Director: the LLM writes a story (cast, sets, props, shots, acting beats). This module checks it against the narration
timing, turns every spoken word into seconds and compiles src/shots.js for the Tall Tale engine (core/director.js)."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from pydantic import BaseModel

MOODS = ["neutral", "smug", "happy", "laugh", "shock", "worried", "angry", "sad", "sly", "proud", "tired", "dizzy"]
PATTERNS = ["plain", "check", "stripes", "overalls", "vest", "apron"]
HATS = ["none", "cap", "bowler", "boater", "beanie", "visor", "tophat", "bun", "flower", "bow", "mailcap"]
NECKS = ["none", "bowtie", "tie", "scarf", "collar"]
EXTRAS = ["mustache", "glasses", "freckles", "blush", "pencil", "monocle"]
SET_KINDS = ["street", "interior", "meadow", "open"]
FRAMINGS = ["extreme_close", "close", "medium", "full", "wide", "establishing"]
CAMERAS = ["drift", "push_in", "pull_out", "truck_left", "truck_right", "orbit_left", "orbit_right", "crane_down", "crane_up", "punch_in", "handheld"]
ACTIONS = ["stand", "walk_in", "walk_out", "cross_left", "cross_right", "run_in", "run_out", "run_left", "run_right", "sit", "jump"]
GESTURES = ["none", "wave", "point", "cheer", "arms_up", "shrug", "hip", "present", "think", "hold"]
HELD = ["parcels", "ticket", "purse", "letters", "rubberStamp", "stamp", "bill", "stack", "mirror", "cup", "key", "book", "paper", "sign", "cash"]
SFX = ["ding", "chirp", "chug", "stamp", "inhale", "heartbeat", "whoosh", "slide", "pop", "plop", "gulp", "boing", "bubbles",
       "sizzle", "sparkle", "thud", "slam", "tock", "zip", "alarm"]
TRANSITIONS = ["cut", "flash", "dip", "punch"]
CALLOUT_STYLES = ["stamp", "pop", "label"]
FX_TYPES = ["shake", "flash"]
SLOT_RE = re.compile(r"(?:(?:front|back)_)?(?:far_left|left|center|right|far_right)")
SPECIAL_SLOTS = {"street": {"boardwalk_left", "boardwalk_right"}, "interior": {"counter_clerk", "counter_top"}, "meadow": set(), "open": set()}
DRESS = {
    "street": {"tree", "barrel", "crate", "car", "lamp", "signpost", "parcel", "mail_sack", "fence", "crowd", "board"},
    "meadow": {"tree", "barrel", "crate", "car", "fence", "house", "signpost", "train", "pole", "parcel", "mail_sack", "crowd", "board"},
    "interior": {"desk", "cubbies", "poster", "scale", "chick_crate", "parcel", "mail_sack", "barrel", "crate", "crowd", "board"},
    "open": {"tree", "barrel", "crate", "car", "fence", "signpost", "parcel", "mail_sack", "house", "crowd", "board"},
}
BUILTIN_PROPS = sorted(set().union(*DRESS.values()))
BOUNDS = {"street": (-4.2, 4.2, -24, 3), "meadow": (-14, 14, -24, 3), "interior": (-3.2, 3.2, -3.5, 1.5), "open": (-14, 14, -24, 3)}
DEFAULT_ERA = {"train": 1825, "car": 1895, "lamp": 1807, "scale": 1880}
MAX_SHOT = 3.9
CALLOUT_DUR = {"stamp": 2.4, "pop": 1.9, "label": 3.4}
_CYCLE = ["push_in", "truck_right", "orbit_left", "pull_out", "truck_left", "orbit_right", "crane_down", "drift"]
_NEXT_FRAME = {"establishing": "wide", "wide": "medium", "full": "medium", "medium": "close", "close": "medium", "extreme_close": "close"}


# ---------- what the LLM returns (no defaults: every field is always written) ----------
class Look(BaseModel):
    body: str
    pattern: str
    patCol: str
    hat: str
    hatCol: str
    neck: str
    neckCol: str
    extra: list[str]
    kid: bool


class Cast(BaseModel):
    id: str
    look: Look


class Dress(BaseModel):
    item: str
    x: float
    z: float
    scale: float
    rot: float
    color: str
    text: str


class StorySet(BaseModel):
    id: str
    kind: str
    mood: str
    wall: str
    motif: str
    floor: str
    ceiling: str
    sign: str
    dress: list[Dress]


class Beat(BaseModel):
    word: str
    mood: str
    gesture: str
    prop: str
    sfx: str


class Actor(BaseModel):
    who: str
    slot: str
    mood: str
    action: str
    gesture: str
    prop: str
    looks_at: str
    talk: bool
    beats: list[Beat]


class Callout(BaseModel):
    text: str
    word: str
    style: str


class Fx(BaseModel):
    word: str
    type: str


class ShotProp(BaseModel):
    name: str
    x: float
    y: float
    z: float
    scale: float
    rot: float
    word: str
    text: str


class Shot(BaseModel):
    line: int
    word: str
    set: str
    framing: str
    camera: str
    focus: list[str]
    transition: str
    actors: list[Actor]
    callouts: list[Callout]
    props: list[ShotProp]
    fx: list[Fx]
    note: str


class Story(BaseModel):
    year: int
    cast: list[Cast]
    sets: list[StorySet]
    shots: list[Shot]


# ---------- narration timing ----------
def _norm(w) -> str:
    return re.sub(r"[^a-z0-9']+", "", str(w).lower())


class Timing:
    def __init__(self, lines: list[dict], words: list[dict], dur: float):
        self.lines, self.words, self.dur = lines, words, float(dur)

    @classmethod
    def load(cls, project: Path) -> "Timing":
        ln = json.loads((project / "data" / "lines.json").read_text(encoding="utf-8"))
        wd = json.loads((project / "data" / "words.json").read_text(encoding="utf-8"))
        return cls(ln["lines"], wd, float(ln["duration"]))

    def start(self, i: int) -> float:
        return float(self.lines[i]["start"])

    def end(self, i: int) -> float:
        return float(self.lines[i]["end"])

    def find(self, word, lo: float, hi: float):
        """Start time of the first spoken word (prefix match) inside [lo, hi]."""
        parts = str(word or "").split()
        tok = _norm(parts[0]) if parts else ""
        if not tok:
            return None
        for w in self.words:
            s = float(w["s"])
            if lo - 0.05 <= s <= hi + 0.01 and _norm(w["w"]).startswith(tok):
                return s
        return None

    def speech(self, lo: float, hi: float) -> list[list[float]]:
        out = []
        for i in range(len(self.lines)):
            s, e = max(self.start(i), lo), min(self.end(i), hi)
            if e > s:
                out.append([round(s, 3), round(e, 3)])
        return out


# ---------- cleaning helpers ----------
def _ident(s) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(s or "").strip().lower().replace(" ", "_").replace("-", "_"))[:24]


def _hex(s, default: str = "") -> str:
    s = str(s or "").strip()
    return s if re.fullmatch(r"#[0-9A-Fa-f]{6}", s) else default


def _pick(v, allowed, default):
    v = str(v or "").strip().lower()
    return v if v in allowed else default


def _num(v, lo, hi, default=0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else max(lo, min(hi, x))


_HELD = {h.lower(): h for h in HELD}


def _prop(s):
    """None = keep / nothing, False = put the prop down, dict = hold this prop."""
    s = str(s or "").strip()
    if not s:
        return None
    if s.lower() == "none":
        return False
    name, _, arg = s.partition(":")
    canon = _HELD.get(name.strip().lower())
    if not canon:
        return None
    return {"name": canon, "arg": re.sub(r"[^A-Za-z0-9 !?.$']", "", arg)[:14].strip()}


def _cast(items, warns) -> list[dict]:
    out, seen = [], set()
    for c in items[:8]:
        cid = _ident(c.id)
        if not cid or cid == "host" or cid in seen:
            warns.append(f"cast id {c.id!r} skipped")
            continue
        seen.add(cid)
        L = c.look
        look = {"body": _hex(L.body, "#E8734A"), "pattern": _pick(L.pattern, PATTERNS, "plain"), "hat": _pick(L.hat, HATS, "none"),
                "neck": _pick(L.neck, NECKS, "none"),
                "extra": [e for e in dict.fromkeys(str(x).lower() for x in L.extra) if e in EXTRAS][:3], "kid": bool(L.kid)}
        for key, val in (("patCol", L.patCol), ("hatCol", L.hatCol), ("neckCol", L.neckCol)):
            if _hex(val):
                look[key] = _hex(val)
        out.append({"id": cid, "look": look})
    return out


def _text(s, n=70) -> str:
    return re.sub(r"[^A-Za-z0-9 |!?.,&'$%:/-]", "", str(s))[:n]


def _sets(items, year: int, era: dict, warns, custom: set) -> list[dict]:
    out, seen = [], set()
    for s in items[:3]:
        sid = _ident(s.id) or f"set{len(out) + 1}"
        if sid in seen:
            continue
        seen.add(sid)
        kind = _pick(s.kind, SET_KINDS, "meadow")
        d = {"id": sid, "kind": kind, "mood": "dusk" if str(s.mood).strip().lower() in ("dusk", "sunset", "evening") else "day", "dress": []}
        if kind == "interior":
            for k in ("wall", "motif", "floor", "ceiling"):
                if _hex(getattr(s, k)):
                    d[k] = _hex(getattr(s, k))
            d["sign"] = re.sub(r"[^A-Za-z0-9 .&'!-]", "", str(s.sign))[:26].strip().upper()
        if kind == "open":                      # reuses the same fields: wall = sky top, motif = horizon, floor = ground, ceiling = hills, sign = "stars"
            d["top"], d["horizon"] = _hex(s.wall, "#3D8EE0"), _hex(s.motif, "#CBEAF8")
            d["ground"], d["hills"] = _hex(s.floor), _hex(s.ceiling)
            d["stars"] = "star" in str(s.sign).lower()
        x0, x1, z0, z1 = BOUNDS[kind]
        for it in s.dress[:14]:
            name = _ident(it.item)
            if name not in DRESS[kind] and name not in custom:
                warns.append(f"dress item {it.item!r} is not available in a {kind}: dropped")
                continue
            if year < era.get(name, 0):
                warns.append(f"dress item {name} did not exist in {year}: dropped")
                continue
            d["dress"].append({"item": name, "x": round(_num(it.x, x0, x1), 2), "z": round(_num(it.z, z0, z1), 2),
                               "scale": round(_num(it.scale, 0.5, 3, 1.0) or 1.0, 2), "rot": round(_num(it.rot, -360, 360), 1),
                               "color": _hex(it.color), "text": _text(it.text)})
        out.append(d)
    return out

def _shot_props(items, kind, at, end, tm, yr, era, custom, warns) -> list[dict]:
    out = []
    x0, x1, z0, z1 = BOUNDS[kind]
    ok = DRESS[kind] | custom
    for it in items[:6]:
        name = _ident(it.name)
        if name not in ok:
            warns.append(f"object {it.name!r} is unknown: dropped")
            continue
        if yr < era.get(name, 0):
            warns.append(f"object {name} did not exist in {yr}: dropped")
            continue
        t = tm.find(it.word, at, end) if str(it.word).strip() else None
        out.append({"name": name, "x": round(_num(it.x, x0, x1), 2), "y": round(_num(it.y, 0, 3), 2), "z": round(_num(it.z, z0, z1), 2),
                    "scale": round(_num(it.scale, 0.3, 3, 1.0) or 1.0, 2), "rot": round(_num(it.rot, -360, 360), 1),
                    "t": round(t, 3) if t is not None else None, "text": _text(it.text, 40)})
    return out


def _actor(a, ids, kind, at, end, tm, cues, warns):
    who = _ident(a.who)
    if who not in ids:
        warns.append(f"unknown character {a.who!r}: dropped")
        return None
    slot = str(a.slot or "").strip().lower().replace(" ", "_")
    if not SLOT_RE.fullmatch(slot) and slot not in SPECIAL_SLOTS[kind]:
        slot = "center"
    beats = []
    for b in a.beats[:6]:
        t = tm.find(b.word, at, end)
        if t is None:
            warns.append(f"beat word {b.word!r} is not spoken in {at:.1f}-{end:.1f}s: dropped")
            continue
        beats.append({"t": round(t, 3), "mood": _pick(b.mood, MOODS, ""), "gesture": _pick(b.gesture, GESTURES, ""), "prop": _prop(b.prop)})
        sfx = _pick(b.sfx, SFX, "")
        if sfx:
            cues.append({"t": round(t, 3), "type": sfx, "gain": 0.9})
    beats.sort(key=lambda x: x["t"])
    looks = _ident(a.looks_at)
    return {"who": who, "slot": slot, "mood": _pick(a.mood, MOODS, "neutral"), "action": _pick(a.action, ACTIONS, "stand"),
            "gesture": _pick(a.gesture, GESTURES, "none"), "prop": _prop(a.prop) or None, "looks_at": looks if looks in ids else "",
            "speech": tm.speech(at, end) if a.talk else [], "beats": beats}


def _callout(c, at, end, tm):
    text = re.sub(r"[^A-Za-z0-9 !?.,:&$'%/-]", "", str(c.text)).strip().upper()[:26]
    if not text:
        return None
    style = _pick(c.style, CALLOUT_STYLES, "pop")
    t = tm.find(c.word, at, end)
    if t is None:
        t = at + 0.3
    t = min(t, max(at + 0.1, end - 0.6))
    return {"t": round(t, 3), "text": text, "style": style, "dur": CALLOUT_DUR[style]}


# ---------- shot post-processing ----------
def _vary(shots) -> None:
    for i in range(1, len(shots)):
        a, b = shots[i - 1], shots[i]
        if a["set"] == b["set"] and a["framing"] == b["framing"] and a["camera"] == b["camera"]:
            c = _CYCLE[(i * 3) % len(_CYCLE)]
            b["camera"] = c if c != a["camera"] else _CYCLE[(i * 3 + 1) % len(_CYCLE)]


def _split_long(shots, tm) -> list[dict]:
    out = []
    for sh in shots:
        dur = sh["end"] - sh["at"]
        if dur <= MAX_SHOT:
            out.append(sh)
            continue
        parts = math.ceil(dur / MAX_SHOT)
        cands = [float(w["s"]) for w in tm.words if sh["at"] + 0.9 < float(w["s"]) < sh["end"] - 0.9]
        cuts: list[float] = []
        for k in range(1, parts):
            tgt = sh["at"] + dur * k / parts
            c = (min(cands, key=lambda s: abs(s - tgt)) - 0.1) if cands else tgt
            if (not cuts or c - cuts[-1] > 0.9) and c < sh["end"] - 0.9:
                cuts.append(round(c, 3))
        bounds = [sh["at"], *cuts, sh["end"]]
        for k in range(len(bounds) - 1):
            c = copy.deepcopy(sh)
            c["at"], c["end"] = bounds[k], bounds[k + 1]
            if k > 0:
                c["camera"] = _CYCLE[(len(out) + k) % len(_CYCLE)]
                c["framing"] = _NEXT_FRAME.get(sh["framing"], "medium") if k % 2 else sh["framing"]
                c["transition"] = "cut"
            lo, hi = c["at"], c["end"]
            c["callouts"] = [x for x in c["callouts"] if lo <= x["t"] < hi]
            c["fx"] = [x for x in c["fx"] if lo <= x["t"] < hi]
            props = []
            for p in c["props"]:                       # already shown earlier: visible from the start; shown later: appears on its word
                if p["t"] is None or p["t"] < lo:
                    props.append(dict(p, t=None))
                elif p["t"] < hi:
                    props.append(p)
            c["props"] = props
            for a in c["actors"]:
                state = {"mood": a["mood"], "gesture": a["gesture"], "prop": a["prop"]}
                for b in a["beats"]:
                    if b["t"] < lo:
                        if b["mood"]:
                            state["mood"] = b["mood"]
                        if b["gesture"]:
                            state["gesture"] = b["gesture"]
                        if b["prop"] is not None:
                            state["prop"] = b["prop"] or None
                a["beats"] = [b for b in a["beats"] if lo <= b["t"] < hi]
                a.update(state)
                if k > 0 and a["action"] not in ("sit", "jump"):
                    a["action"] = "stand"
            out.append(c)
    return out


def _inject_host(shots, appear: str, tm) -> None:
    if appear == "none" or not shots:
        return
    targets = [0] + ([len(shots) - 1] if appear == "first_last" and len(shots) > 1 else [])
    for idx in targets:
        sh = shots[idx]
        if any(a["who"] == "host" for a in sh["actors"]):
            continue
        used = {a["slot"] for a in sh["actors"]}
        slot = next((s for s in ("front_right", "front_far_right", "front_left", "front_far_left") if s not in used), "front_right")
        if idx == 0:
            t = round(sh["at"] + (sh["end"] - sh["at"]) * 0.55, 3)
            host = {"who": "host", "slot": slot, "mood": "happy", "action": "stand", "gesture": "wave", "prop": None, "looks_at": "",
                    "speech": tm.speech(sh["at"], sh["end"]), "beats": [{"t": t, "mood": "smug", "gesture": "point", "prop": None}]}
            if sh["framing"] in ("extreme_close", "close", "medium"):
                sh["framing"] = "wide"
        else:
            host = {"who": "host", "slot": slot, "mood": "smug", "action": "stand", "gesture": "hip", "prop": None, "looks_at": "",
                    "speech": [], "beats": []}
        sh["actors"].append(host)
        if sh["focus"] and "host" not in sh["focus"]:      # the camera must frame him too, or he is cut off at the edge
            sh["focus"].append("host")

def _set_punch(sh) -> None:
    if sh["camera"] != "punch_in":
        return
    times = [b["t"] for a in sh["actors"] for b in a["beats"]] + [c["t"] for c in sh["callouts"]] + [f["t"] for f in sh["fx"]]
    t = min(times) if times else sh["at"] + 0.55 * (sh["end"] - sh["at"])
    sh["punch"] = round(min(max(t, sh["at"] + 0.3), sh["end"] - 0.4), 3)


def build(story: Story, tm: Timing, year: int | None = None, appear: str = "first", era: dict | None = None, plain: bool = False,
          strict: bool = True, custom=None, need_props: bool = False):
    """-> (resolved story dict, problems the LLM must fix, warnings). plain=True drops scenery, objects and overlays (safe mode).
    custom = names of the objects designed for this video (propgen). need_props = the film must actually show things."""
    problems: list[str] = []
    warns: list[str] = []
    custom = set(custom or [])
    yr = story.year if 1000 <= story.year <= 2100 else (year or 1900)
    era_first = {**DEFAULT_ERA, **(era or {})}
    cast = _cast(story.cast, warns)
    ids = {c["id"] for c in cast} | {"host"}
    sets = _sets(story.sets, yr, era_first, warns, custom)
    if not sets:
        sets = [{"id": "main", "kind": "street", "mood": "day", "dress": []}]
        warns.append("no valid set: using a default street")
    kinds = {s["id"]: s["kind"] for s in sets}
    default_set = sets[0]["id"]
    n = len(tm.lines)
    cues: list[dict] = []

    staged = []
    for sp in story.shots:
        line = min(max(int(sp.line), 0), n - 1)
        at = tm.start(line) - 0.06
        t = tm.find(sp.word, tm.start(line), tm.end(line))
        if t is not None:
            at = max(at, t - 0.12)
        staged.append((max(0.0, at), sp))
    staged.sort(key=lambda x: x[0])
    kept = []
    for at, sp in staged:
        if kept and at - kept[-1][0] < 0.8:
            warns.append(f"shot at {at:.1f}s is too close to the previous one: dropped")
            continue
        kept.append((at, sp))
    if not kept:
        return {}, ["no shots: write at least one shot per script line"], warns
    kept[0] = (0.0, kept[0][1])

    shots = []
    for i, (at, sp) in enumerate(kept):
        end = kept[i + 1][0] if i + 1 < len(kept) else tm.dur
        sid = _ident(sp.set)
        if sid not in kinds:
            sid = default_set
        actors, used = [], set()
        for a in sp.actors:
            if len(actors) >= 4:
                break
            d = _actor(a, ids, kinds[sid], at, end, tm, cues, warns)
            if d and d["who"] not in used:
                used.add(d["who"])
                actors.append(d)
        shot = {"at": round(at, 3), "end": round(end, 3), "set": sid, "framing": _pick(sp.framing, FRAMINGS, "medium"),
                "camera": _pick(sp.camera, CAMERAS, "drift"), "focus": [f for f in (_ident(x) for x in sp.focus) if f in used][:3],
                "transition": _pick(sp.transition, TRANSITIONS, "cut") if i else "cut", "actors": actors, "callouts": [], "props": [], "fx": [],
                "note": str(sp.note)[:120]}
        if not plain:
            for c in sp.callouts[:2]:
                d = _callout(c, at, end, tm)
                if d:
                    shot["callouts"].append(d)
            for f in sp.fx[:2]:
                typ, t = _pick(f.type, FX_TYPES, ""), tm.find(f.word, at, end)
                if typ and t is not None:
                    shot["fx"].append({"t": round(t, 3), "type": typ})
            shot["props"] = _shot_props(sp.props, kinds[sid], at, end, tm, yr, era_first, custom, warns)
        shots.append(shot)

    if not cast:
        problems.append("cast is empty: write 2-6 characters")
    if strict and len(shots) < max(3, int(n * 0.5)):
        problems.append(f"only {len(shots)} shots for {n} script lines: write at least one shot per line")
    if len({s["camera"] for s in shots}) < min(4, len(shots)):
        problems.append("use at least 4 different camera moves")
    if len({s["framing"] for s in shots}) < min(3, len(shots)):
        problems.append("use at least 3 different framings")
    if sum(1 for s in shots if not s["actors"]) > len(shots) * 0.4:
        problems.append("too many shots without any character: put characters (with moods) in most shots")
    if sum(1 for s in shots if s["framing"] in ("close", "extreme_close")) > len(shots) * 0.45:
        problems.append("too many close-ups: use close/extreme_close for at most a quarter of the shots (reactions only); "
                        "show the objects and the place with medium, full and wide framings")
    if need_props and not plain:
        if sum(1 for s in shots if s["props"]) < len(shots) * 0.5:
            problems.append("most shots show nothing of the topic: add `props` (the objects, place, sign or crowd the narration talks about) "
                            "to at least half of the shots, revealed on the spoken word")
        used_names = {p["name"] for s in shots for p in s["props"]} | {d["item"] for st in sets for d in st["dress"]}
        if custom and not (used_names & custom):
            problems.append("none of the designed custom objects is used: place them with `props` or `dress` using their exact names")

    _vary(shots)
    shots = _split_long(shots, tm)
    _inject_host(shots, appear, tm)
    for i, sh in enumerate(shots):
        sh["id"] = f"S{i + 1:02d}"
        _set_punch(sh)
        cues.append({"t": round(sh["at"] + 0.04, 3), "type": "whoosh", "gain": 0.5})
    cues.sort(key=lambda c: c["t"])
    result = {"year": yr, "era": {"cars": yr >= era_first["car"], "poles": yr >= 1865, "lamps": yr >= era_first["lamp"]},
              "cast": cast, "sets": [dict(s, dress=[]) for s in sets] if plain else sets, "shots": shots, "cues": cues}
    return result, problems, warns


JS = """// generated by shorts_agent/director.py: do not edit, re-run the storyboard stage instead
import { buildFromStory } from './core/director.js';
const STORY = __STORY__;
const PROPS = __PROPS__;
export function buildShots(E) {
  return buildFromStory(E, STORY, PROPS);
}
"""


def to_js(story: dict, props: list | None = None) -> str:
    defs = {p["name"]: p for p in (props or [])}
    return JS.replace("__STORY__", json.dumps(story, ensure_ascii=False, separators=(",", ":"))).replace(
        "__PROPS__", json.dumps(defs, ensure_ascii=False, separators=(",", ":")))


def vocab_text() -> str:
    return "\n".join([
        "ALLOWED VALUES (anything else is replaced by a default):",
        "mood: " + ", ".join(MOODS),
        "pattern: " + ", ".join(PATTERNS) + " | hat: " + ", ".join(HATS) + " | neck: " + ", ".join(NECKS) + " | extra: " + ", ".join(EXTRAS),
        "set kind: " + ", ".join(SET_KINDS) + " | set mood: day, dusk",
        "open set = a sky and ground you colour yourself (use it for sports grounds, space, science): wall = top-of-sky hex, motif = horizon hex, "
        "floor = ground hex (\"\" = no ground, the people stand on a small platform), ceiling = hills hex or \"\", sign = \"stars\" for a night sky with stars",
        "built-in objects for `dress` and `props`: street = " + ", ".join(sorted(DRESS["street"])) + "; meadow = " + ", ".join(sorted(DRESS["meadow"]))
        + "; interior = " + ", ".join(sorted(DRESS["interior"])),
        "object text: poster lines separated by | (first line is the title, a line starting with ! is red); board = the sign text; signpost = place name; scale = pounds",
        "framing: " + ", ".join(FRAMINGS) + " | camera: " + ", ".join(CAMERAS),
        "slot: [front_|back_]far_left|left|center|right|far_right; street also boardwalk_left, boardwalk_right; "
        "interior also counter_clerk (behind the counter), counter_top (standing on it)",
        "action: " + ", ".join(ACTIONS) + " | gesture: " + ", ".join(GESTURES),
        "held props: " + ", ".join(HELD) + " (with text: book:RULES, paper:NEWS, sign:SALE, cash:3)",
        "transition: " + ", ".join(TRANSITIONS) + " | callout style: " + ", ".join(CALLOUT_STYLES) + " | fx: " + ", ".join(FX_TYPES),
        "sfx: " + ", ".join(SFX),
    ])


# ---------- a complete demo story for the engine's example narration (offline test, no LLM) ----------
def _look(body, pattern="plain", patCol="", hat="none", hatCol="", neck="none", neckCol="", extra=(), kid=False):
    return {"body": body, "pattern": pattern, "patCol": patCol, "hat": hat, "hatCol": hatCol, "neck": neck, "neckCol": neckCol,
            "extra": list(extra), "kid": kid}


def _d(item, x, z, scale=1, rot=0, color="", text=""):
    return {"item": item, "x": x, "z": z, "scale": scale, "rot": rot, "color": color, "text": text}


def _set(sid, kind, mood="day", wall="", motif="", floor="", ceiling="", sign="", dress=()):
    return {"id": sid, "kind": kind, "mood": mood, "wall": wall, "motif": motif, "floor": floor, "ceiling": ceiling, "sign": sign,
            "dress": list(dress)}


def _a(who, slot, mood="neutral", action="stand", gesture="none", prop="", looks_at="", talk=False, beats=()):
    return {"who": who, "slot": slot, "mood": mood, "action": action, "gesture": gesture, "prop": prop, "looks_at": looks_at,
            "talk": talk, "beats": [{"word": w, "mood": m, "gesture": g, "prop": "", "sfx": s} for w, m, g, s in beats]}


def _s(line, set_, framing, camera, focus, actors, word="", transition="cut", callouts=(), fx=(), note="", props=()):
    """props = (name, x, z, scale, word, text) tuples"""
    return {"line": line, "word": word, "set": set_, "framing": framing, "camera": camera, "focus": focus, "transition": transition,
            "actors": actors, "callouts": [{"text": t, "word": w, "style": s} for t, w, s in callouts],
            "props": [{"name": p[0], "x": p[1], "y": 0, "z": p[2], "scale": p[3], "rot": 0, "word": p[4], "text": p[5] if len(p) > 5 else ""} for p in props],
            "fx": [{"word": w, "type": t} for w, t in fx], "note": note}


DEMO = {
    "year": 1914,
    "cast": [
        {"id": "may", "look": _look("#7FC8E8", hat="bow", hatCol="#D8343F", neck="collar", kid=True)},
        {"id": "dad", "look": _look("#6FA35A", "overalls", "#3E5FA8", "boater", "#E8C77A", extra=["mustache"])},
        {"id": "clerk", "look": _look("#4FB3A9", "vest", "#2B5E73", "visor", "#2F8F5B", "collar", extra=["pencil"])},
        {"id": "grandma", "look": _look("#E58A6A", "apron", "#FFF4E0", "bun", "#D9D9E2", extra=["glasses", "blush"])},
    ],
    "sets": [
        _set("main", "street", dress=[_d("barrel", -3.5, -1), _d("crate", 3.6, -2)]),
        _set("home", "meadow", dress=[_d("house", -1, -12), _d("tree", 6, -8), _d("signpost", 3.5, -3, text="LEWISTON")]),
        _set("office", "interior", wall="#2F6B5A", motif="#3B7D69", ceiling="#5A3A2A", sign="PARCEL POST",
             dress=[_d("poster", -2.4, -3, text="NOTICE|!NO PEOPLE|MAY BE SENT|BY MAIL")]),
    ],
    "shots": [
        _s(0, "main", "wide", "crane_down", ["may", "dad"],
           [_a("dad", "left", "happy", gesture="present", talk=True), _a("may", "center", "happy", "walk_in", beats=[("mailed", "shock", "", "pop")])],
           callouts=[("IDAHO 1914", "idaho", "label")], note="hook: the family arrives", props=[("board", 3.0, -2.0, 1, "mailed", "MAIL A KID?")]),
        _s(1, "home", "wide", "push_in", ["grandma"], [_a("grandma", "center", "happy", gesture="wave")], note="grandma's house"),
        _s(2, "office", "close", "push_in", ["may"],
           [_a("may", "center", "proud", beats=[("stamps", "laugh", "", "stamp")]), _a("clerk", "right", "shock")],
           fx=[("stamps", "shake")], note="stamps on the coat"),
        _s(3, "main", "medium", "truck_left", ["dad"],
           [_a("dad", "center", "happy", "cross_left", prop="parcels", beats=[("packages", "proud", "", "plop")])], transition="punch",
           props=[("parcel", 1.6, 0.6, 1, "packages", ""), ("crowd", -2.6, -3, 1, "", "")]),
        _s(4, "home", "medium", "orbit_left", ["dad", "may"],
           [_a("dad", "left", "happy", looks_at="may", talk=True), _a("may", "right", "happy", "jump", looks_at="dad")]),
        _s(5, "home", "wide", "crane_up", ["may"], [_a("may", "center", "worried", gesture="point")],
           callouts=[("73 MILES", "miles", "pop")], note="signpost"),
        _s(6, "main", "close", "handheld", ["dad"], [_a("dad", "center", "worried", prop="ticket", beats=[("ticket", "worried", "", "gulp")])],
           transition="flash"),
        _s(7, "office", "wide", "drift", ["dad", "may", "clerk"],
           [_a("dad", "left", "happy", talk=True), _a("may", "center", "happy"), _a("clerk", "counter_clerk", "neutral")],
           callouts=[("53 CENTS", "post", "stamp")]),
    ],
}
EXAMPLE = {**DEMO, "shots": DEMO["shots"][:4]}