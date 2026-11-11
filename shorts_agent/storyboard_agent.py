"""script.json + engine docs -> src/shots.js, validated by `capture.mjs check`. The host is injected by code, not written by the LLM."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import brand, llm, styles
from .config import REPO, SKILL_DIR
from .llm import generate_text

BANNED = ["fetch(", "XMLHttpRequest", "eval(", "new Function", "import(", "require(", "process.",
          "WebSocket", "document.", "window.", "localStorage", "Math.random", "Date.", "async ", "await "]
RETURN_RE = re.compile(r"return\s*\{\s*shots\s*:\s*(\w+)\s*,\s*cues\s*:\s*(\w+)\s*\}")
EXPORT_RE = re.compile(r"export\s+(?:function|const)\s+buildShots")
PROPS_RE = re.compile(r"import\s*\*\s*as\s+(\w+)\s+from\s+['\"]\./core/props\.js['\"]")

COMMON = """You are the shot-list author for a 2D short-video engine. You write exactly ONE file: src/shots.js.
Output ONLY one ```js code block with the complete file. No explanation.

Rules:
- Same structure as the example shots.js: imports ONLY from './core/lib.js', './core/timing.js', './core/kit.js' and, when the style rules
  say so, './core/props.js' imported EXACTLY as `import * as SC from './core/props.js';` (scenery is always `SC`). Use ONLY names that
  really exist in those files. `export function buildShots()` builds the shot list and cue list like the example and ends with
  `return { shots: S, cues: CUES };`. Inside buildShots, `S` is the array of shots and `CUES` the array of cues (as in the example):
  never use `S` or any variable named like an import for anything else; `cut` is defined exactly as in the example.
- `lt`, `d` and `t` exist ONLY inside a shot's draw(lt, d, t) function: never use them anywhere else.
- One shot per script line (ids S01, S02, ...), each `at: cut(i)`. If a line lasts longer than about 3.2 s, split it into TWO shots
  (S03a, S03b); the second starts at Wd('some middle word', line) minus 0.08.
- Anchor key moments with Wd('word', lineIndex): the word MUST be actually spoken in that line (lowercase, no punctuation).
- draw(lt, d, t) is a pure function of time: no state between frames, no Math.random (use rnd(i) from lib), no Date, no async,
  no network, no DOM.
- Richness: every shot has at least 4 visible layers (background, main subject, a secondary detail, a label or accent) and at
  least 2 things moving at different speeds. Reveals (labels, marks, ribbons) land on their spoken word.
- Define NEW local helper functions at the top of shots.js only for things the libraries lack. Never edit kit.js or props.js.
- Each shot starts with a whoosh cue; add 1-2 meaningful cues per shot, only cue types that appear in the example or STYLE.md.
- Accurate content, nothing graphic."""

TAIL = "\n\nWrite the complete src/shots.js for THIS video."


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def sync_overlay(project: Path, st: styles.Style) -> None:
    """Re-copy our overlay files (hero, props, host...) into the project and regenerate brand.js, so edits apply to old projects too."""
    ov = REPO / "overlay" / st.key
    if ov.exists():
        shutil.copytree(ov, project, dirs_exist_ok=True)
    if st.use_brand:
        brand.write_js(project)


def build_context(project: Path) -> str:
    st = styles.active()
    sdir = SKILL_DIR / "styles" / (st.engine or st.key)
    script = json.loads(read(project / "script.json"))
    lines = "\n".join(f'{i}: "{l["text"]}"' for i, l in enumerate(script["lines"]))
    extra = f"=== src/core/props.js (scenery library, imported as SC) ===\n{read(project / 'src/core/props.js')}\n\n" if st.hero else ""
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


def inject_host(code: str) -> str:
    """Wrap the returned shot list so the engine draws the host on the first (and optionally last) shot."""
    if "core/host.js" in code:
        return code
    return "import * as HOST from './core/host.js';\n" + RETURN_RE.sub(
        r"return { shots: HOST.withHost(\1), cues: \2 }", code, count=1)


def static_check(code: str, st: styles.Style, nlines: int) -> list[str]:
    if len(code.strip()) < 400:
        return ["Your reply did not contain the complete file. Return the whole src/shots.js in ONE ```js code block, nothing else."]
    problems = [f"Forbidden token in code: {b!r}" for b in BANNED if b in code]
    if not EXPORT_RE.search(code):
        problems.append("Missing `export function buildShots()`.")
    if not RETURN_RE.search(code):
        problems.append("buildShots must end with `return { shots: S, cues: CUES };` (variable names as in the example).")
    if st.hero:
        if "core/hero.js" in code or "core/host.js" in code or "H.hero(" in code:
            problems.append("Do not import or draw the host: the engine adds him automatically. Remove hero.js/host.js/H.hero.")
        m = PROPS_RE.search(code)
        if not m:
            problems.append("Import the scenery library exactly as `import * as SC from './core/props.js';`.")
        else:
            alias = m.group(1)
            if re.search(rf"\b(?:const|let|var)\s+{alias}\b", code):
                problems.append(f"Name collision: `{alias}` is the scenery import but is also declared as a variable (the shots array "
                                f"`S` shadows it). Import scenery as `SC` and keep `const S = [], CUES = []` for the shots.")
            calls = len(re.findall(rf"\b{alias}\.[A-Za-z]+\(", code))
            if calls < 2 * nlines:
                problems.append(f"Scenes are too sparse ({calls} scenery calls for {nlines} lines): use SC.stage in every scene and "
                                "add houses, trees, crowds, vehicles, fire, smoke or weather so each shot shows the event.")
    return problems


def run_check(project: Path) -> tuple[bool, str]:
    p = subprocess.run(["node", "tools/capture.mjs", "check"], cwd=project,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.returncode == 0 and "CHECK OK" in p.stdout), (p.stdout + "\n" + p.stderr).strip()


def build_shots(project: Path, max_tries: int = 5) -> None:
    st = styles.active()
    sync_overlay(project, st)
    nlines = len(json.loads(read(project / "script.json"))["lines"])
    system = COMMON + f"\n\nSTYLE-SPECIFIC RULES ({st.key}):\n" + st.board_rules
    base = build_context(project)
    target = project / "src" / "shots.js"
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    prompt, problems = base, []
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 3 else "storyboard_hard"
        raw = generate_text(prompt, system=system, task=task, max_output_tokens=32000)
        code = extract_js(raw)
        via = f"via {llm.LAST.get('model', '?')}, finish={llm.LAST.get('finish', '?')}"
        (logs / f"shots_attempt{attempt}.js").write_text(code, encoding="utf-8")
        problems = static_check(code, st, nlines)
        if not problems:
            target.write_text(inject_host(code) if st.hero else code, encoding="utf-8")
            ok, out = run_check(project)
            (logs / f"check_attempt{attempt}.txt").write_text(out, encoding="utf-8")
            print(f"[storyboard] attempt {attempt} ({task}, {via}): check {'OK' if ok else 'FAILED'}")
            if ok:
                return
            print("   ", out[-500:].replace("\n", "\n    "))
            problems = [f"`node tools/capture.mjs check` failed. Output (tail):\n{out[-2500:]}"]
        else:
            print(f"[storyboard] attempt {attempt} ({task}, {via}): static problems {problems}")
            if len(code.strip()) < 400:
                print("    raw reply starts with:", raw[:300].replace("\n", " "))
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