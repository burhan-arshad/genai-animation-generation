"""Niche packs: everything topic-specific lives in niches/<name>.json. Select one with NICHE in .env (default: history)."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from .config import REPO

DIR = REPO / "niches"
REQUIRED = {"writing": ["rules"], "topics": ["system", "block_regex"]}


def available() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.json") if not p.stem.startswith("_"))


def validate(name: str, data: dict) -> list[str]:
    problems = []
    for section, keys in REQUIRED.items():
        if not isinstance(data.get(section), dict):
            problems.append(f"{name}: missing section '{section}'")
            continue
        problems += [f"{name}: missing '{section}.{k}'" for k in keys if not data[section].get(k)]
    return problems


@lru_cache(maxsize=None)
def load(name: str | None = None) -> dict:
    name = name or os.getenv("NICHE") or "history"
    p = DIR / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"Unknown niche '{name}'. Available: {', '.join(available()) or 'none'} (folder: {DIR})")
    data = json.loads(p.read_text(encoding="utf-8"))
    bad = validate(name, data)
    if bad:
        raise SystemExit("Invalid niche file:\n- " + "\n- ".join(bad))
    return data
