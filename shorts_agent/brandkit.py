"""Channel avatar + banner: host rendered by the engine, banner scene painted in cut-paper style with Pillow. No LLM, no quota."""
from __future__ import annotations

import math
import os
import random
import shutil

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import brand, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR
from .smoke import node

AVATAR_SHOT = """import { ctx, W, H } from './core/lib.js';
import * as K from './core/kit.js';
import * as HH from './core/hero.js';

export function buildShots() {
  return { shots: [{ id: 'AV', at: 0, cam: [540, 860], zoom: 0, note: 'avatar',
    draw() {
      ctx.fillStyle = '#2F7F86'; ctx.fillRect(-300, -300, W + 600, H + 600);
      for (let i = 0; i < 16; i++) {
        const a = i * Math.PI / 8, b = a + Math.PI / 16;
        K.cut(K.P_poly([[540, 860], [540 + 1500 * Math.cos(a), 860 + 1500 * Math.sin(a)], [540 + 1500 * Math.cos(b), 860 + 1500 * Math.sin(b)]]), '#3C929A', { shadow: 0, edge: 0 });
      }
      K.cut(K.P_circ(540, 860, 500), '#C8952F', { shadow: 0.6, edge: 6 });
      K.cut(K.P_circ(540, 860, 430), '#E4B54C', { shadow: 0, edge: 0 });
      K.cut(K.P_poly([[-100, 1560], [300, 1240], [720, 1440], [1180, 1180], [1180, 2200], [-100, 2200]]), '#A8322D');
      HH.hero({ x: 540, y: 2840, s: 3.6, dir: 1, mood: 'happy', eye: 0, blink: 0, t: 0 });
    } }], cues: [] };
}
"""
OUT = REPO / "brand" / "assets"
BW, BH = 2560, 1440
INK, CREAM, GOLD, CRIMSON = "#2B2118", "#F4EAD2", "#C8952F", "#A8322D"


def font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    names = ["georgiab.ttf", "georgia.ttf"] if bold else ["georgia.ttf", "georgiab.ttf"]
    for n in names + ["timesbd.ttf", "times.ttf"]:
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def spaced_width(text: str, f, sp: int) -> float:
    return sum(f.getlength(c) for c in text) + sp * (len(text) - 1)


def draw_spaced(d, cx: float, y: float, text: str, f, fill: str, sp: int, shadow: str | None = None):
    x = cx - spaced_width(text, f, sp) / 2
    for c in text:
        if shadow:
            d.text((x + 4, y + 5), c, font=f, fill=shadow, anchor="ls")
        d.text((x, y), c, font=f, fill=fill, anchor="ls")
        x += f.getlength(c) + sp


def fit_font(text: str, max_w: int, start: int, sp: int, bold: bool = True):
    size = start
    while size > 40:
        f = font(size, bold)
        if spaced_width(text, f, sp) <= max_w:
            return f
        size -= 6
    return font(40, bold)


# ───────────── cut-paper helpers ─────────────
def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def circ(cx, cy, r, n=40):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def paper_layer(img: Image.Image, polys, fill: str, shadow: float = 1.0, edge: str | None = None):
    """Draw polygons as one layer of cut paper: soft drop shadow first, then the paper."""
    if shadow:
        sh = Image.new("L", img.size, 0)
        sd = ImageDraw.Draw(sh)
        for p in polys:
            sd.polygon([(x + 8 * shadow, y + 12 * shadow) for x, y in p], fill=120)
        sh = sh.filter(ImageFilter.GaussianBlur(10 * shadow))
        img.paste((34, 24, 18), (0, 0), sh)
    d = ImageDraw.Draw(img)
    for p in polys:
        d.polygon(p, fill=fill)
        if edge:
            d.line(p + [p[0]], fill=edge, width=3)


def gradient(w: int, h: int, top, bottom) -> Image.Image:
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h))


def skyline(rng: random.Random, base: int, hmin: int, hmax: int):
    polys, x = [], -60
    while x < BW + 60:
        kind = rng.choice(["house", "house", "house", "tower", "church", "hall", "tree", "tree"])
        w, h = rng.randint(120, 240), rng.randint(hmin, hmax)
        top = base - h
        if kind == "house":
            polys += [rect(x, top, w, h + 4), [(x - 14, top), (x + w + 14, top), (x + w / 2, top - w * 0.55)],
                      rect(x + w * 0.7, top - w * 0.5, w * 0.12, w * 0.4)]
        elif kind == "tower":
            tw, top = w * 0.55, base - h * 1.5
            polys += [rect(x, top, tw, h * 1.5 + 4), [(x - 8, top), (x + tw + 8, top), (x + tw / 2, top - tw * 1.3)]]
        elif kind == "church":
            top = base - h * 0.8
            polys += [rect(x, top, w, h * 0.8 + 4), [(x - 10, top), (x + w + 10, top), (x + w * 0.3, top - w * 0.42)],
                      rect(x + w * 0.58, base - h * 1.7, w * 0.26, h * 1.7 + 4),
                      [(x + w * 0.58 - 6, base - h * 1.7), (x + w * 0.84 + 6, base - h * 1.7), (x + w * 0.71, base - h * 1.7 - w * 0.6)]]
        elif kind == "hall":
            polys.append(rect(x, top, w * 1.2, h + 4))
            polys += [rect(x + i * w * 0.3, top - 26, w * 0.18, 30) for i in range(4)]
            w = int(w * 1.2)
        else:
            polys += [rect(x + w * 0.45, base - 70, w * 0.1, 74), circ(x + w * 0.5, base - 70 - w * 0.35, w * 0.42)]
        x += w + rng.randint(-24, 28)
    return polys


def torn(x0, y0, x1, y1, rng, jag=9, step=24):
    top = [(x, y0 + rng.randint(-jag, jag)) for x in range(int(x0), int(x1), step)] + [(x1, y0 + rng.randint(-jag, jag))]
    bot = [(x, y1 + rng.randint(-jag, jag)) for x in range(int(x1), int(x0), -step)] + [(x0, y1 + rng.randint(-jag, jag))]
    return top + bot


def ribbon_poly(x0, y0, x1, y1, notch=36):
    ym = (y0 + y1) / 2
    return [(x0, y0), (x1, y0), (x1 - notch, ym), (x1, y1), (x0, y1), (x0 + notch, ym)]


# ───────────── avatar (engine) ─────────────
def render_avatar_frame():
    styles.set_active("history")
    project = PROJECTS_ROOT / "brand-assets"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "paper-atlas" / "example", project)
    shutil.copytree(REPO / "overlay" / "history", project, dirs_exist_ok=True)
    brand.write_js(project)
    (project / "src" / "shots.js").write_text(AVATAR_SHOT, encoding="utf-8")
    node(project, "check")
    node(project, "frames", "review/f", "1.0")
    frames = [f for f in (project / "review").rglob("*.jpg") if f.name != "all.jpg"]
    if not frames:
        raise SystemExit("capture.mjs frames produced no image under review/")
    return max(frames, key=lambda f: f.stat().st_mtime)


def circle_with_ring(img: Image.Image, size: int, ring: int, ring_color: str) -> Image.Image:
    out = Image.new("RGBA", (size + 2 * ring, size + 2 * ring), (0, 0, 0, 0))
    m = Image.new("L", out.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, out.size[0] - 1, out.size[1] - 1), fill=255)
    out.paste(Image.new("RGBA", out.size, ring_color), (0, 0), m)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(img.resize((size, size), Image.LANCZOS).convert("RGBA"), (ring, ring), mask)
    return out


# ───────────── banner (Pillow) ─────────────
def make_banner(avatar: Image.Image, name: str, tagline: str) -> Image.Image:
    rng = random.Random(11)
    img = gradient(BW, BH, (24, 45, 84), (247, 200, 135))
    paper_layer(img, [circ(1860, 930, 200)], "#F8D77F", shadow=0.3)
    clouds = []
    for cx, cy, s in [(260, 230, 1.1), (2260, 190, 1.0), (1260, 130, 0.8), (1950, 400, 0.6), (700, 380, 0.6)]:
        clouds += [circ(cx, cy, 58 * s), circ(cx + 70 * s, cy + 10 * s, 48 * s),
                   circ(cx - 70 * s, cy + 14 * s, 46 * s), circ(cx, cy + 22 * s, 56 * s)]
    paper_layer(img, clouds, "#FBF3E0", shadow=0.4)
    for base, hr, color, sh in [(960, (110, 180), "#8E78A0", 0.5), (1090, (150, 250), "#5E5683", 0.8), (1235, (200, 330), "#2F3860", 1.0)]:
        polys = skyline(rng, base, *hr)
        polys.append(rect(-60, base, BW + 120, BH - base + 60))
        paper_layer(img, polys, color, shadow=sh)

    # decorative date ribbons, outside the always-visible centre area
    paper_layer(img, [ribbon_poly(110, 330, 400, 420)], GOLD, shadow=0.8)
    paper_layer(img, [ribbon_poly(2160, 300, 2450, 390)], GOLD, shadow=0.8)
    d = ImageDraw.Draw(img)
    d.text((255, 375), "1666", font=font(54), fill=INK, anchor="mm")
    d.text((2305, 345), "1858", font=font(54), fill=INK, anchor="mm")

    # title strip (torn paper) inside the safe area (x 507..2053, y 508..931)
    paper_layer(img, [torn(930, 548, 2030, 800, rng)], CREAM, shadow=1.0, edge="#FFFBEF")
    d = ImageDraw.Draw(img)
    title = name.upper()
    f = fit_font(title, 960, 160, 10)
    draw_spaced(d, 1480, 716, title, f, INK, 10, shadow="#D9C9A4")
    d.rectangle((1480 - 220, 744, 1480 + 220, 754), fill=CRIMSON)
    paper_layer(img, [ribbon_poly(985, 832, 1975, 908)], GOLD, shadow=0.8)
    d = ImageDraw.Draw(img)
    tf = fit_font(tagline, 900, 44, 2, bold=False)
    draw_spaced(d, 1480, 884, tagline, tf, INK, 2)

    # host medallion
    cx, cy, r, ring = 700, 720, 165, 14
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).ellipse((cx - r - ring + 10, cy - r - ring + 16, cx + r + ring + 10, cy + r + ring + 16), fill=140)
    img.paste((34, 24, 18), (0, 0), sh.filter(ImageFilter.GaussianBlur(14)))
    med = circle_with_ring(avatar, 2 * r, ring, GOLD)
    img.paste(med, (cx - r - ring, cy - r - ring), med)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frame = Image.open(render_avatar_frame()).convert("RGB")      # 1080 x 1920
    avatar = frame.crop((0, 330, 1080, 1410)).resize((800, 800), Image.LANCZOS)
    avatar.save(OUT / "avatar.png")
    avatar.resize((98, 98), Image.LANCZOS).save(OUT / "avatar_98px_preview.png")
    ch = brand.load()["channel"]
    name = ch["name"] if ch["name"] != "TBD" else "Channel name"
    tagline = ch["tagline"] or "Strange but true history in 40 seconds"
    banner = make_banner(avatar, name, tagline)
    banner.save(OUT / "banner.png")
    banner.save(OUT / "banner.jpg", quality=92)                     # in case the PNG is over the upload size limit
    print("Saved avatar.png, avatar_98px_preview.png, banner.png and banner.jpg in", OUT)
    if hasattr(os, "startfile"):
        os.startfile(OUT / "banner.png")
        os.startfile(OUT / "avatar.png")


if __name__ == "__main__":
    main()