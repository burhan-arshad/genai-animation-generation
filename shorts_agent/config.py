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


def _engine_default() -> Path:
    local = REPO / "engine"                       # the engine pack lives inside this repo
    return local if (local / "styles").exists() else REPO.parent / "faceless-shorts"


# The rendering engine pack: the folder that contains SKILL.md and styles/
SKILL_DIR = _path("SKILL_DIR", _engine_default())
# Where every video project (script, audio, shots, renders) is created
PROJECTS_ROOT = _path("PROJECTS_ROOT", HOME / "faceless-shorts")
# Python inside the engine's own virtualenv (Kokoro voice + Whisper live there)
_venv_py = "Scripts/python.exe" if os.name == "nt" else "bin/python"
SKILL_PY = _path("SKILL_PY", HOME / ".faceless-shorts" / "venv" / _venv_py)

# Render quality. The 3D renderer runs in headless Chrome; without a graphics card it is software rendering on the CPU.
PROFILES = {
    "preview": {"QS": "&res=0.25&aa=0&shadow=512&dof=0&bloom=0", "FPS": "24"},     # checks and contact sheets
    "draft": {"QS": "&res=0.4&aa=0&shadow=512&dof=0&bloom=0", "FPS": "20"},        # fastest real video
    "balanced": {"QS": "&res=0.6&aa=0&shadow=512&dof=0&bloom=0", "FPS": "24"},
    "quality": {"QS": "&res=1&aa=4&shadow=2048", "FPS": "30"},
}


def render_env(profile: str | None = None) -> dict[str, str]:
    p = profile or (os.getenv("RENDER_PROFILE") or "balanced")
    env = dict(PROFILES.get(p, PROFILES["balanced"]))
    if os.getenv("RENDER_SOFTWARE", "1") != "0":    # capture.mjs only checks that SOFTWARE_GL is set
        env["SOFTWARE_GL"] = "1"
    env["BOOT_SECONDS"] = os.getenv("BOOT_SECONDS", "600")
    return env


def proc_flags() -> int:
    """Windows: run the heavy render at below-normal priority so the laptop stays usable (RENDER_NICE=0 turns it off)."""
    if os.name != "nt" or os.getenv("RENDER_NICE", "1") == "0":
        return 0
    return 0x00004000                               # BELOW_NORMAL_PRIORITY_CLASS