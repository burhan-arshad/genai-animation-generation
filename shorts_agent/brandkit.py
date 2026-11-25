"""Channel kit for the mysteries channel, painted with Pillow (no renderer, no LLM, no quota, about 5 seconds):
  avatar.png            800 x 800 (1:1), YouTube crops it to a circle and shows it at 98 x 98
  banner.jpg / .png     2560 x 1440 (16:9), all text inside the 1546 x 423 safe area (max file size 6 MB)
  channel_text.txt      handle ideas, About text, keywords
python -m shorts_agent.brandkit                                  uses channel.name and channel.tagline of brand/brand.json
python -m shorts_agent.brandkit --name "The Open File" --tagline "Mysteries solved and unsolved in 50 seconds"
python -m shorts_agent.brandkit --names                          name ideas"""
import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import brand
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, proc_flags, render_env

OUT = REPO / "brand" / "assets"
BW, BH = 2560, 1440
SAFE_W, SAFE_H = 1546, 423
SX0, SY0 = (BW - SAFE_W) // 2, (BH - SAFE_H) // 2
SX1, SY1 = SX0 + SAFE_W, SY0 + SAFE_H
INK, GOLD, GOLD_D, PAPER, RED = "#0A0E22", "#E2B33C", "#A87A22", "#F3E9D2", "#C8283A"
FONT = SKILL_DIR / "styles" / "tall-tale" / "example" / "fonts" / "Inter-Black.otf"
DEFAULT_NAME = "The Open File"
DEFAULT_TAG = "Mysteries solved and unsolved in 50 seconds"
NAME_IDEAS = [
    ("The Open File", "an open case = unsolved, a file = the evidence; short, easy to say, fits solved and unsolved cases"),
    ("Clue Cabinet", "a cabinet of clues; friendly, collectable feeling"),
    ("The Missing Page", "a page missing from history; mysterious and bookish"),
    ("Cold Trail", "the trail went cold; very short, may already be taken"),
    ("Unsolved Ledger", "a ledger of cases; formal tone"),
]


def font(size: int) -> ImageFont.ImageFont:
    for p in (str(FONT), "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(d, text: str, max_w: int, start: int, min_size: int = 40) -> ImageFont.ImageFont:
    s = start
    while s > min_size:
        f = font(s)
        if d.textlength(text, font=f) <= max_w:
            return f
        s -= 4
    return font(min_size)


def vgrad(w: int, h: int, stops: list) -> Image.Image:
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / ((p1 - p0) or 1)
                px[0, y] = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                break
    return col.resize((w, h))


def overlay(img: Image.Image, fn, blur: int = 0) -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fn(ImageDraw.Draw(layer))
    if blur:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def make_avatar() -> Image.Image:
    """A magnifying glass with a question mark, gold on night blue: readable even at 98 x 98. Drawn at 1600 and scaled down for smooth edges."""
    S = 1600
    img = vgrad(S, S, [(0, (30, 42, 92)), (1, (9, 13, 34))])
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((S * .18, S * .16, S * .82, S * .80), fill=130)
    img = Image.composite(Image.new("RGB", (S, S), (92, 116, 206)), img, mask.filter(ImageFilter.GaussianBlur(S * .10)))
    d = ImageDraw.Draw(img)
    rnd = random.Random(7)
    for _ in range(46):
        x, y, r = rnd.randint(120, S - 120), rnd.randint(120, S - 120), rnd.choice([3, 4, 6])
        v = rnd.randint(120, 220)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(v, v, min(255, v + 25)))
    cx, cy, R = 736, 704, 400
    a = math.radians(45)
    sx, sy = cx + R * math.cos(a), cy + R * math.sin(a)
    ex, ey = sx + 352 * math.cos(a), sy + 352 * math.sin(a)
    d.line([(sx, sy), (ex, ey)], fill=GOLD_D, width=120)
    d.ellipse((ex - 60, ey - 60, ex + 60, ey + 60), fill=GOLD_D)
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(14, 20, 48), outline=GOLD, width=72)
    d.text((cx, cy + 14), "?", font=font(int(S * .42)), fill=GOLD, anchor="mm")
    d.arc((cx - R + 110, cy - R + 110, cx + R - 110, cy + R - 110), 200, 250, fill=(255, 255, 255), width=26)
    d.ellipse((30, 30, S - 30, S - 30), outline=GOLD, width=34)
    return img.resize((800, 800), Image.LANCZOS)


def make_banner(name: str, tagline: str) -> tuple[Image.Image, bool]:
    """Night sky, moon, a lighthouse and a ghost ship far left and right; the title and tagline sit inside the safe area."""
    img = vgrad(BW, BH, [(0, (8, 12, 30)), (0.45, (24, 34, 78)), (0.71, (58, 72, 128)), (0.715, (10, 14, 30)), (1, (4, 6, 16))])
    rnd = random.Random(11)
    d = ImageDraw.Draw(img)
    for _ in range(340):
        x, y, r = rnd.randint(0, BW), rnd.randint(0, 880), rnd.choice([1, 1, 2, 2, 3])
        v = rnd.randint(110, 230)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(v, v, min(255, v + 20)))
    img = overlay(img, lambda g: g.ellipse((2000, -10, 2520, 510), fill=(150, 170, 230, 70)), 70)
    d = ImageDraw.Draw(img)
    d.ellipse((2140, 130, 2380, 370), fill=(244, 238, 214))
    for cx, cy, r in ((2220, 215, 26), (2300, 290, 20), (2290, 195, 14)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(226, 219, 192))
    for i, w in enumerate((170, 140, 110, 80, 55, 35)):                       # the moon's path on the sea
        y = 1060 + i * 58
        d.rectangle((2260 - w, y, 2260 + w, y + 10), fill=(120, 138, 190))
    img = overlay(img, lambda g: g.polygon([(230, 594), (BW, 330), (BW, 860)], fill=(255, 225, 140, 34)), 6)   # the lighthouse beam
    d = ImageDraw.Draw(img)
    d.polygon([(40, 1110), (150, 1015), (330, 1000), (440, 1110)], fill=(9, 12, 26))
    d.polygon([(168, 1012), (292, 1012), (270, 640), (190, 640)], fill=(12, 16, 36))
    d.rectangle((176, 626, 284, 646), fill=(9, 12, 26))
    d.rectangle((198, 560, 262, 626), fill=(12, 16, 36))
    d.rectangle((208, 572, 252, 616), fill=(255, 222, 120))
    d.polygon([(190, 560), (230, 520), (270, 560)], fill=(9, 12, 26))
    d.polygon([(2090, 1030), (2540, 1030), (2500, 1090), (2140, 1090)], fill=(8, 10, 22))                      # the ghost ship
    d.line([(2090, 1030), (2000, 1000)], fill=(8, 10, 22), width=8)
    for mx, top in ((2230, 740), (2350, 690), (2460, 760)):
        d.line([(mx, 1030), (mx, top)], fill=(8, 10, 22), width=9)
    d.polygon([(2238, 760), (2238, 960), (2330, 950), (2318, 880), (2335, 800)], fill=(14, 18, 40))
    d.polygon([(2358, 712), (2358, 930), (2450, 940), (2432, 860), (2446, 780)], fill=(14, 18, 40))
    d.polygon([(2468, 780), (2468, 940), (2520, 930), (2510, 860)], fill=(14, 18, 40))
    for y, a in ((930, 55), (1010, 80), (1090, 70)):                                                          # fog
        img = overlay(img, lambda g, y=y, a=a: g.ellipse((-200, y - 45, BW + 200, y + 45), fill=(170, 185, 225, a)), 40)
    vm = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(vm).ellipse((-300, -250, BW + 300, BH + 250), fill=255)
    img = Image.composite(img, Image.new("RGB", (BW, BH), (0, 0, 0)), vm.filter(ImageFilter.GaussianBlur(200)))
    d = ImageDraw.Draw(img)
    title, cx = name.upper(), BW // 2
    f = fit(d, title, SAFE_W - 200, 170)
    d.text((cx, 655), title, font=f, fill=GOLD, anchor="mm", stroke_width=9, stroke_fill=INK)
    d.rectangle((cx - 150, 742, cx + 150, 748), fill=RED)
    tf = fit(d, tagline, SAFE_W - 240, 50, 28)
    d.text((cx, 800), tagline, font=tf, fill=PAPER, anchor="mm", stroke_width=4, stroke_fill=INK)
    boxes = [d.textbbox((cx, 655), title, font=f, anchor="mm", stroke_width=9), d.textbbox((cx, 800), tagline, font=tf, anchor="mm", stroke_width=4)]
    return img, all(SX0 <= b[0] and b[2] <= SX1 and SY0 <= b[1] and b[3] <= SY1 for b in boxes)


def previews(banner: Image.Image) -> None:
    p = banner.copy().convert("RGBA")
    shade = Image.new("RGBA", p.size, (0, 0, 0, 150))
    ImageDraw.Draw(shade).rectangle((SX0, SY0, SX1, SY1), fill=(0, 0, 0, 0))
    p = Image.alpha_composite(p, shade)
    ImageDraw.Draw(p).rectangle((SX0, SY0, SX1, SY1), outline=(255, 60, 60, 255), width=6)
    p.convert("RGB").resize((1280, 720)).save(OUT / "banner_safe_area_preview.jpg", quality=88)
    banner.crop((SX0, SY0, SX1, SY1)).save(OUT / "banner_preview_phone.png")
    banner.crop((0, SY0, BW, SY1)).resize((1280, 211)).save(OUT / "banner_preview_desktop.png")


def channel_text(name: str, tagline: str) -> str:
    h = re.sub(r"[^a-z0-9]", "", name.lower())
    return (f"CHANNEL NAME: {name}\nTAGLINE: {tagline}\n\nHANDLE IDEAS (check which one is free in YouTube Studio, Customization, Basic info):\n"
            f"  @{h}\n  @{h}hq\n  @{h}shorts\n\nABOUT (paste into Customization, Basic info, Description):\n"
            "Every case has a last known moment. We open the file and follow the clues: vanished ships, forgeries, lost treasures, strange objects "
            "and the mysteries that were finally cracked.\n\nNew 50-second case files. Scripts are written from public sources and checked against "
            "reliable references; theories are always labelled as theories.\n\nNarrated and animated with AI tools.\n\n"
            "KEYWORDS: mystery, unsolved mysteries, cold case, solved mysteries, history mysteries, hoax, lost treasure, shorts\n")


def avatar_bg(S: int = 1600) -> Image.Image:
    img = vgrad(S, S, [(0, (30, 42, 92)), (1, (9, 13, 34))])
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((S * .12, S * .10, S * .88, S * .86), fill=150)
    img = Image.composite(Image.new("RGB", (S, S), (92, 116, 206)), img, mask.filter(ImageFilter.GaussianBlur(S * .10)))
    d = ImageDraw.Draw(img)
    rnd = random.Random(7)
    for _ in range(46):
        x, y, r = rnd.randint(60, S - 60), rnd.randint(60, S - 60), rnd.choice([3, 4, 6])
        v = rnd.randint(120, 220)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(v, v, min(255, v + 25)))
    return img


def finish_avatar(img: Image.Image) -> Image.Image:
    ImageDraw.Draw(img).ellipse((30, 30, img.size[0] - 30, img.size[1] - 30), outline=GOLD, width=34)
    return img.resize((800, 800), Image.LANCZOS)


def render_hero_frames(mood: str):
    """Two frames of the same still shot of the host's study: with him and without him. -> [with, without] or None."""
    ex = SKILL_DIR / "styles" / "film" / "example"
    if not (ex / "src" / "core" / "film.js").exists():
        print("[brandkit] the film engine folder was not found")
        return None
    project = PROJECTS_ROOT / "brand-assets"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(ex, project)
    brand.write_js(project)
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "lines.json").write_text(json.dumps({"duration": 4, "lines": [{"i": 0, "text": "x", "start": 0, "end": 4}]}), encoding="utf-8")
    (project / "data" / "words.json").write_text("[]", encoding="utf-8")
    (project / "script.json").write_text(json.dumps({"title": "brand", "lines": [{"text": "x"}]}), encoding="utf-8")
    hero = {"who": "hero", "x0": 40, "x1": 40, "d": 1, "face": "r", "mood": mood, "arms": {"l": "down", "r": "chin"}, "legs": "stand",
            "talk": False, "held": {}, "beats": []}
    env = {**os.environ, **render_env(project=project)}
    frames = []
    for name, actors in (("with", [hero]), ("without", [])):
        shot = {"id": "S01", "at": 0.0, "end": 4.0, "set": "study", "framing": "close", "camera": "static", "focus_x": 40, "transition": "cut",
                "effect": "", "fx": "", "note": "avatar", "actors": actors, "props": [], "callouts": [], "panel": {"prop": "scroll", "s": 1.0}}
        story = {"title": "brand", "meta": {}, "duration": 4.0, "cast": {}, "sets": {"study": {"kind": "study", "time": "night", "dress": []}},
                 "custom": {}, "shots": [shot]}
        (project / "data" / "story.json").write_text(json.dumps(story), encoding="utf-8")
        p = subprocess.run(["node", "tools/capture.mjs", "frames", f"review/{name}", "1.2"], cwd=project, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, creationflags=proc_flags())
        f = project / "review" / name / "t1.20.jpg"
        if p.returncode != 0 or not f.exists():
            print((p.stdout + p.stderr)[-600:])
            return None
        frames.append(Image.open(f).convert("RGB"))
    return frames


def hero_avatar(mood: str = "think"):
    """The host cut out of the frame (the difference between the two renders is exactly him), head and shoulders, on the avatar background."""
    frames = render_hero_frames(mood)
    if not frames:
        return None
    with_h, without = frames
    W, H = with_h.size
    half = (W // 2, H // 2)
    diff = ImageChops.difference(with_h, without).convert("L").resize(half)
    m = diff.point(lambda v: 255 if v > 36 else 0).filter(ImageFilter.MedianFilter(5))
    m = m.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    fill = m.copy()
    ImageDraw.floodfill(fill, (0, 0), 128)                                   # holes inside him become part of the mask
    m = ImageChops.lighter(m, fill.point(lambda v: 255 if v == 0 else 0))
    box = m.getbbox()
    if not box or (box[2] - box[0]) < 60 or (box[2] - box[0]) * (box[3] - box[1]) < 0.02 * half[0] * half[1]:
        print("[brandkit] could not find the host in the frame")
        return None
    mask = m.resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))
    x0, y0, x1, y1 = (v * 2 for v in box)
    s = int(min((x1 - x0) * 1.3, W, H))
    left = max(0, min(W - s, (x0 + x1) // 2 - s // 2))
    top = max(0, min(H - s, y0 - int(0.08 * s)))
    T = 1560
    cut = with_h.crop((left, top, left + s, top + s)).resize((T, T), Image.LANCZOS)
    cm = mask.crop((left, top, left + s, top + s)).resize((T, T), Image.LANCZOS)
    img = avatar_bg()
    img.paste(cut, ((1600 - T) // 2, 1600 - T), cm)
    return finish_avatar(img)


def bust_avatar() -> Image.Image:
    """Fallback: a simplified drawing of the host from brand.json (used when the film engine cannot draw him)."""
    c = brand.load()["character"]
    look = c["presets"][c["preset"]]
    img = avatar_bg()
    d = ImageDraw.Draw(img)
    ink, skin = (31, 28, 51), look.get("skin", "#F1C9A0")
    d.ellipse((190, 1180, 1410, 2100), fill=look["body"], outline=ink, width=14)
    if look.get("pattern") in ("vest", "overalls", "stripes"):
        d.polygon([(560, 1190), (800, 1500), (1040, 1190), (1040, 1600), (560, 1600)], fill=look.get("patCol", "#6B422B"), outline=ink)
    if look.get("neck", "none") != "none":
        d.rounded_rectangle((590, 1080, 1010, 1250), 50, fill=look.get("neckCol", "#A8322D"), outline=ink, width=12)
    d.ellipse((470, 410, 1130, 1110), fill=skin, outline=ink, width=16)
    for ex in (690, 910):
        d.ellipse((ex - 24, 740, ex + 24, 800), fill=ink)
    extra = look.get("extra", [])
    if "blush" in extra:
        for bx in (610, 990):
            d.ellipse((bx - 50, 850, bx + 50, 910), fill=(236, 150, 140))
    if "glasses" in extra:
        for ex in (690, 910):
            d.ellipse((ex - 85, 700, ex + 85, 840), outline=ink, width=14)
        d.line([(775, 770), (825, 770)], fill=ink, width=14)
    d.arc((700, 840, 900, 960), 20, 160, fill=ink, width=14)
    d.pieslice((455, 380, 1145, 900), 180, 360, fill=look.get("hair", "#2B2118"), outline=None if look.get("hat", "none") != "none" else ink, width=14)
    if look.get("hat", "none") != "none":
        hc = look.get("hatCol", "#3A3532")
        d.pieslice((540, 250, 1060, 650), 180, 360, fill=hc, outline=ink, width=14)
        d.ellipse((470, 420, 1130, 500), fill=hc, outline=ink, width=14)
    return finish_avatar(img)


def circle_preview(av: Image.Image) -> None:
    """How YouTube shows it: cropped to a circle, big and at 98 x 98."""
    m = Image.new("L", av.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, av.size[0] - 1, av.size[1] - 1), fill=255)
    out = Image.new("RGB", (560, 400), (24, 24, 28))
    big = Image.new("RGB", (400, 400), (24, 24, 28))
    big.paste(av.resize((400, 400), Image.LANCZOS), (0, 0), m.resize((400, 400), Image.LANCZOS))
    small = Image.new("RGB", (98, 98), (24, 24, 28))
    small.paste(av.resize((98, 98), Image.LANCZOS), (0, 0), m.resize((98, 98), Image.LANCZOS))
    out.paste(big, (0, 0))
    out.paste(small, (440, 150))
    out.save(OUT / "avatar_circle_preview.png")

def mb(path) -> float:
    return path.stat().st_size / 1048576


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--tagline")
    ap.add_argument("--names", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--mood", default="think", help="the host's mood in the avatar: think, smug, happy, sly, proud...")
    ap.add_argument("--draw", action="store_true", help="skip the film engine: use the simplified drawing of the host")
    ap.add_argument("--icon", action="store_true", help="the magnifying-glass icon instead of the host")
    a = ap.parse_args()
    if a.names:
        for n, why in NAME_IDEAS:
            print(f"{n:<18} {why}")
        print("\nPick one: python -m shorts_agent.brandkit --name \"The Open File\"\nCheck that the handle is free in YouTube Studio before you upload.")
        return
    b = brand.load()
    if a.name or a.tagline:
        if a.name:
            b["channel"]["name"] = a.name.strip()
        if a.tagline:
            b["channel"]["tagline"] = a.tagline.strip()
        brand.PATH.write_text(json.dumps(b, indent=2, ensure_ascii=False), encoding="utf-8")
    name = b["channel"]["name"] if b["channel"]["name"] != "TBD" else DEFAULT_NAME
    tagline = b["channel"]["tagline"] or DEFAULT_TAG
    OUT.mkdir(parents=True, exist_ok=True)
    how = "the magnifying-glass icon"
    if a.icon:
        av = make_avatar()
    else:
        av = None if a.draw else hero_avatar(a.mood)
        how = "your host, rendered by the film engine"
        if av is None:
            av, how = bust_avatar(), "a simplified drawing of your host (from brand.json)"
    av.save(OUT / "avatar.png")
    av.resize((98, 98), Image.LANCZOS).save(OUT / "avatar_98px_preview.png")
    circle_preview(av)
    banner, inside = make_banner(name, tagline)
    banner.save(OUT / "banner.jpg", quality=92)
    banner.save(OUT / "banner.png")
    previews(banner)
    (OUT / "channel_text.txt").write_text(channel_text(name, tagline), encoding="utf-8")
    png_ok = mb(OUT / "banner.png") <= 6
    print(f"Channel: {name} | {tagline}\n")
    print(f"avatar.png            {av.size[0]}x{av.size[1]}  (1:1)    OK   {mb(OUT / 'avatar.png'):.2f} MB   made from: {how}")
    print(f"banner.jpg            {BW}x{BH} (16:9)   OK   {mb(OUT / 'banner.jpg'):.2f} MB   (limit 6 MB)  <- upload this one")
    print(f"banner.png            {mb(OUT / 'banner.png'):.2f} MB   " + ("OK" if png_ok else "OVER 6 MB: upload banner.jpg instead"))
    print(f"text inside the {SAFE_W}x{SAFE_H} safe area: {'yes' if inside else 'NO: use a shorter name or tagline'}")
    print(f"\nFiles are in {OUT}. Look at avatar_circle_preview.png (how YouTube shows it), banner_safe_area_preview.jpg and channel_text.txt.")
    if hasattr(os, "startfile") and not a.no_open:
        for f in ("avatar_circle_preview.png", "banner_safe_area_preview.jpg"):
            os.startfile(OUT / f)

if __name__ == "__main__":
    main()