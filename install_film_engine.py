"""Run once from the repo root, after the new files are in place:   python install_film_engine.py
The film engine shares tools/ (capture.mjs, mix.py) and fonts/ with the Tall Tale engine: this copies them, writes the example's brand.js and checks the setup."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from shorts_agent import brand
from shorts_agent.config import SKILL_DIR

FILM = SKILL_DIR / "styles" / "film" / "example"
TALE = SKILL_DIR / "styles" / "tall-tale" / "example"


def main() -> int:
    if not (TALE / "tools" / "capture.mjs").exists():
        print(f"FAIL: {TALE / 'tools' / 'capture.mjs'} not found. Set SKILL_DIR in .env to the engine folder.")
        return 1
    if not (FILM / "src" / "core" / "film.js").exists():
        print(f"FAIL: {FILM / 'src' / 'core' / 'film.js'} not found: copy engine/styles/film first.")
        return 1
    shutil.copytree(TALE / "tools", FILM / "tools", dirs_exist_ok=True)
    (FILM / "fonts").mkdir(exist_ok=True)
    for f in ("Inter-Black.otf", "Inter-ExtraBold.otf"):
        shutil.copy(TALE / "fonts" / f, FILM / "fonts" / f)
    (FILM / "renders").mkdir(exist_ok=True)
    brand.write_js(FILM)
    ok = all((FILM / p).exists() for p in ("index.html", "script.json", "data/story.json", "src/main.js", "src/core/brand.js", "tools/capture.mjs", "fonts/Inter-Black.otf"))
    print("film engine installed:", FILM if ok else "INCOMPLETE")
    print("next: bash engine/scripts/selftest.sh   (must print SELFTEST PASSED), then: python -m shorts_agent.doctor")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
