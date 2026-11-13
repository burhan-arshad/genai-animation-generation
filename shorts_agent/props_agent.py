"""Niche props agent: for niches with props.mode = "generate" the LLM designs this video's scenery objects
(stadium, bat, galaxy, brain...) as src/core/niche_props.js. The host (hero) stays the fixed brand character."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import styles
from .config import SKILL_DIR
from .llm import generate_text

BANNED = ["fetch(", "XMLHttpRequest", "eval(", "new Function", "import(", "require(", "process.",
          "WebSocket", "document.", "window.", "localStorage", "Math.random", "Date.", "async ", "await "]
FUNC_RE = re.compile(r"^export\s+function\s+(\w+)", re.M)
FROM_RE = re.compile(r"""from\s+['"]([^'"]+)['"]""")
ALLOWED_IMPORTS = {"./lib.js", "./kit.js"}
ALLOWED_SC = ("cloud", "smoke", "flame", "rain", "snow", "nightWash")   # generic effects of props.js that fit every niche
MIN_PROPS = 8

SYSTEM = """You are the art department of a 2D cut-paper short-video engine. You write exactly ONE file: src/core/niche_props.js
Output ONLY one ```js code block with the complete file. No explanation.

The file is the scenery library for THIS video's niche and topic, in the same cut-paper look as the reference src/core/props.js
(copy its conventions, NOT its objects). The channel host character is not your job: never draw the host.

File rules:
- Imports ONLY from './lib.js' and './kit.js', and only names that really exist in those files (see the sources below).
  Typical: `import { ctx, W, H, TAU, rnd, clamp, lerp } from './lib.js';` and `import { cut, P, P_rr, P_circ, P_poly } from './kit.js';`.
- Draw shapes with cut(pathFn, colour, { shadow, edge }) and P_rr / P_circ / P_poly so every shape gets the paper edge and soft shadow.
  Use ctx.save()/translate/scale/restore like the reference and leave ctx state (alpha, transform, line style) as you found it.
- Every prop is `export function name(x, y, s = 1, t = 0, o = {})`: x = horizontal centre, y = ground contact (bottom), s = scale,
  t = film time in seconds, o = options (colour, pose, variant...). Pure function: same arguments, same picture. No state, no Math.random
  (use rnd(i)), no Date, no async, no network, no DOM. No text or lettering unless `o.text` is passed.
- Also export `backdrop(t = 0, o = {})`: the full-frame background for this niche (field, starfield, room, sky...). It fills the whole frame
  including -300..W+300, supports o.variant 'a' | 'b' | 'c' (different time of day or mood) and, if the niche has a ground, puts the horizon
  around y 900-1100. The frame is 1080 x 1920.
- Also export `NC`, the colour palette of this niche (muted paper tones plus one accent), and use it everywhere.
- Write 10-16 props. Hand-held objects are about 150-250 px at s = 1, buildings, stadiums and planets 400-900 px. Every prop has at least
  5 shapes (body, shade, highlight, details) and the important ones move with t (flags sway, balls spin, stars twinkle, lights pulse).
  Silhouettes must be recognisable and correct for the topic (a bat looks like a bat). Keep each prop under about 60 shapes and loops under 80 iterations.
- People (players, fans, scientists...) only if the topic needs them: simple flat paper figures in the same style, clearly different from the
  channel host, with pose or colour through `o`.
- Accurate content, nothing graphic. No real logos, brands, flags, team kits or likenesses of real people."""

TAIL = "\n\nWrite the complete src/core/niche_props.js for THIS video."

HARNESS = """import * as NP from './core/niche_props.js';

export function buildShots() {
  const names = Object.keys(NP).filter((k) => typeof NP[k] === 'function' && k !== 'backdrop');
  const shot = { id: 'P01', at: 0, cam: [540, 900], note: 'props test sheet',
    draw(lt, d, t) {
      NP.backdrop(t, { variant: 'a' });
      names.forEach((n, i) => NP[n](140 + (i % 4) * 265, 520 + Math.floor(i / 4) * 340, 0.5, t, {}));
    } };
  return { shots: [shot], cues: [] };
}
"""


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else "(missing)"


def exports_of(path: Path) -> set[str]:
    """Names of the exported functions of a JS file (used to catch hallucinated NP.xxx calls)."""
    try:
        return set(FUNC_RE.findall(path.read_text(encoding="utf-8")))
    except OSError:
        return set()


def extract_js(raw: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", raw, re.S)
    return (m.group(1) if m else raw).strip() + "\n"


def static_check(code: str, st: styles.Style) -> list[str]:
    if len(code.strip()) < 600:
        return ["Your reply did not contain the complete file. Return the whole src/core/niche_props.js in ONE ```js code block, nothing else."]
    problems = [f"Forbidden token in code: {b!r}" for b in BANNED if b in code]
    for src in FROM_RE.findall(code):
        if src not in ALLOWED_IMPORTS:
            problems.append(f"Import from {src!r} is not allowed: import only from './lib.js' and './kit.js'.")
    names = set(FUNC_RE.findall(code))
    if "backdrop" not in names:
        problems.append("Missing `export function backdrop(t = 0, o = {})`.")
    n = len(names - {"backdrop"})
    if n < MIN_PROPS:
        problems.append(f"Only {n} props exported: write at least {MIN_PROPS} (`export function name(x, y, s = 1, t = 0, o = {{}})`).")
    missing = [r for r in st.props_required if r not in names]
    if missing:
        problems.append("Missing required props (use these exact export names): " + ", ".join(missing))
    return problems


def render_test(project: Path) -> tuple[bool, str]:
    """Draw every exported prop on one test shot: catches runtime errors and leaves a preview image."""
    (project / "src" / "shots.js").write_text(HARNESS, encoding="utf-8")
    for args in (("check",), ("frames", "review/props", "1.0")):
        p = subprocess.run(["node", "tools/capture.mjs", *args], cwd=project, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stdout + "\n" + p.stderr).strip()
        if p.returncode != 0 or (args[0] == "check" and "CHECK OK" not in p.stdout):
            return False, out
    try:
        imgs = [f for f in (project / "review").rglob("*.jpg") if f.name != "props_preview.jpg"]
        if imgs:
            shutil.copy(max(imgs, key=lambda f: f.stat().st_mtime), project / "review" / "props_preview.jpg")
    except OSError:
        pass
    return True, out


def topic_of(project: Path) -> str:
    r = project / "research.json"
    if r.exists():
        t = json.loads(read(r)).get("topic")
        if t:
            return t
    return json.loads(read(project / "script.json")).get("title", "")


def build_context(project: Path, st: styles.Style, topic: str) -> str:
    core = project / "src" / "core"
    sdir = SKILL_DIR / "styles" / (st.engine or st.key)
    script = json.loads(read(project / "script.json"))
    lines = "\n".join(f'{i}: "{l["text"]}"' for i, l in enumerate(script["lines"]))
    req = ", ".join(st.props_required) or "(none: choose them yourself)"
    return (f"=== STYLE.md ===\n{read(sdir / 'STYLE.md')}\n\n"
            f"=== src/core/lib.js ===\n{read(core / 'lib.js')}\n\n"
            f"=== src/core/kit.js ===\n{read(core / 'kit.js')}\n\n"
            f"=== REFERENCE src/core/props.js (another niche's scenery: copy the conventions, NOT the objects) ===\n{read(core / 'props.js')}\n\n"
            f"=== NICHE ===\n{st.props_theme}\n{st.props_note}\n\n"
            f"=== THIS VIDEO ===\ntopic: {topic}\ntitle: {script['title']}\nlines (index: spoken text):\n{lines}\n\n"
            f"REQUIRED exports (exact names, plus `backdrop` and `NC`): {req}. Add every other prop this story needs.{TAIL}")


def build_props(project: Path, force: bool = False, max_tries: int = 4) -> Path | None:
    st = styles.active()
    if st.props_mode != "generate":
        return None
    target = project / "src" / "core" / "niche_props.js"
    meta = project / "props_meta.json"
    topic = topic_of(project)
    sig = hashlib.sha1(json.dumps([st.key, topic, st.props_theme, list(st.props_required), st.props_note]).encode()).hexdigest()
    if not force and target.exists() and meta.exists():
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("sig") == sig:
                print("[props] cached: niche_props.js matches this topic and niche")
                return target
        except ValueError:
            pass
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    base = build_context(project, st, topic)
    system = SYSTEM + (("\n\nNICHE STYLE NOTE: " + st.props_note) if st.props_note else "")
    prompt, problems, code = base, [], ""
    for attempt in range(1, max_tries + 1):
        task = "props" if attempt <= 2 else "props_hard"
        raw = generate_text(prompt, system=system, task=task, max_output_tokens=32000)
        code = extract_js(raw)
        (logs / f"props_attempt{attempt}.js").write_text(code, encoding="utf-8")
        problems = static_check(code, st)
        if not problems:
            target.write_text(code, encoding="utf-8")
            ok, out = render_test(project)
            (logs / f"props_check{attempt}.txt").write_text(out, encoding="utf-8")
            print(f"[props] attempt {attempt} ({task}): test render {'OK' if ok else 'FAILED'}")
            if ok:
                meta.write_text(json.dumps({"sig": sig, "topic": topic, "niche": st.key,
                                            "props": sorted(exports_of(target))}, indent=2), encoding="utf-8")
                print("[props] props:", ", ".join(sorted(exports_of(target))))
                return target
            print("   ", out[-500:].replace("\n", "\n    "))
            problems = [f"The test render failed (`node tools/capture.mjs`). Output (tail):\n{out[-2500:]}"]
        else:
            print(f"[props] attempt {attempt} ({task}): static problems {problems}")
        prompt = (f"{base}\n\nYour previous niche_props.js:\n```js\n{code}\n```\n\n"
                  "It has these problems. Fix them and return the FULL corrected file:\n- " + "\n- ".join(problems))
    target.unlink(missing_ok=True)
    raise RuntimeError("Could not generate valid props:\n- " + "\n- ".join(problems))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate niche props for an existing project folder (test without a full run)")
    ap.add_argument("project", type=Path)
    ap.add_argument("--niche", "--style", dest="style", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.style:
        styles.set_active(a.style)
    out = build_props(a.project.resolve(), force=a.force)
    print("Wrote", out, "| preview:", a.project / "review" / "props_preview.jpg")