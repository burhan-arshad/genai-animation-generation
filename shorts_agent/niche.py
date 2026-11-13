"""Niche packs: everything topic-specific lives in niches/<name>.json. Select one with NICHE in .env (default: history)."""
from __future__ import annotations
import re

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
    pr = data.get("props")
    if pr is not None:
        mode = pr.get("mode", "library") if isinstance(pr, dict) else None
        if mode not in ("library", "generate"):
            problems.append(f"{name}: props.mode must be 'library' or 'generate'")
        elif mode == "generate":
            if not str(pr.get("theme", "")).strip():
                problems.append(f"{name}: props.theme is required when props.mode is 'generate'")
            bad = [r for r in pr.get("required", []) if not re.fullmatch(r"[a-z][A-Za-z0-9]*", str(r)) or r in ("backdrop", "NC")]
            if bad:
                problems.append(f"{name}: props.required names must be camelCase identifiers (not backdrop/NC): {bad}")
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
