"""Thumbnail (1280x720) of a finished video: its most visual frame next to a big title. Made after the quality check."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import SKILL_DIR, proc_flags, render_env

FONT = SKILL_DIR / "styles" / "tall-tale" / "example" / "fonts" / "Inter-Black.otf"
INK = "#1F1C33"


def pick_time(story: dict) -> float:
    """The shot that shows the most (objects, callouts, effect, people), not the first and not an extreme close-up."""
    best, pick = -99, story["shots"][-1]
    for s in story["shots"][1:] or story["shots"]:
        score = 2 * len(s.get("props", [])) + 2 * len(s.get("callouts", [])) + len(s["actors"]) + (2 if s.get("effect") else 0) \
            - (4 if s["framing"] == "extreme_close" else 0)
        if score > best:
            best, pick = score, s
    return round(pick["at"] + (pick["end"] - pick["at"]) * 0.7, 2)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT), size)
    except OSError:
        return ImageFont.load_default()


def _wrap(d, text: str, size: int, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=_font(size)) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def make_thumbnail(project: Path, title: str) -> Path | None:
    story = json.loads((project / "story.json").read_text(encoding="utf-8"))
    t = pick_time(story)
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/thumb", str(t)], cwd=project, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, **render_env("balanced")}, creationflags=proc_flags())
    src = project / "review" / "thumb" / f"t{t:.2f}.jpg"
    if p.returncode != 0 or not src.exists():
        return None
    fr = Image.open(src).convert("RGB")
    W, H = 1280, 720
    img = ImageOps.fit(fr, (W, H)).filter(ImageFilter.GaussianBlur(20)).point(lambda v: int(v * 0.7))
    fh = H - 40
    small = fr.resize((int(fr.width * fh / fr.height), fh), Image.LANCZOS)
    x0 = W - small.width - 40
    ImageDraw.Draw(img).rounded_rectangle((x0 - 8, 12, x0 + small.width + 8, 28 + fh), 24, fill="#FFFFFF")
    img.paste(small, (x0, 20))
    d = ImageDraw.Draw(img)
    text = title.upper()[:44]
    for size in range(150, 50, -10):
        lines = _wrap(d, text, size, x0 - 80)
        if len(lines) * size * 1.08 <= H - 80 and all(d.textlength(l, font=_font(size)) <= x0 - 80 for l in lines):
            break
    y = (H - len(lines) * size * 1.08) / 2
    for i, l in enumerate(lines):
        d.text((50, y), l, font=_font(size), fill="#FFD35A" if i == 0 else "#FFFFFF", stroke_width=max(6, size // 14), stroke_fill=INK)
        y += size * 1.08
    out = project / "thumb.jpg"
    img.save(out, quality=88)
    return out