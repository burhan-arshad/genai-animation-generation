"""Vision QA: a multimodal model looks at a contact sheet of the finished video and reports visual problems."""
from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import BaseModel

from . import brand
from .llm import generate_structured

N = 8


class Issue(BaseModel):
    frame: int
    severity: str          # 'blocker' | 'minor'
    problem: str


class Report(BaseModel):
    score: int
    issues: list[Issue]
    summary: str


SYSTEM = """You are a strict visual QA reviewer for 40-second animated history Shorts (flat cut-paper style, vertical 9:16).
You see ONE contact sheet: 8 numbered frames sampled evenly over the video (frame 1 = the start). Check:
1. A human host character may appear ONLY in {host_rule}. A host standing beside the scene in any other frame is a blocker.
2. Every frame after the intro must show a full scene of the event (buildings, trees, people, vehicles, fire, weather). Mostly empty sky or empty ground is a blocker.
3. Era: nothing that did not exist in the story year (cars, trains, factories, street lamps, modern clothes, skyscrapers). Report only what you can clearly identify.
4. Important objects must not overlap in a confusing way or be cut off; the caption strip at the bottom must not hide the main action.
5. Crowds in street scenes are ordinary people, not kings or queens.
Be conservative: if unsure, do not report. `score` is 1-10 overall polish. `severity` is 'blocker' only for clear violations of rules 1-3."""


def _duration(video: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    return float(p.stdout.strip() or 0)


def frames(video: Path, out: Path) -> list[Path]:
    dur = _duration(video)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(N):
        f = out / f"vf{i + 1}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{dur * (i + 0.5) / N:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=300:-2", "-q:v", "3", str(f)], capture_output=True)
        if f.exists():
            paths.append(f)
    return paths


def sheet(paths: list[Path]) -> bytes:
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = ims[0].size
    cols, rows = 4, (len(ims) + 3) // 4
    s = Image.new("RGB", (cols * w, rows * h), "#000000")
    d = ImageDraw.Draw(s)
    for i, im in enumerate(ims):
        x, y = (i % cols) * w, (i // cols) * h
        s.paste(im, (x, y))
        d.rectangle((x, y, x + 34, y + 26), fill="#000000")
        d.text((x + 8, y + 6), str(i + 1), fill="#FFFFFF")
    buf = io.BytesIO()
    s.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def vision_check(project: Path, year: int | None, video: str = "final_norm.mp4") -> dict:
    mode = os.getenv("VISION_QA", "advisory")
    if mode == "off":
        return {"status": "off"}
    paths = frames(project / "renders" / video, project / "review" / "vision")
    if len(paths) < N // 2:
        return {"status": "skipped", "reason": "could not extract frames"}
    host_rule = {"first": "frame 1 (the first seconds)", "first_last": "frames 1 and 8", "none": "no frame at all"}[brand.appear()]
    rep = generate_structured(f"Story year: {year or 'unknown'}.\nReview the contact sheet.", Report,
                              system=SYSTEM.format(host_rule=host_rule), temperature=0.0, task="vision",
                              images=[sheet(paths)])
    blockers = [i for i in rep.issues if i.severity.lower() == "blocker"]
    out = {"status": "blockers" if blockers else "clean", "mode": mode, "score": rep.score, "summary": rep.summary,
           "issues": [i.model_dump() for i in rep.issues]}
    (project / "vision.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse
    from . import styles
    from .storyboard_agent import story_year
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--video", default="final_norm.mp4")
    a = ap.parse_args()
    styles.set_active("history")
    print(json.dumps(vision_check(a.project, story_year(a.project), a.video), indent=2))