"""Tall Tale storyboard: script + narration timing -> story JSON (LLM) -> checked and time-resolved (director.py) -> src/shots.js."""
from __future__ import annotations

import argparse
import json
import os
import time
import re
import shutil
import subprocess
from pathlib import Path

from . import brand, niche, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, proc_flags, render_env
from .director import DEMO, EXAMPLE, Story, Timing, build, to_js, vocab_text
from .llm import generate_structured

YEAR_RE = re.compile(r"\b(1[0-9]\d\d|20[0-2]\d)\b")

SYSTEM = """You direct a 40-50 second animated short in the 'Tall Tale' style: flat cartoon cut-out people living in a sunny 3D world.
You never write code. You return ONE story object that matches the JSON schema; the engine builds the scenes from it.

CAST (2-6 characters for THIS story): id (lowercase letters; never 'host', the channel host is added automatically) and a look:
body colour (hex), pattern, hat, neck item, extras, kid (true for children). One hat and one neck item each, bright colours,
clearly different from each other. Unused text fields are "".
SETS (1-3): kind street | interior | meadow, mood day | dusk. An interior also takes wall/motif/floor/ceiling (hex) and a short sign.
The stage centre is (0,0): x runs left to right (-14..14), z negative = farther from the camera (-24..3). The actors stand in
|x|<3, |z|<2: put `dress` items at the sides or behind them. An interior has a counter on its right and a window in the back wall.
SHOTS: at least one per script line, in order. A line longer than 3 s gets two shots (the second one has `word` = the first spoken word of
its second half; otherwise word is ""). Every shot: set, framing, camera, focus (ids that must be in frame), transition, actors, callouts, fx, note.
ACTORS in a shot: who, slot, mood, action, gesture, prop, looks_at (id or ""), talk (true while this character is the one speaking), and
beats = changes on a spoken word: {word, mood, gesture, prop, sfx} (unused fields ""). `word` must be a word that is really spoken in
that shot's lines, lowercase, copied from the script. prop "none" puts the held prop down.
DIRECTION RULES:
- No two neighbouring shots with the same set + framing + camera move. Use at least 4 different moves and 3 framings.
  crane_down to open, push_in on big moments, punch_in on the reveal word, handheld for panic, orbit/truck for talking scenes.
- Open with a wide or establishing shot of the place (the host appears by himself). Finish on a reaction close-up or a punchline gag.
- Faces act: change mood on every beat (shock on the reveal, smug when someone is clever, worried for trouble, laugh for the payoff).
- Use `callouts` for years, numbers, names and signs ("IDAHO 1914", "73 MILES", "NO PEOPLE"): the narration spells numbers out, the callout
  shows them as digits. style: label (place/date tag), pop (big word), stamp (rubber stamp). At most two per shot, 26 characters.
- Put sfx on beats (pop, boing, stamp, ding, thud, slam, plop, zip, sparkle, gulp, chirp, tock) and `shake`/`flash` fx on impacts.
- Everything must belong to the story's time and place. Nothing graphic.
"""


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def era_props(st: styles.Style) -> dict:
    """prop name -> first year it may appear (from the niche pack; {} when the style has no niche)."""
    if not st.niche:
        return {}
    return niche.load(st.niche).get("storyboard", {}).get("era", {}).get("props", {}) or {}


def story_year(project: Path) -> int | None:
    texts = []
    r = project / "research.json"
    if r.exists():
        texts.append(json.loads(read(r)).get("topic", ""))
    texts.append(json.loads(read(project / "script.json")).get("title", ""))
    for t in texts:
        m = YEAR_RE.search(t)
        if m:
            return int(m.group(1))
    return None


def overlay_dir(st: styles.Style) -> Path | None:
    for name in (st.overlay, st.niche, st.key):
        d = REPO / "overlay" / name if name else None
        if d and d.exists():
            return d
    return None


def sync_overlay(project: Path, st: styles.Style) -> None:
    """Re-copy our overlay files (director.js...) into the project and regenerate brand.js, so edits apply to old projects too."""
    ov = overlay_dir(st)
    if ov:
        shutil.copytree(ov, project, dirs_exist_ok=True)
    if st.use_brand:
        brand.write_js(project)


def run_check(project: Path) -> tuple[bool, str]:
    p = subprocess.run(["node", "tools/capture.mjs", "check"], cwd=project, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **render_env("preview")}, creationflags=proc_flags())
    return (p.returncode == 0 and "CHECK OK" in p.stdout), (p.stdout + "\n" + p.stderr).strip()

def build_prompt(project: Path, st: styles.Style, script: dict, tm: Timing, year: int | None) -> str:
    r = project / "research.json"
    topic = json.loads(read(r)).get("topic", "") if r.exists() else script["title"]
    lines = "\n".join(f"{i}: [{l['start']:.2f}-{l['end']:.2f}s] {l['text']}" for i, l in enumerate(tm.lines))
    yr = f"STORY YEAR: {year}" if year else "STORY YEAR: unknown: choose the believable year in `year`"
    return (f"{SYSTEM}\n{vocab_text()}\n\nSTYLE AND NICHE RULES:\n{st.board_rules}\n\n"
            f"EXAMPLE of the output format (another story; do not copy it):\n{json.dumps(EXAMPLE, ensure_ascii=False)}\n\n"
            f"TOPIC: {topic}\nTITLE: {script['title']}\n{yr}\nSCRIPT (index: [start-end] text):\n{lines}\n\nWrite the story object for THIS script.")


def build_shots(project: Path, max_tries: int = 3) -> None:
    st = styles.active()
    sync_overlay(project, st)
    tm = Timing.load(project)
    script = json.loads(read(project / "script.json"))
    year = story_year(project)
    appear = brand.appear() if st.use_brand else "none"
    era = era_props(st)
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    base = build_prompt(project, st, script, tm, year)
    prompt, problems = base, []
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 2 else "storyboard_hard"
        story = generate_structured(prompt, Story, system="You output only the JSON story object.", temperature=0.6, task=task)
        (logs / f"story_attempt{attempt}.json").write_text(story.model_dump_json(indent=1), encoding="utf-8")
        data, problems, warns = build(story, tm, year, appear, era)
        for w in warns:
            print("   warning:", w)
        print(f"[storyboard] attempt {attempt} ({task}): {len(problems)} problem(s), {len(warns)} warning(s)")
        if not problems:
            for plain in (False, True):                        # the second pass is the safe mode: no scenery items, no overlays
                d = data if not plain else build(story, tm, year, appear, era, plain=True)[0]
                (project / "src" / "shots.js").write_text(to_js(d), encoding="utf-8")
                ok, out = run_check(project)
                (logs / f"check_attempt{attempt}{'_plain' if plain else ''}.txt").write_text(out, encoding="utf-8")
                print(f"[storyboard] render check {'OK' if ok else 'FAILED'}{' (safe mode)' if plain else ''}")
                if ok:
                    (project / "story.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
                    return
                print("   ", out[-500:].replace("\n", "\n    "))
            problems = [f"The engine could not draw your story. Output (tail):\n{out[-1500:]}"]
        prompt = (f"{base}\n\nYour previous story object:\n{story.model_dump_json()}\n\n"
                  "It has these problems. Fix them and return the FULL corrected story object:\n- " + "\n- ".join(problems))
    raise RuntimeError("Storyboard failed after retries:\n- " + "\n- ".join(problems))


def contact_sheet(project: Path, story: dict, out: Path) -> None:
    """One small frame from the middle of every shot (about 11 frames instead of 50)."""
    from PIL import Image, ImageDraw
    shots = story["shots"][:30]
    times = [round((s["at"] + s["end"]) / 2, 2) for s in shots]
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/s", ",".join(str(t) for t in times)], cwd=project, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env={**os.environ, **render_env("preview")}, creationflags=proc_flags())
    print((p.stdout + p.stderr)[-300:])
    if p.returncode != 0:
        raise RuntimeError("frames failed")
    cols, w, h = 6, 216, 384
    sheet = Image.new("RGB", (cols * w, -(-len(times) // cols) * h), "black")
    d = ImageDraw.Draw(sheet)
    for i, (t, s) in enumerate(zip(times, shots)):
        x, y = (i % cols) * w, (i // cols) * h
        f = project / "review" / "s" / f"t{t:.2f}.jpg"
        if f.exists():
            sheet.paste(Image.open(f).convert("RGB").resize((w, h)), (x, y))
        d.text((x + 6, y + 4), f"{s['id']} {t:.1f}s {s['camera']}", fill="#FFFFFF")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)


def demo() -> None:
    """Offline test, no LLM: the demo story on a copy of the engine's example narration, then a contact sheet."""
    t0 = time.time()
    st = styles.active()
    project = PROJECTS_ROOT / "demo-tall-tale"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "tall-tale" / "example", project)
    sync_overlay(project, st)
    tm = Timing.load(project)
    data, problems, warns = build(Story.model_validate(DEMO), tm, 1914, brand.appear() if st.use_brand else "none", era_props(st), strict=False)
    print("problems:", problems or "none")
    for w in warns:
        print("warning:", w)
    (project / "src" / "shots.js").write_text(to_js(data), encoding="utf-8")
    ok, out = run_check(project)
    print(out[-400:])
    print(f"[demo] check {'OK' if ok else 'FAILED'} after {time.time() - t0:.0f} s")
    if ok:
        contact_sheet(project, data, project / "review" / "all.jpg")
        print(f"[demo] done in {time.time() - t0:.0f} s: {project / 'review' / 'all.jpg'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path, nargs="?")
    ap.add_argument("--demo", action="store_true", help="offline test without the LLM")
    ap.add_argument("--style", "--niche", dest="style", default=None)
    a = ap.parse_args()
    if a.style:
        styles.set_active(a.style)
    if a.demo:
        demo()
    elif a.project:
        build_shots(a.project.resolve())
        print("shots.js ready")
    else:
        ap.error("give a project folder or --demo")