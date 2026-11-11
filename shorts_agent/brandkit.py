"""Channel avatar + banner rendered from the host character and brand.json (no LLM, no quota)."""
from __future__ import annotations

import os
import shutil

from PIL import Image, ImageDraw, ImageFont

from . import brand, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR
from .smoke import node

SHOTS = """import * as K from './core/kit.js';
import * as H from './core/hero.js';

export function buildShots() {
  return { shots: [{ id: 'AV', at: 0, cam: [540, 760], zoom: 0, note: 'avatar',
    draw(lt, d, t) {
      K.parchment(5);
      H.hero({ x: 540, y: 2190, s: 2.6, dir: 1, mood: 'happy', eye: 0, blink: 0, t: 0 });
    } }], cues: [] };
}
"""
OUT = REPO / "brand" / "assets"


def font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    names = ["georgiab.ttf", "georgia.ttf"] if bold else ["georgia.ttf", "georgiab.ttf"]
    for n in names + ["timesbd.ttf", "times.ttf"]:
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render_frame():
    styles.set_active("history")
    project = PROJECTS_ROOT / "brand-assets"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "paper-atlas" / "example", project)
    shutil.copytree(REPO / "overlay" / "history", project, dirs_exist_ok=True)
    brand.write_js(project)
    (project / "src" / "shots.js").write_text(SHOTS, encoding="utf-8")
    node(project, "check")
    node(project, "frames", "review/f", "1.0")
    frames = [f for f in (project / "review").rglob("*.jpg") if f.name != "all.jpg"]
    if not frames:
        raise SystemExit("capture.mjs frames produced no image under review/")
    return max(frames, key=lambda f: f.stat().st_mtime)


def circle(img: Image.Image, size: int, ring: int = 0, ring_color: str = "#C8952F") -> Image.Image:
    out = Image.new("RGBA", (size + 2 * ring, size + 2 * ring), (0, 0, 0, 0))
    if ring:
        m = Image.new("L", out.size, 0)
        ImageDraw.Draw(m).ellipse((0, 0, out.size[0] - 1, out.size[1] - 1), fill=255)
        out.paste(Image.new("RGBA", out.size, ring_color), (0, 0), m)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(img.resize((size, size), Image.LANCZOS).convert("RGBA"), (ring, ring), mask)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frame = Image.open(render_frame()).convert("RGB")          # 1080 x 1920
    avatar = frame.crop((140, 360, 940, 1160)).resize((800, 800), Image.LANCZOS)
    avatar.save(OUT / "avatar.png")

    ch = brand.load()["channel"]
    name = ch["name"] if ch["name"] != "TBD" else "Channel name"
    tagline = ch["tagline"] or "Strange but true history in 40 seconds"
    W, H = 2560, 1440
    ban = Image.new("RGB", (W, H), "#E9DCBC")
    d = ImageDraw.Draw(ban)
    d.rectangle((0, 0, W, 26), fill="#A8322D")
    d.rectangle((0, H - 26, W, H), fill="#A8322D")
    cx, cy, r = 690, 720, 160                                    # inside the 1546 x 423 safe area
    ban.paste(circle(avatar, 2 * r, ring=12), (cx - r - 12, cy - r - 12), circle(avatar, 2 * r, ring=12))
    d.text((930, 650), name, font=font(130), fill="#2B2118", anchor="ls")
    d.rectangle((930, 676, 1350, 688), fill="#A8322D")
    d.text((930, 770), tagline, font=font(46, False), fill="#3E2C1E", anchor="ls")
    ban.save(OUT / "banner.png")
    print("Saved", OUT / "avatar.png", "and", OUT / "banner.png")
    if hasattr(os, "startfile"):
        os.startfile(OUT / "banner.png")


if __name__ == "__main__":
    main()