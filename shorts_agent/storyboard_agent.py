"""script.json + engine docs -> src/shots.js, validated by `capture.mjs check`, with a retry loop."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from .llm import generate_text
from .runner import SKILL_DIR

STYLE_DIR = SKILL_DIR / "styles" / "inside-out"
BANNED = ["fetch(", "XMLHttpRequest", "eval(", "new Function", "import(", "require(", "process.",
          "WebSocket", "document.", "window.", "localStorage", "Math.random", "Date.", "async ", "await "]

SYSTEM = """You are the shot-list author for the 'Inside Out' 2D short-video engine. You write exactly ONE file: src/shots.js.
Output ONLY one ```js code block with the complete file. No explanation.

Rules:
- Same structure as the example shots.js: imports ONLY from './core/lib.js', './core/timing.js', './core/kit.js' and ONLY names that really exist there. `export function buildShots()` returns { shots: S, cues: CUES }.
- One shot per script line (ids S01, S02, ...), each `at: cut(i)` with cut defined exactly as in the example.
- Anchor key moments with Wd('word', lineIndex): the word MUST be actually spoken in that line (lowercase, no punctuation; prefix match). Never use a word that is not in that line's text.
- draw(lt, d, t) is a pure function of time. No state kept between frames, no Math.random (use rnd(i) from lib), no Date, no async, no network, no DOM.
- Reuse the kit (K.man, K.room, K.xray, K.pill, K.tag, K.redX, K.warning, K.stopwatch, K.calendar, ...). For things the kit lacks (e.g. lungs, a balloon, a brain) define NEW local helper functions at the top of shots.js in the same flat style: flat fills from palette C, one darker shade, one light highlight, ink outlines only on graphics. Never edit kit.js.
- One visual mode per shot. X-ray means the WHOLE body is x-ray (K.man with xray: true) on K.xray(t) background. Cyan only for inside-body views, red only for danger, yellow is for highlights.
- Keep key action between y 250 and 1250 (captions cover y 1250-1550). Fill backgrounds past the edges (the camera zooms).
- Something must always be moving inside a shot. Each shot starts with cue(st, 'whoosh'); add 1-2 meaningful cues per shot, only using the allowed cue types from STYLE.md.
- Reveals (labels, X, warning) land on their spoken word. The last line: hero looks at the camera (the loop line).
- Accurate science, no gore, no injury on screen."""


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def build_context(project: Path) -> str:
    script = json.loads(read(project / "script.json"))
    lines = "\n".join(f'{i}: "{l["text"]}"' for i, l in enumerate(script["lines"]))
    return (
        f"=== STYLE.md ===\n{read(STYLE_DIR / 'STYLE.md')}\n\n"
        f"=== src/core/lib.js ===\n{read(project / 'src/core/lib.js')}\n\n"
        f"=== src/core/timing.js ===\n{read(project / 'src/core/timing.js')}\n\n"
        f"=== src/core/kit.js ===\n{read(project / 'src/core/kit.js')}\n\n"
        f"=== EXAMPLE src/shots.js (different topic: gum) ===\n{read(STYLE_DIR / 'example/src/shots.js')}\n\n"
        f"=== THIS VIDEO: title '{script['title']}', lines (index: spoken text) ===\n{lines}\n\n"
        "Write the complete src/shots.js for THIS video."
    )


def extract_js(raw: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", raw, re.S)
    return (m.group(1) if m else raw).strip() + "\n"


def static_check(code: str) -> list[str]:
    problems = [f"Forbidden token in code: {b!r}" for b in BANNED if b in code]
    if "export function buildShots" not in code:
        problems.append("Missing `export function buildShots()`.")
    if "return { shots: S, cues: CUES }" not in code:
        problems.append("Must end with `return { shots: S, cues: CUES };`.")
    return problems


def run_check(project: Path) -> tuple[bool, str]:
    p = subprocess.run(["node", "tools/capture.mjs", "check"], cwd=project,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout + "\n" + p.stderr).strip()
    return (p.returncode == 0 and "CHECK OK" in p.stdout), out


def build_shots(project: Path, max_tries: int = 5) -> None:
    base = build_context(project)
    target = project / "src" / "shots.js"
    prompt, last_code, problems = base, "", []
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 3 else "storyboard_hard"
        code = extract_js(generate_text(prompt, system=SYSTEM, task=task))
        problems = static_check(code)
        if not problems:
            target.write_text(code, encoding="utf-8")
            ok, out = run_check(project)
            print(f"[storyboard] attempt {attempt}: check {'OK' if ok else 'FAILED'}")
            if ok:
                return
            problems = [f"`node tools/capture.mjs check` failed. Output (tail):\n{out[-2500:]}"]
        else:
            print(f"[storyboard] attempt {attempt}: static problems {problems}")
        last_code = code
        prompt = (f"{base}\n\nYour previous shots.js:\n```js\n{last_code}\n```\n\n"
                  "It has these problems. Fix them and return the FULL corrected file:\n- " + "\n- ".join(problems))
    raise SystemExit("Storyboard failed after retries:\n- " + "\n- ".join(problems))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    a = ap.parse_args()
    build_shots(a.project.resolve())
    print("shots.js ready")