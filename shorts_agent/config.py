"""Central config: every path and setting comes from .env, nothing is hardcoded elsewhere."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()


def _path(name: str, default: Path) -> Path:
    """Empty or missing env var -> default (an empty value in .env must not become Path('.'))."""
    v = (os.getenv(name) or "").strip().strip('"')
    return Path(v).expanduser() if v else default


# The rendering engine pack (not part of this repo): the folder that contains SKILL.md and styles/
SKILL_DIR = _path("SKILL_DIR", REPO.parent / "faceless-shorts")
# Where every video project (script, audio, shots, renders) is created
PROJECTS_ROOT = _path("PROJECTS_ROOT", HOME / "faceless-shorts")
# Python inside the engine's own virtualenv (Kokoro voice + Whisper live there)
_venv_py = "Scripts/python.exe" if os.name == "nt" else "bin/python"
SKILL_PY = _path("SKILL_PY", HOME / ".faceless-shorts" / "venv" / _venv_py)