"""Central config: paths and settings come from .env, nothing hardcoded elsewhere."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = Path(os.getenv("SKILL_DIR", r"D:\AntiGravity\faceless-shorts"))
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", str(Path.home() / "faceless-shorts")))
SKILL_PY = Path(os.getenv("SKILL_PY", str(Path.home() / ".faceless-shorts" / "venv" / "Scripts" / "python.exe")))