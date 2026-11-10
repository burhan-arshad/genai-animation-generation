"""Brand config: one JSON file drives the host character look, voice and audience note."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .config import REPO

PATH = REPO / "brand" / "brand.json"

DEFAULTS = {
    "channel": {
        "name": "TBD",
        "tagline": ""
    },
    "character": {
        "name": "History Student",
        "preset": "a",
        "appear": "first",
        "scale": 1.0,
        "presets": {
            "a": {
                "outfit": "tee",
                "skin": "#D9A273",
                "hair": "#2B2118",
                "hairStyle": "quiff",
                "glasses": True,
                "beard": False,
                "top": "#EBDDBF",
                "pants": "#6B4F34",
                "shoes": "#4A3425",
                "headphones": False,
                "accent": "#A8322D"
            },
            "b": {
                "outfit": "tee",
                "skin": "#EBC3A0",
                "hair": "#4A2D1B",
                "hairStyle": "short",
                "glasses": True,
                "beard": False,
                "top": "#C9A45C",
                "pants": "#3E4A5C",
                "shoes": "#6B4F34",
                "headphones": False,
                "accent": "#2F7F86"
            },
            "c": {
                "outfit": "tee",
                "skin": "#8D5A3B",
                "hair": "#1B1410",
                "hairStyle": "short",
                "glasses": False,
                "beard": False,
                "top": "#F3E9D2",
                "pants": "#5A4635",
                "shoes": "#2B2118",
                "headphones": False,
                "accent": "#C8952F"
            },
        },
    },
    "voice": {
        "name": "bm_george",
        "speed": 1.0,
        "music": "bed",
        "fx": ""
    },
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