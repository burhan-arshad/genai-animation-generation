"""Channel avatar + banner + host sheet for the Tall Tale look. The host is rendered by the engine (real 3D scene, real hero),
the banner is painted with Pillow. No LLM, no quota.   python -m shorts_agent.brandkit"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from . import brand, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, render_env
from .storyboard_agent import sync_overlay

OUT = REPO / "brand" / "assets"
BW, BH = 2560, 1440
INK, CREAM, GOLD, CRIMSON, SHADOW = "#1F1C33", "#F4EBD6", "#E2B33C", "#C8283A", "#2A3A55"
FONT = SKILL_DIR / "styles" / "tall-tale" / "example" / "fonts" / "Inter-Black.otf"

SHOT = """import { camera } from './core/engine.js';
import * as WD from './core/world.js';
import { Toon } from './core/toon.js';
import { BRAND } from './core/brand.js';
import { heroLook } from './core/hero.js';

export function buildShots(E) {
  const M = WD.meadow(E, { fenceOn: false });
  const cam = camera(40);
  const pre = BRAND.character.presets, keys = Object.keys(pre);
  const main = new Toon(heroLook(BRAND.character.look), { height: 1.75, res: 2 });
  M.scene.add(main.group);
  const row = keys.map((k) => { const T = new Toon(heroLook(pre[k]), { height: 1.75, res: 1.5 }); M.scene.add(T.group); return T; });
  const MOODS = ['happy', 'smug', 'shock', 'laugh', 'worried'];
  const fx = { bloom: 0.2, aperture: 0.0008, maxblur: 0.006, vignette: 0.1 };
  const shots = [
    { id: 'AV', at: 0, note: 'avatar', draw(lt, d, t, blit) {
      row.forEach((T) => { T.group.visible = false; });
      main.group.visible = true;
      cam.position.set(0.12, 1.5, 2.1); cam.lookAt(0, 1.44, 0);
      main.set({ mood: 'happy' }).at(0, 0, 0).face(cam);
      E.render(M.scene, cam, { ...fx, focus: 2.1 }); blit();
    } },
    { id: 'SH', at: 2, note: 'host sheet', draw(lt, d, t, blit) {
      main.group.visible = false;
      cam.position.set(0, 1.0, 7.2); cam.lookAt(0, 0.95, 0);
      row.forEach((T, i) => { T.group.visible = true; T.set({ mood: MOODS[i % MOODS.length], armR: i === 0 ? [150, 10] : [8, 6] }).at((i - (row.length - 1) / 2) * 0.85, 0, 0).face(cam); });
      E.render(M.scene, cam, { ...fx, aperture: 0, focus: 7.2 }); blit();
    } },
  ];
  return { shots, cues: [] };
}
"""


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT), size)
    except OSError:
        return ImageFont.load_default()


def fit(d, text: str, max_w: int, start: int):
    size = start
    while size > 30:
        f = font(size)
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(30)


def gradient(w: int, h: int, top, bottom) -> Image.Image:
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h))


def poly(d, pts, fill):
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=INK, width=6, joint="curve")


def cloud(d, cx, cy, s):
    puffs = [(0, 0, 60), (70, 10, 48), (-70, 14, 46), (0, 22, 56)]
    for outline in (True, False):
        for dx, dy, r in puffs:
            rr = (r + (7 if outline else 0)) * s
            d.ellipse((cx + dx * s - rr, cy + dy * s - rr, cx + dx * s + rr, cy + dy * s + rr), fill=INK if outline else "#FFFFFF")


def hill(img, base, amp, color, seed, freq):
    d = ImageDraw.Draw(img)
    pts = [(x, base + math.sin(x * freq + seed) * amp + math.sin(x * freq * 2.3 + seed * 2) * amp * 0.4) for x in range(-20, BW + 40, 20)]
    d.polygon(pts + [(BW + 40, BH + 20), (-20, BH + 20)], fill=color)
    d.line(pts, fill=INK, width=8, joint="curve")


def house(d, x, y, s, wall, roof):
    w, h = 150 * s, 110 * s
    d.rectangle((x - w / 2, y - h, x + w / 2, y), fill=wall, outline=INK, width=6)
    poly(d, [(x - w / 2 - 12 * s, y - h), (x, y - h - 80 * s), (x + w / 2 + 12 * s, y - h)], roof)
    d.rectangle((x - 14 * s, y - 60 * s, x + 14 * s, y), fill="#3C6FB6", outline=INK, width=4)


def circle_with_ring(img: Image.Image, size: int, ring: int, ring_color: str) -> Image.Image:
    out = Image.new("RGBA", (size + 2 * ring, size + 2 * ring), (0, 0, 0, 0))
    m = Image.new("L", out.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, out.size[0] - 1, out.size[1] - 1), fill=255)
    out.paste(Image.new("RGBA", out.size, ring_color), (0, 0), m)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(img.resize((size, size), Image.LANCZOS).convert("RGBA"), (ring, ring), mask)
    return out


def make_banner(avatar: Image.Image, name: str, tagline: str) -> Image.Image:
    img = gradient(BW, BH, (61, 142, 224), (203, 234, 248))
    d = ImageDraw.Draw(img)
    d.ellipse((2090, 140, 2330, 380), fill="#FFD35A", outline=INK, width=8)                   # sun
    for cx, cy, s in [(300, 250, 1.2), (1260, 150, 0.9), (2330, 520, 0.8), (760, 420, 0.7)]:
        cloud(d, cx, cy, s)
    hill(img, 960, 70, "#9FD07A", 1.0, 0.0042)
    hill(img, 1090, 60, "#79C25A", 2.5, 0.0055)
    hill(img, 1235, 50, "#5DA83E", 4.0, 0.0065)
    d = ImageDraw.Draw(img)
    for x, y, s, w, r in [(150, 1010, 1.0, "#F2E6CF", "#B5553C"), (2420, 1000, 1.1, "#F2C9D6", "#3E5FA8"),
                          (360, 1130, 0.8, "#6FA3B8", "#A8322D"), (2200, 1120, 0.9, "#E3C16F", "#7A5236")]:
        house(d, x, y, s, w, r)

    # title plate, inside the always-visible centre area (x 507..2053, y 508..931)
    d.rounded_rectangle((940, 562, 2040, 814), 36, fill=SHADOW)
    d.rounded_rectangle((930, 548, 2030, 800), 36, fill=CREAM, outline=INK, width=8)
    f = fit(d, name, 960, 150)
    d.text((1480, 664), name, font=f, fill=INK, anchor="mm")
    d.rectangle((1260, 744, 1700, 756), fill=CRIMSON)
    poly(d, [(985, 832), (1975, 832), (1939, 870), (1975, 908), (985, 908), (1021, 870)], GOLD)
    tf = fit(d, tagline, 880, 44)
    d.text((1480, 870), tagline, font=tf, fill=INK, anchor="mm")

    # host medallion
    cx, cy, r, ring = 700, 720, 165, 14
    d.ellipse((cx - r - ring - 7 + 10, cy - r - ring - 7 + 14, cx + r + ring + 7 + 10, cy + r + ring + 7 + 14), fill=SHADOW)
    d.ellipse((cx - r - ring - 7, cy - r - ring - 7, cx + r + ring + 7, cy + r + ring + 7), fill=INK)
    med = circle_with_ring(avatar, 2 * r, ring, GOLD)
    img.paste(med, (cx - r - ring, cy - r - ring), med)
    return img


def make_project():
    styles.set_active(styles.default_key())
    project = PROJECTS_ROOT / "brand-assets"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "tall-tale" / "example", project)
    sync_overlay(project, styles.active())                                  # director.js, hero.js and brand.js
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "lines.json").write_text(json.dumps({"duration": 6, "lines": [{"i": 0, "text": "x", "start": 0, "end": 6}]}), encoding="utf-8")
    (project / "data" / "words.json").write_text("[]", encoding="utf-8")      # no captions on the avatar
    (project / "script.json").write_text(json.dumps({"title": "brand", "lines": [{"text": "x"}]}), encoding="utf-8")
    (project / "src" / "shots.js").write_text(SHOT, encoding="utf-8")
    return project


def render(project):
    env = {**os.environ, **render_env("quality")}                           # one frame each: full quality is cheap
    env.setdefault("BOOT_SECONDS", "600")
    p = subprocess.run(["node", "tools/capture.mjs", "frames", "review/f", "1.0,3.0"], cwd=project, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    print((p.stdout + p.stderr)[-800:])
    if p.returncode != 0:
        raise SystemExit("render failed: see the output above")
    f = project / "review" / "f"
    return Image.open(f / "t1.00.jpg").convert("RGB"), Image.open(f / "t3.00.jpg").convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    av_frame, sheet = render(make_project())
    avatar = av_frame.crop((0, 420, 1080, 1500)).resize((800, 800), Image.LANCZOS)      # 1080 x 1080 around the host's head
    avatar.save(OUT / "avatar.png")
    avatar.resize((98, 98), Image.LANCZOS).save(OUT / "avatar_98px_preview.png")
    sheet.save(OUT / "host_sheet.jpg", quality=92)
    ch = brand.load()["channel"]
    name = ch["name"] if ch["name"] != "TBD" else "Channel name"
    tagline = ch["tagline"] or "Strange but true stories in 40 seconds"
    banner = make_banner(avatar, name, tagline)
    banner.save(OUT / "banner.png")
    banner.save(OUT / "banner.jpg", quality=92)                              # in case the PNG is over the upload size limit
    print("Saved avatar.png, avatar_98px_preview.png, host_sheet.jpg, banner.png and banner.jpg in", OUT)
    if hasattr(os, "startfile"):
        for f in ("banner.png", "avatar.png", "host_sheet.jpg"):
            os.startfile(OUT / f)


if __name__ == "__main__":
    main()