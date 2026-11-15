"""Tall Tale storyboard: designed props + story JSON (LLM) -> checked and time-resolved (director.py) -> src/shots.js,
then a vision reviewer looks at the picture sheet and asks for a rewrite if the film does not show its topic."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

from . import brand, niche, propgen, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, proc_flags, render_env
from .director import DEMO, EXAMPLE, Story, Timing, build, to_js, vocab_text
from .llm import BudgetExceeded, generate_structured

YEAR_RE = re.compile(r"\b(1[0-9]\d\d|20[0-2]\d)\b")

SYSTEM = """You direct a 40-50 second animated short in the 'Tall Tale' style: flat cartoon cut-out people living in a sunny 3D world.
You never write code. You return ONE story object that matches the JSON schema; the engine builds the scenes from it.

SHOW THE STORY (the most important rule): a viewer with the sound off must understand the topic from the pictures alone. In every shot put
on screen the objects, place or crowd that the line talks about: use `props` (reveal them on the spoken word with `word`) and the set's
`dress`. Use the CUSTOM OBJECTS designed for this topic (exact names) for the topic's own things, and the built-in objects for generic
scenery. `crowd` = a group of spectators reacting, `board` = a sign (put its words in `text`). The characters react to the objects
(looks_at, moods, gestures). Never leave a shot as people standing in an empty place.
The camera frames the people AND the objects of a shot together: put the topic's main object right beside the actors (x between 1.5 and 3,
z between -3 and 0.5, scale 1 or more), never behind them or far away. Use close/extreme_close for at most a quarter of the shots
(reactions only); show objects and places with medium, full and wide framings.
CAST (2-6 characters for THIS story): id (lowercase letters; never 'host', the channel host is added automatically) and a look:
body colour (hex), pattern, hat, neck item, extras, kid (true for children). One hat and one neck item each, bright colours,
clearly different from each other. Unused text fields are "".
SETS (1-3): kind street | interior | meadow | open, mood day | dusk. An interior also takes wall/motif/floor/ceiling (hex) and a short sign.
Pick the set that fits the story: street, interior or meadow. Use `open` only for a place that is none of these.
The stage centre is (0,0): x runs left to right (-14..14), z negative = farther from the camera (-24..3). Actors stand in |x|<3, |z|<2;
big scenery (a stadium, a barn) goes farther back (z -10..-16, scale 0.3-1). `props` fields: name, x, y (height above the ground,
0 normally), z, scale, rot (degrees), word (reveal word or ""), text.
SHOTS: at least one per script line, in order. A line longer than 3 s gets two shots (the second one has `word` = the first spoken word of
its second half; otherwise word is ""). Every shot: set, framing, camera, focus (ids that must be in frame), transition, actors, callouts, props, fx, note.
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


class ShotNote(BaseModel):
    id: str
    shows_topic: bool
    problem: str
    fix: str


class Relevance(BaseModel):
    score: int
    summary: str
    shots: list[ShotNote]


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


def topic_of(project: Path, script: dict) -> str:
    r = project / "research.json"
    return (json.loads(read(r)).get("topic") if r.exists() else "") or script["title"]


def overlay_dir(st: styles.Style) -> Path | None:
    for name in (st.overlay, st.niche, st.key):
        d = REPO / "overlay" / name if name else None
        if d and d.exists():
            return d
    return None


def sync_overlay(project: Path, st: styles.Style) -> None:
    """Re-copy our overlay files (director.js, hero.js, propkit.js...) into the project and regenerate brand.js."""
    ov = overlay_dir(st)
    if ov:
        shutil.copytree(ov, project, dirs_exist_ok=True)
    if st.use_brand:
        brand.write_js(project)


def run_check(project: Path) -> tuple[bool, str]:
    p = subprocess.run(["node", "tools/capture.mjs", "check"], cwd=project, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **render_env("preview")}, creationflags=proc_flags())
    return (p.returncode == 0 and "CHECK OK" in p.stdout), (p.stdout + "\n" + p.stderr).strip()


def build_prompt(project: Path, st: styles.Style, script: dict, tm: Timing, year: int | None, custom: dict) -> str:
    lines = "\n".join(f"{i}: [{l['start']:.2f}-{l['end']:.2f}s] {l['text']}" for i, l in enumerate(tm.lines))
    yr = f"STORY YEAR: {year}" if year else "STORY YEAR: unknown: choose the believable year in `year`"
    objs = "\n".join(f"- {n}: {d['desc']} (about {d['span']} m)" for n, d in custom.items()) or "(none: use the built-in objects)"
    return (f"{SYSTEM}\n{vocab_text()}\n\nSTYLE AND NICHE RULES:\n{st.board_rules}\n\n"
            f"CUSTOM OBJECTS designed for this topic (use these exact names in `props` and `dress`):\n{objs}\n\n"
            f"EXAMPLE of the output format (another story; do not copy it):\n{json.dumps(EXAMPLE, ensure_ascii=False)}\n\n"
            f"TOPIC: {topic_of(project, script)}\nTITLE: {script['title']}\n{yr}\nSCRIPT (index: [start-end] text):\n{lines}\n\n"
            "Write the story object for THIS script.")


def contact_sheet(project: Path, story: dict, out: Path) -> None:
    """One small frame from the late middle of every shot (props have appeared by then)."""
    from PIL import Image, ImageDraw
    shots = story["shots"][:36]
    times = [round(s["at"] + (s["end"] - s["at"]) * 0.7, 2) for s in shots]
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/s", ",".join(str(t) for t in times)], cwd=project, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env={**os.environ, **render_env("preview")}, creationflags=proc_flags())
    print((p.stdout + p.stderr)[-300:])
    if p.returncode != 0:
        raise RuntimeError("frames failed")
    cols, w, h = 6, 270, 480
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


def shot_text(tm: Timing, s: dict) -> str:
    return " ".join(w["w"] for w in tm.words if s["at"] - 0.05 <= float(w["s"]) < s["end"])[:160]


def relevance(project: Path, story: dict, tm: Timing, topic: str) -> Relevance | None:
    """A vision model looks at the picture sheet: does every shot SHOW what its words are about? None = the reviewer could not run."""
    try:
        path = project / "review" / "all.jpg"
        contact_sheet(project, story, path)
        listing = "\n".join(f"{s['id']}: \"{shot_text(tm, s)}\"" for s in story["shots"][:36])
        return generate_structured(
            f"The picture is a contact sheet of a short animated film about: {topic}. Tiles go left to right, top to bottom; each is labelled with its "
            f"shot id. The narration spoken during each shot:\n{listing}\n\nFor every shot say whether the picture SHOWS what the words are about "
            "(the object, place, event or sign), not just a person standing around. shows_topic=false when a viewer would not understand the words "
            "from the picture. For each false shot write the `problem` and a concrete `fix` (which object to show and where, which framing or set). "
            "`score` 1-10 = how well the whole film explains the topic visually.",
            Relevance, system="You are a strict film editor reviewing a storyboard sheet. Judge only what is visible.",
            temperature=0.0, task="vision", images=[path.read_bytes()])
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"[storyboard] relevance review skipped ({type(e).__name__}: {str(e)[:120]})")
        return None


def write_metrics(project: Path, d: dict, custom: dict, attempt: int, plain: bool, rv: Relevance | None) -> None:
    used = {p["name"] for s in d["shots"] for p in s["props"]} | {x["item"] for st in d["sets"] for x in st["dress"]}
    (project / "metrics.json").write_text(json.dumps({
        "shots": len(d["shots"]), "shots_with_props": sum(1 for s in d["shots"] if s["props"]), "custom_objects": len(custom),
        "custom_used": len(used & set(custom)), "rounds": attempt, "safe_mode": plain,
        "relevance": rv.score if rv else None, "relevance_bad_shots": sum(1 for n in rv.shots if not n.shows_topic) if rv else None}, indent=1), encoding="utf-8")


def build_shots(project: Path, max_tries: int = 3) -> None:
    st = styles.active()
    sync_overlay(project, st)
    tm = Timing.load(project)
    script = json.loads(read(project / "script.json"))
    year = story_year(project)
    topic = topic_of(project, script)
    appear = brand.appear() if st.use_brand else "none"
    era = era_props(st)
    logs = project / "logs"
    logs.mkdir(exist_ok=True)
    custom: dict = {}
    if os.getenv("PROPS_AGENT", "1") != "0":
        try:
            custom = propgen.design(project, st, script, topic, year)
        except BudgetExceeded:
            raise
        except Exception as e:
            print(f"[props] design failed ({type(e).__name__}: {str(e)[:200]}): continuing with the built-in objects only")
    base = build_prompt(project, st, script, tm, year, custom)
    review = os.getenv("RELEVANCE_CHECK", "1") != "0"
    prompt, problems, best = base, [], None
    for attempt in range(1, max_tries + 1):
        task = "storyboard" if attempt <= 2 else "storyboard_hard"
        story = generate_structured(prompt, Story, system="You output only the JSON story object.", temperature=0.6, task=task)
        (logs / f"story_attempt{attempt}.json").write_text(story.model_dump_json(indent=1), encoding="utf-8")
        data, problems, warns = build(story, tm, year, appear, era, custom=set(custom), need_props=True)
        for w in warns:
            print("   warning:", w)
        print(f"[storyboard] attempt {attempt} ({task}): {len(problems)} problem(s), {len(warns)} warning(s)")
        if problems:
            prompt = (f"{base}\n\nYour previous story object:\n{story.model_dump_json()}\n\n"
                      "It has these problems. Fix them and return the FULL corrected story object:\n- " + "\n- ".join(problems))
            continue
        ok, plain, d, out = False, False, data, ""
        for plain in ((False, True) if os.getenv("SAFE_MODE", "0") == "1" else (False,)): 
            d = data if not plain else build(story, tm, year, appear, era, plain=True, custom=set(custom))[0]
            (project / "src" / "shots.js").write_text(to_js(d, list(custom.values())), encoding="utf-8")
            ok, out = run_check(project)
            (logs / f"check_attempt{attempt}{'_plain' if plain else ''}.txt").write_text(out, encoding="utf-8")
            print(f"[storyboard] render check {'OK' if ok else 'FAILED'}{' (SAFE MODE: the film has no objects!)' if plain else ''}")
            if ok:
                break
            print("   ", out[-500:].replace("\n", "\n    "))
        if not ok:
            problems = [f"The engine could not draw your story. Output (tail):\n{out[-1500:]}"]
            prompt = (f"{base}\n\nYour previous story object:\n{story.model_dump_json()}\n\n"
                      "It has these problems. Fix them and return the FULL corrected story object:\n- " + "\n- ".join(problems))
            continue
        best = (to_js(d, list(custom.values())), d)
        (project / "story.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        write_metrics(project, d, custom, attempt, plain, None)
        if plain or not review:
            return
        rv = relevance(project, d, tm, topic)
        if rv is None:
            return
        write_metrics(project, d, custom, attempt, plain, rv)
        bad = [n for n in rv.shots if not n.shows_topic]
        print(f"[storyboard] relevance {rv.score}/10: {len(bad)} of {len(d['shots'])} shot(s) do not show the topic. {rv.summary[:160]}")
        if rv.score >= 7 or len(bad) < max(3, int(len(d["shots"]) * 0.3)) or attempt == max_tries:
            return
        notes = "\n".join(f"- {n.id}: {n.problem}. FIX: {n.fix}" for n in bad[:10])
        prompt = (f"{base}\n\nYour previous story object:\n{story.model_dump_json()}\n\nAn editor looked at the rendered picture sheet and says the film does "
                  f"not show its topic well ({rv.score}/10). {rv.summary}\nShots that do not show what the words are about:\n{notes}\n"
                  "Rewrite the FULL story object so that every shot shows its topic: bring the objects next to the actors, use medium/full/wide framings.")
    if best:                                                  # a later attempt failed: put the last good film back
        (project / "src" / "shots.js").write_text(best[0], encoding="utf-8")
        return
    raise RuntimeError("Storyboard failed after retries:\n- " + "\n- ".join(problems))


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