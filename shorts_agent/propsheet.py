"""A picture of every ready-made extra object (filmboard.EXTRA_PROPS) drawn by the film engine:  python -m shorts_agent.propsheet"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from PIL import Image, ImageDraw

from . import brand
from .config import PROJECTS_ROOT, SKILL_DIR, proc_flags, render_env
from .filmboard import EXTRA_PROPS


def main() -> None:
    ex = SKILL_DIR / "styles" / "film" / "example"
    project = PROJECTS_ROOT / "props-sheet"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ex, project)
    brand.write_js(project)
    names = list(EXTRA_PROPS)
    n = len(names)
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "lines.json").write_text(json.dumps({"duration": n, "lines": [{"i": 0, "text": "x", "start": 0, "end": n}]}), encoding="utf-8")
    (project / "data" / "words.json").write_text("[]", encoding="utf-8")
    (project / "script.json").write_text(json.dumps({"title": "props", "lines": [{"text": "x"}]}), encoding="utf-8")
    shots = [{"id": f"P{i}", "at": float(i), "end": float(i + 1), "set": "study", "framing": "panel", "camera": "static", "focus_x": 50, "transition": "cut",
              "effect": "", "fx": "", "note": nm, "actors": [], "props": [], "callouts": [], "panel": {"prop": nm, "s": 1.0}} for i, nm in enumerate(names)]
    story = {"title": "props", "meta": {}, "duration": float(n), "cast": {}, "sets": {"study": {"kind": "study", "time": "night", "dress": []}},
             "custom": EXTRA_PROPS, "shots": shots}
    (project / "data" / "story.json").write_text(json.dumps(story), encoding="utf-8")
    times = ",".join(f"{i + 0.5}" for i in range(n))
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/f", times], cwd=project, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **render_env(project=project)}, creationflags=proc_flags())
    if p.returncode != 0:
        raise SystemExit("render failed:\n" + (p.stdout + p.stderr)[-800:])
    cols, w, h = 4, 270, 480
    sheet = Image.new("RGB", (cols * w, -(-n // cols) * h), "black")
    d = ImageDraw.Draw(sheet)
    for i, nm in enumerate(names):
        f = project / "review" / "f" / f"t{i + 0.5:.2f}.jpg"
        x, y = (i % cols) * w, (i // cols) * h
        if f.exists():
            sheet.paste(Image.open(f).convert("RGB").resize((w, h)), (x, y))
        d.text((x + 8, y + 6), nm, fill="#FFFFFF")
    out = project / "review" / "props.jpg"
    sheet.save(out, quality=90)
    print("saved", out)
    if hasattr(os, "startfile"):
        os.startfile(out)


if __name__ == "__main__":
    main()