"""Brand config: one JSON file drives the host character look, voice and audience note."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .config import REPO

PATH = REPO / "brand" / "brand.json"

DEFAULTS = {
    "channel": {"name": "TBD", "tagline": ""},
        "character": {
        "name": "History Student",
        "preset": "a",
        "appear": "first",
        "scale": 1.0,
        "presets": {
            "a": {"body": "#EBDDBF", "pattern": "vest", "patCol": "#6B422B", "hat": "none", "neck": "scarf", "neckCol": "#A8322D",
                  "extra": ["glasses", "blush"], "hair": "#2B2118", "hairStyle": "messy", "satchel": "#8A5A35", "kid": False},
            "b": {"body": "#7FB7BE", "pattern": "stripes", "patCol": "#5E9AA1", "hat": "none", "neck": "bowtie", "neckCol": "#C8952F",
                  "extra": ["glasses"], "hair": "#4A2D1B", "hairStyle": "side", "satchel": "#6B4F34", "kid": False},
            "c": {"body": "#F3E9D2", "pattern": "overalls", "patCol": "#3E5FA8", "hat": "none", "neck": "none",
                  "extra": ["freckles"], "hair": "#1B1410", "hairStyle": "curly", "satchel": "#A8322D", "kid": False},
        },
    },
    "voice": {"name": "am_michael", "speed": 1.05, "music": "bounce", "fx": ""},
    "audience": {
        "regions": ["United States", "Europe"],
        "writing_note": (
            "AUDIENCE: viewers in the United States and Europe. "
            "Use American English spelling. Add one short clause of "
            "context for anything a non-local viewer may not know "
            "(where it is, who they were). Avoid slang and idioms "
            "that do not travel. Quote units exactly as the evidence "
            "does; never convert. Neutral, factual tone; no jokes "
            "at any nation's expense."
        ),
    },
}

def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load() -> dict:
    if not PATH.exists():
        PATH.parent.mkdir(exist_ok=True)
        PATH.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
    return _merge(DEFAULTS, json.loads(PATH.read_text(encoding="utf-8")))


def appear() -> str:
    a = load()["character"]["appear"]
    if a not in ("first", "first_last", "none"):
        raise ValueError("brand.json character.appear must be first, first_last or none")
    return a


def write_js(project: Path) -> None:
    """Generate src/core/brand.js for a project from brand.json (re-run on every storyboard)."""
    c = dict(load()["character"])
    presets = c.pop("presets")
    if c["preset"] not in presets:
        raise ValueError(f"brand.json character.preset {c['preset']!r} not in {list(presets)}")
    c["look"], c["presets"] = presets[c["preset"]], presets
    js = ("// generated from brand/brand.json: edit that file, not this one\n"
          "export const BRAND = " + json.dumps({"character": c}, indent=2) + ";\n")
    (project / "src" / "core" / "brand.js").write_text(js, encoding="utf-8")


def apply_voice_fx(project: Path) -> None:
    """Optional ffmpeg filter on the narration (EQ/compression only: duration must not change)."""
    fx = (load()["voice"].get("fx") or "").strip()
    wav = project / "data" / "narration.wav"
    if not fx or not wav.exists():
        return
    tmp = wav.with_suffix(".fx.wav")
    p = subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-af", fx, str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("voice fx failed:\n" + p.stderr[-600:])
    os.replace(tmp, wav)


if __name__ == "__main__":
    print(PATH)
    print(json.dumps(load(), indent=2))