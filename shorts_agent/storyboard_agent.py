"""script.json + engine docs -> src/shots.js, validated by `capture.mjs check`, with retries, logs and model escalation."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from . import brand, styles
from .config import SKILL_DIR
from .llm import generate_text

BANNED = ["fetch(", "XMLHttpRequest", "eval(", "new Function", "import(", "require(", "process.",
          "WebSocket", "document.", "window.", "localStorage", "Math.random", "Date.", "async ", "await "]
RETURN_RE = re.compile(r"return\s*\{\s*shots\s*:\s*\w+\s*,\s*cues\s*:\s*\w+\s*\}")

COMMON = """You are the shot-list author for a 2D short-video engine. You write exactly ONE file: src/shots.js.
Output ONLY one ```js code block with the complete file. No explanation.

Rules:
- Same structure as the example shots.js: imports ONLY from './core/lib.js', './core/timing.js', './core/kit.js' (plus './core/hero.js'
  and './core/props.js' when the style rules say so) and ONLY names that really exist there. `export function buildShots()` builds the
  shot list and cue list exactly like the example and ends with `return { shots: S, cues: CUES };` (use the same variable names as the
  example); `cut` is defined exactly as in the example.
- One shot per script line (ids S01, S02, ...), each `at: cut(i)`. If a line lasts longer than about 3.2 s, split it into TWO shots
  (S03a, S03b); the second starts at Wd('some middle word', line) minus 0.08.
- Anchor key moments with Wd('word', lineIndex): the word MUST be actually spoken in that line (lowercase, no punctuation).
- draw(lt, d, t) is a pure function of time: no state between frames, no Math.random (use rnd(i) from lib), no Date, no async,
  no network, no DOM.
- Richness: every shot has at least 4 visible layers (background, main subject, a secondary detail, a label or accent) and at
  least 2 things moving at different speeds. Reveals (labels, marks, ribbons) land on their spoken word.
- Define NEW local helper functions at the top of shots.js only for things the libraries lack. Never edit kit.js, hero.js or props.js.
- Each shot starts with a whoosh cue; add 1-2 meaningful cues per shot, only cue types that appear in the example or STYLE.md.
- Accurate content, nothing graphic."""

TAIL = "\n\nWrite the complete src/shots.js for THIS video."


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def build_context(project: Path) -> str:
    st = styles.active()
    sdir = SKILL_DIR / "styles" / (st.engine or st.key)
    script = json.loads(read(project / "script.json"))
    lines = "\n".join(f'{i}: "{l["text"]}"' for i, l in enumerate(script["lines"]))
    extra = ""
    if st.hero:  # the host API is fully described in the style rules; only the scenery source is needed
        extra = f"=== src/core/props.js (scenery library) ===\n{read(project / 'src/core/props.js')}\n\n"
    return (
        f"=== STYLE.md ===\n{read(sdir / 'STYLE.md')}\n\n"
        f"=== src/core/lib.js ===\n{read(project / 'src/core/lib.js')}\n\n"
        f"=== src/core/timing.js ===\n{read(project / 'src/core/timing.js')}\n\n"
        f"=== src/core/kit.js ===\n{read(project / 'src/core/kit.js')}\n\n"
        f"{extra}"
        f"=== EXAMPLE src/shots.js (different topic; follow its structure, not its look) ===\n{read(sdir / 'example/src/shots.js')}\n\n"
        f"=== THIS VIDEO: title '{script['title']}', lines (index: spoken text) ===\n{lines}{TAIL}")


def extract_js(raw: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", raw, re.S)
    return (m.group(1) if m else raw).strip() + "\n"


def static_check(code: str, st: styles.Style, nlines: int) -> list[str]:
    problems = [f"Forbidden token in code: {b!r}" for b in BANNED if b in code]
    if "export function buildShots" not in code:
        problems.append("Missing `export function buildShots()`.")
    if not RETURN_RE.search(code):
        problems.append("buildShots must end with `return { shots: S, cues: CUES };` (variable names as in the example).")
    if st.hero:
        want = {"first": 1, "first_last": 2, "none": 0}[brand.appear()]
        got = code.count("H.hero(")
        if want == 0 and "core/hero.js" in code:
            problems.append("Do not import hero.js: no host character in this channel setting.")
        if want and "core/hero.js" not in code:
            problems.append("Import the host: `import * as H from './core/hero.js';`.")
        if got != want:
            problems.append(f"H.hero( must appear exactly {want} time(s) in the file (found {got}): the host is only in "
                            "the shots the style rules name, never in the story scenes.")
        if "core/props.js" not in code:
            problems.append("Import the scenery library: `import * as S from './core/props.js';`.")
        calls = len(re.findall(r"\bS\.[A-Za-z]+\(", code))
        if calls < 2 * nlines:
            problems.append(f"Scenes are too sparse ({calls} scenery calls for {nlines} lines): use S.stage in every scene and "
                            "add houses, trees, crowds, vehicles, fire, smoke or weather so each shot shows the event.")
    return problems


def run_check(project: Path) -> tuple[bool, str]:
    p = subprocess.run(["node", "tools/capture.mjs", "check"], cwd=project,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.returncode == 0 and "CHECK OK" in p.stdout), (p.stdout + "\n" + p.stderr).strip()


def build_shots(project: Path, max_tries: int = 5) -> None:
    st = styles.active()
    if st.use_brand:
        brand.write_js(project)          # pick up any brand.json change
    nlines = len(json.loads(read(project / "script.json"))["lines"])
    system = COMMON + f"\n\nSTYLE-SPECIFIC RULES ({st.key}):\n" + st.board_rules
    base = build_context(project)
    target = project / "src" / "shots.js"
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    prompt, problems = base, []
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 3 else "storyboard_hard"
        code = extract_js(generate_text(prompt, system=system, task=task))
        (logs / f"shots_attempt{attempt}.js").write_text(code, encoding="utf-8")
        problems = static_check(code, st, nlines)
        if not problems:
            target.write_text(code, encoding="utf-8")
            ok, out = run_check(project)
            (logs / f"check_attempt{attempt}.txt").write_text(out, encoding="utf-8")
            print(f"[storyboard] attempt {attempt} ({task}): check {'OK' if ok else 'FAILED'}")
            if ok:
                return
            print("   ", out[-500:].replace("\n", "\n    "))
            problems = [f"`node tools/capture.mjs check` failed. Output (tail):\n{out[-2500:]}"]
        else:
            print(f"[storyboard] attempt {attempt} ({task}): static problems {problems}")
        prompt = (f"{base}\n\nYour previous shots.js:\n```js\n{code}\n```\n\n"
                  "It has these problems. Fix them and return the FULL corrected file:\n- " + "\n- ".join(problems))
    raise SystemExit("Storyboard failed after retries:\n- " + "\n- ".join(problems))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--style", default=None)
    a = ap.parse_args()
    if a.style:
        styles.set_active(a.style)
    build_shots(a.project.resolve())
    print("shots.js ready")