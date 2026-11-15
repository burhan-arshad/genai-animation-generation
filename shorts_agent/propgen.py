"""Prop designer: the LLM designs this video's objects as blueprints (parts: box, sphere, cylinder, slab...), checked in code,
previewed in 3D and reviewed by a vision model. Blueprints are plain data, never code: overlay/.../propkit.js builds them."""
from __future__ import annotations

import hashlib
import json
import os
import re
import copy
import math
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

from . import styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, proc_flags, render_env
from .director import BUILTIN_PROPS, _hex, _ident, _num
from .llm import generate_structured

VERSION = 1
SHAPES = ["box", "sphere", "cylinder", "cone", "torus", "slab", "lathe", "label"]


class Part(BaseModel):
    shape: str
    size: list[float]
    pos: list[float]
    rot: list[float]
    color: str
    text: str
    fg: str
    pts: list[list[float]]
    profile: list[list[float]]


class PropDef(BaseModel):
    name: str
    desc: str
    span: float
    parts: list[Part]


class PropSet(BaseModel):
    props: list[PropDef]


class Check(BaseModel):
    name: str
    ok: bool
    problem: str
    fix: str


class Review(BaseModel):
    items: list[Check]


def _p(shape, size, pos=(0, 0, 0), rot=(0, 0, 0), color="#B9B4A6", text="", fg="", pts=(), profile=()):
    return {"shape": shape, "size": list(size), "pos": list(pos), "rot": list(rot), "color": color, "text": text, "fg": fg,
            "pts": [list(x) for x in pts], "profile": [list(x) for x in profile]}


EXAMPLES = [
    {"name": "cricket_bat", "desc": "wooden cricket bat standing upright", "span": 1.0, "parts": [
        _p("slab", (0.045, 0, 0), color="#E8C888", pts=[(-0.055, 0), (0.055, 0), (0.062, 0.6), (-0.062, 0.6)]),
        _p("box", (0.13, 0.025, 0.05), (0, 0.012, 0), color="#C9A66B"),
        _p("cylinder", (0.017, 0.017, 0.34), (0, 0.77, 0), color="#B5372E"),
        _p("cylinder", (0.021, 0.021, 0.12), (0, 0.9, 0), color="#2E5A9E"),
        _p("box", (0.02, 0.5, 0.07), (0, 0.3, -0.03), color="#D9B87A")]},
    {"name": "stone_giant", "desc": "a huge stone man lying on his back", "span": 3.0, "parts": [
        _p("cylinder", (0.42, 0.38, 1.1), (0, 0.42, 0), (0, 0, 90), "#B9B4A6"),
        _p("sphere", (0.3, 0.32, 0.3), (-0.8, 0.5, 0), color="#C4BFB1"),
        _p("cone", (0.05, 0.14, 0), (-0.8, 0.5, 0.3), (90, 0, 0), "#B0AB9D"),
        _p("sphere", (0.04, 0.04, 0.02), (-0.88, 0.58, 0.27), color="#2A2A33"),
        _p("sphere", (0.04, 0.04, 0.02), (-0.72, 0.58, 0.27), color="#2A2A33"),
        _p("cylinder", (0.16, 0.13, 1.0), (1.05, 0.3, 0.17), (0, 0, 90), "#B9B4A6"),
        _p("cylinder", (0.16, 0.13, 1.0), (1.05, 0.3, -0.17), (0, 0, 90), "#B9B4A6"),
        _p("cylinder", (0.1, 0.09, 0.75), (-0.1, 0.45, 0.5), (0, 0, 90), "#C4BFB1"),
        _p("cylinder", (0.1, 0.09, 0.75), (-0.1, 0.45, -0.5), (0, 0, 90), "#C4BFB1")]},
]
def _ring(r0, r1, y, color):
    return _p("lathe", (1, 1, 1), color=color, profile=[(r0, y), (r1, y), (r1, y + 0.06), (r0, y + 0.06)])


def _stadium():
    parts = [
        _p("cylinder", (9, 9, 0.2), (0, 0.1, 0), color="#6DBB4A"),                              # the ground
        _p("box", (1.4, 0.03, 6.5), (0, 0.215, 0), color="#D9B87A"),                           # the pitch
        _p("box", (1.9, 0.035, 0.07), (0, 0.23, 3.0), color="#FFFFFF"),
        _p("box", (1.9, 0.035, 0.07), (0, 0.23, -3.0), color="#FFFFFF"),
        _p("torus", (8.6, 0.07, 0), (0, 0.26, 0), (90, 0, 0), "#FFFFFF"),                       # the boundary rope
        _p("lathe", (1, 1, 1), color="#C9C2B5", profile=[(9.2, 0), (9.2, 1.4), (10.4, 1.4), (10.4, 2.6), (11.6, 2.6), (11.6, 3.8), (12.8, 3.8), (12.8, 0)]),
        _ring(9.3, 10.35, 1.42, "#C8283A"), _ring(10.5, 11.55, 2.62, "#2E5A9E"), _ring(11.7, 12.75, 3.82, "#E2B33C"),   # seats
    ]
    for sx in (-1, 1):
        for sz in (-1, 1):                                                                       # four floodlight towers
            parts.append(_p("cylinder", (0.15, 0.2, 7), (sx * 10, 3.5, sz * 9), color="#8A8F9C"))
            parts.append(_p("box", (1.6, 0.9, 0.2), (sx * 10, 7.3, sz * 9), (0, math.degrees(math.atan2(-sx * 10, -sz * 9)), 0), "#FFF3C8"))
    parts += [_p("box", (4, 1.8, 0.4), (0, 5.2, -13.6), color="#26304A"),
              _p("label", (3.6, 1.3, 0), (0, 5.2, -13.38), color="#26304A", text="SCORE", fg="#FFD35A")]
    return {"name": "stadium", "desc": "a cricket stadium: oval green ground with a pitch, boundary rope, three-tier stands, floodlights and a scoreboard",
            "span": 26.0, "parts": parts}


# hand-made blueprints for objects the LLM draws badly; a niche that lists one in props.required gets it for free
def _ball():
    parts = [_p("sphere", (0.1, 0.1, 0.1), color="#C8283A")]
    for dy in (-0.014, 0, 0.014):                              # the white seam: three thin rings round the middle
        parts.append(_p("torus", (0.102, 0.006, 0), (0, dy, 0), (90, 0, 0), "#F4EBD6"))
    return {"name": "ball", "desc": "a red leather cricket ball with a white seam", "span": 0.5, "parts": parts}


LIBRARY = {"stadium": _stadium(), "ball": _ball()}

SYSTEM = """You are the prop designer of a 3D cartoon film (flat saturated colours, cut-out people, simple solid shapes).
You design objects as BLUEPRINTS: a list of parts made of primitive shapes. You never write code.
Units are metres. y is up, +x is right, +z points to the camera. Every part has: shape, size, pos, rot (degrees), color (hex),
and for label: text and fg; for slab: pts; for lathe: profile. Unused fields are "" or [].
Shapes (size = [a, b, c]):
- box [width, height, depth] | sphere [rx, ry, rz] (an ellipsoid) | cylinder [radius_top, radius_bottom, height] (axis = y; rot z=90 lays it along x)
- cone [radius, height, 0] | torus [major_radius, tube_radius, 0] (a ring standing in the xy plane)
- label [width, height, 0]: a flat sign showing `text` on a `color` background, `fg` = text colour (max 24 characters)
- slab [depth, 0, 0] + pts = [[x,y],...] outline (3-24 points): a flat extruded silhouette, good for blades, flags, roofs, wings
- lathe + profile = [[radius, y],...] (2-24 points): a solid of revolution, good for vases, bottles, bells, balls, trophies, bowls
RULES: 6-20 parts per object. The silhouette must be recognisable as the real thing from the side. 2-4 colours per object plus a darker
shade for details. `span` = longest side of the finished object in metres (a person is 1.75, a cricket bat 1.0, a house 6). The engine puts
the finished object on the ground and scales it to `span`. No real logos, flags or brands. Nothing graphic.
Two EXAMPLES of the format:
"""


def _vec(v, n, default, lo, hi):
    try:
        out = [max(lo, min(hi, float(x))) for x in list(v)[:n]]
    except (TypeError, ValueError):
        out = []
    return (out + list(default)[len(out):])[:n]


def clean_part(p):
    shape = str(p.shape).strip().lower()
    if shape not in SHAPES:
        return None
    part = {"shape": shape, "size": _vec(p.size, 3, [1, 1, 1], 0.005, 30), "pos": _vec(p.pos, 3, [0, 0, 0], -30, 30),
            "rot": _vec(p.rot, 3, [0, 0, 0], -360, 360), "color": _hex(p.color, "#B9B4A6"),
            "text": re.sub(r"[^A-Za-z0-9 !?.,&'$%:/-]", "", str(p.text))[:24].strip(), "fg": _hex(p.fg, "#1F1C33"), "pts": [], "profile": []}
    if shape == "slab":
        pts = [_vec(q, 2, [0, 0], -30, 30) for q in p.pts[:24]]
        if len(pts) < 3:
            return None
        part["pts"] = pts
    if shape == "lathe":
        prof = [_vec(q, 2, [0.1, 0], -30, 30) for q in p.profile[:24]]
        if len(prof) < 2:
            return None
        part["profile"] = [[max(0.001, r), y] for r, y in prof]
    if shape == "label" and not part["text"]:
        return None
    return part


def clean_props(items, problems: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for it in items[:12]:
        name = _ident(it.name)
        if not name or name in out:
            continue
        parts = [x for x in (clean_part(p) for p in it.parts[:36]) if x]
        if len(parts) < 4:
            problems.append(f"{it.name}: only {len(parts)} valid parts; use at least 4 (a recognisable silhouette needs detail)")
            continue
        out[name] = {"name": name, "desc": str(it.desc)[:90], "span": round(_num(it.span, 0.3, 12, 2.0), 2), "parts": parts}
    return out


def _context(topic, title, year, lines, st, lib) -> str:
    req = ", ".join(n for n in st.props_required if n.lower() not in lib) or "(none: choose them yourself)"
    have = ", ".join(BUILTIN_PROPS + [f"{n} ({d['desc'][:40]})" for n, d in lib.items()])
    return (f"TOPIC: {topic}\nTITLE: {title}\nYEAR: {year or 'unknown'}\nNICHE: {st.props_theme or 'general'}\n{st.props_note}\n"
            f"REQUIRED objects (use these exact names): {req}\n"
            f"ALREADY AVAILABLE, do not design them again: {have}\n\nSCRIPT:\n" + "\n".join(f"- {t}" for t in lines))


def design(project: Path, st: styles.Style, script: dict, topic: str, year: int | None) -> dict[str, dict]:
    """-> {name: blueprint}. Cached in project/props.json (same topic + niche = no new quota)."""
    lines = [l["text"] for l in script["lines"]]
    lib = {n.lower(): copy.deepcopy(LIBRARY[n.lower()]) for n in st.props_required if n.lower() in LIBRARY}
    sig = hashlib.sha1(json.dumps([VERSION, topic, st.key, st.props_theme, list(st.props_required), st.props_note, sorted(lib)]).encode()).hexdigest()
    cache = project / "props.json"
    if cache.exists():
        try:
            c = json.loads(cache.read_text(encoding="utf-8"))
            if c.get("sig") == sig:
                print(f"[props] cached: {len(c['props'])} object(s)")
                return {p["name"]: p for p in c["props"]}
        except (ValueError, KeyError):
            pass
    base = _context(topic, script["title"], year, lines, st, lib)
    defs = _design_once(base)
    if (defs or lib) and os.getenv("PROPS_CRITIC", "1") != "0":
        for rnd in (1, 2):
            sheet = render_sheet(project, {**defs, **lib})
            if sheet is None:
                print("[props] preview could not be rendered: keeping the designs unchecked")
                break
            bad = [c for c in _critic(sheet, {**defs, **lib}) if _ident(c.name) not in lib]
            print(f"[props] review {rnd}: {len(bad)} object(s) need work" + (": " + ", ".join(c.name for c in bad) if bad else ""))
            if not bad or rnd == 2:
                break
            ask = "\n".join(f"- {c.name}: {c.problem} FIX: {c.fix}\n  previous blueprint: {json.dumps(defs[_ident(c.name)])}" for c in bad)
            r = generate_structured(base + "\n\nThese objects were reviewed and need work. Return ONLY these objects, corrected:\n" + ask,
                                    PropSet, system=SYSTEM + json.dumps(EXAMPLES, ensure_ascii=False), temperature=0.6, task="props_hard")
            defs.update(clean_props(r.props, []))
    defs.update(lib)
    render_sheet(project, defs)                               # the final sheet is the one you see in the dashboard
    cache.write_text(json.dumps({"sig": sig, "props": list(defs.values())}, indent=1, ensure_ascii=False), encoding="utf-8")
    return defs


def _design_once(base: str) -> dict[str, dict]:
    ex = json.dumps(EXAMPLES, ensure_ascii=False)
    prompt = (base + "\n\nDesign 5-9 objects: everything the narration talks about that a viewer must SEE to understand the story "
              "(the main object, the place or container, the key tools, symbols and signs). Short snake_case names.")
    problems: list[str] = []
    for attempt in range(1, 4):
        r = generate_structured(prompt, PropSet, system=SYSTEM + ex, temperature=0.7, task="props" if attempt < 3 else "props_hard")
        problems = []
        defs = clean_props(r.props, problems)
        print(f"[props] attempt {attempt}: {len(defs)} object(s) ok, {len(problems)} problem(s)")
        if len(defs) >= 3:
            return defs
        prompt = base + "\n\nYour previous attempt had these problems:\n- " + "\n- ".join(problems or ["fewer than 3 usable objects"]) + "\nReturn all objects again, corrected."
    return {}


SHEET_JS = """import { camera } from './core/engine.js';
import * as WD from './core/world.js';
import { buildProp } from './core/propkit.js';
const DEFS = __DEFS__;
export function buildShots(E) {
  const M = WD.meadow(E, { fenceOn: false, flowers: false });
  const cam = camera(40);
  const objs = DEFS.map((d) => { const o = buildProp(d); if (o) { o.visible = false; M.scene.add(o); } return o; });
  const shots = DEFS.map((d, i) => ({ id: 'P' + i, at: i, note: d.name, draw(lt, dd, t, blit) {
    objs.forEach((o) => { if (o) o.visible = false; });
    const o = objs[i], s = d.span;
    if (o) { o.visible = true; o.rotation.y = -0.6; }
    cam.position.set(s * 0.9, s * 0.55 + 0.4, s * 1.7 + 0.8); cam.lookAt(0, s * 0.3, 0);
    E.render(M.scene, cam, { bloom: 0, aperture: 0, vignette: 0.05, focus: 3 });
    blit();
  } }));
  return { shots, cues: [] };
}
"""


def render_sheet(project: Path, defs: dict) -> bytes | None:
    """One 3D picture per object, tiled into project/review/props.jpg (cheap: the quality is low on purpose)."""
    from PIL import Image, ImageDraw
    names = list(defs)
    work = PROJECTS_ROOT / f"_props-{project.name}"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(SKILL_DIR / "styles" / "tall-tale" / "example", work)
    shutil.copytree(REPO / "overlay" / "tall-tale", work, dirs_exist_ok=True)
    (work / "data").mkdir(exist_ok=True)
    (work / "data" / "lines.json").write_text(json.dumps({"duration": len(names) + 1, "lines": [{"i": 0, "text": "x", "start": 0, "end": len(names) + 1}]}), encoding="utf-8")
    (work / "data" / "words.json").write_text("[]", encoding="utf-8")
    (work / "script.json").write_text(json.dumps({"title": "props", "lines": [{"text": "x"}]}), encoding="utf-8")
    (work / "src" / "shots.js").write_text(SHEET_JS.replace("__DEFS__", json.dumps(list(defs.values()))), encoding="utf-8")
    times = ",".join(f"{i + 0.5}" for i in range(len(names)))
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/f", times], cwd=work, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **render_env("draft")}, creationflags=proc_flags())
    if p.returncode != 0:
        print((p.stdout + p.stderr)[-400:])
        return None
    cols, w, h = 3, 300, 533
    sheet = Image.new("RGB", (cols * w, -(-len(names) // cols) * h), "black")
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        f = work / "review" / "f" / f"t{i + 0.5:.2f}.jpg"
        x, y = (i % cols) * w, (i // cols) * h
        if f.exists():
            sheet.paste(Image.open(f).convert("RGB").resize((w, h)), (x, y))
        d.text((x + 8, y + 6), name, fill="#FFFFFF")
    out = project / "review" / "props.jpg"
    out.parent.mkdir(exist_ok=True)
    sheet.save(out, quality=90)
    return out.read_bytes()


def _critic(sheet: bytes, defs: dict) -> list[Check]:
    listing = "; ".join(f"{n} = {d['desc']}" for n, d in defs.items())
    try:
        r = generate_structured(
            "The picture shows 3D props, one per tile (left to right, top to bottom), each labelled with its name: " + listing +
            ". For each prop say whether a viewer would recognise it as the thing described. ok=false if it looks like random blobs, has the wrong "
            "shape, floats apart or is mostly hidden. For every ok=false write the `problem` and a concrete `fix` (which parts to change, add or move).",
            Review, system="You are a strict but fair art director reviewing 3D prop renders. A simple object is ok if it is recognisable.",
            temperature=0.0, task="vision", images=[sheet])
    except Exception as e:                                   # the critic must never block the film
        print(f"[props] critic skipped ({type(e).__name__}: {str(e)[:120]})")
        return []
    return [c for c in r.items if not c.ok and _ident(c.name) in defs]

