"""Render the same two lines in several Kokoro voices so you can choose by ear."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from .config import PROJECTS_ROOT, REPO, SKILL_DIR, SKILL_PY

DEFAULT = ["bm_george", "bm_lewis", "bm_fable", "bm_daniel", "am_michael", "am_adam", "bf_emma"]
OUT = REPO / "brand" / "assets"


def make(voice: str) -> bool:
    proj = PROJECTS_ROOT / f"audition-{voice}"
    if proj.exists():
        shutil.rmtree(proj)
    shutil.copytree(SKILL_DIR / "styles" / "paper-atlas" / "example", proj)
    sj = proj / "script.json"
    s = json.loads(sj.read_text(encoding="utf-8"))
    s["voice"], s["lines"] = voice, s["lines"][:2]
    sj.write_text(json.dumps(s, indent=2), encoding="utf-8")
    p = subprocess.run([str(SKILL_PY), str(SKILL_DIR / "scripts" / "voice.py"), str(proj)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    wav = proj / "data" / "narration.wav"
    if p.returncode != 0 or not wav.exists():
        print(f"  {voice}: failed ({(p.stderr or p.stdout)[-150:].strip()})")
        return False
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(wav, OUT / f"voice_{voice}.wav")
    print(f"  {voice}: ok -> {OUT / ('voice_' + voice + '.wav')}")
    return True


if __name__ == "__main__":
    voices = sys.argv[1:] or DEFAULT
    ok = [v for v in voices if make(v)]
    print("\nListen to the files in", OUT, "then set voice.name in brand/brand.json. Working voices:", ok)