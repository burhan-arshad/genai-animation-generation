"""Disk cleanup. python -m shorts_agent.cleanup MODE [--days N] [--yes]   (a dry run unless --yes)
temp = test leftovers | dead = dropped/rejected videos | slim = big files of finished videos | old = whole folders of old uploaded videos"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from . import store
from .config import PROJECTS_ROOT

HEAVY = ["review", "logs", "renders/seg", "renders/final.mp4", "renders/video_only.mp4", "renders/clip.mp4", "data/narration.wav", "data/mix.wav"]
DEFAULT_DAYS = {"temp": 0, "dead": 0, "slim": 7, "old": 30}


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def _folder(root: Path, job: dict):
    p = (root / job["slug"]).resolve() if job.get("slug") else None
    return p if p and p.parent == root and p.exists() else None


def _plan(mode: str, days: int) -> list[tuple]:
    """-> [(path or None, job id to delete or None)]"""
    root = PROJECTS_ROOT.resolve()
    jobs = [dict(r) for r in store.db().execute("SELECT * FROM jobs")]
    old = lambda j: (time.time() - (j.get("updated") or 0)) / 86400 >= days
    items: list[tuple] = []
    if mode == "temp" and root.exists():
        items += [(p, None) for p in [root / "demo-tall-tale", root / "brand-assets", *root.glob("_props-*")] if p.exists()]
    elif mode == "dead":
        items += [(_folder(root, j), j["id"]) for j in jobs if j["status"] in ("dropped", "rejected")]
    elif mode == "slim":
        for j in jobs:
            f = _folder(root, j)
            if f and j["status"] in ("uploaded", "dropped", "rejected") and old(j):
                items += [(f / h, None) for h in HEAVY if (f / h).exists()]
    elif mode == "old":
        items += [(_folder(root, j), None) for j in jobs if j["status"] == "uploaded" and old(j) and _folder(root, j)]
    return items


def scan() -> dict:
    out = {}
    for mode, days in DEFAULT_DAYS.items():
        items = _plan(mode, days)
        out[mode] = {"count": len(items), "bytes": sum(_size(p) for p, _ in items if p), "days": days}
    root = PROJECTS_ROOT
    out["total_bytes"] = _size(root) if root.exists() else 0
    return out


def apply(mode: str, days: int | None = None) -> dict:
    if mode not in DEFAULT_DAYS:
        raise ValueError("unknown cleanup mode")
    items = _plan(mode, DEFAULT_DAYS[mode] if days is None else days)
    freed = sum(_size(p) for p, _ in items if p)
    for p, _ in items:
        if p and p.exists():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    store.delete_jobs([j for _, j in items if j])
    return {"removed": len(items), "bytes": freed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=list(DEFAULT_DAYS))
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    items = _plan(a.mode, DEFAULT_DAYS[a.mode] if a.days is None else a.days)
    for p, j in items:
        print(f"  {_size(p) / 1048576:7.1f} MB  {p}" + (f"  (job #{j} is deleted too)" if j else ""))
    print(f"{len(items)} item(s), {sum(_size(p) for p, _ in items if p) / 1048576:.0f} MB")
    if a.yes:
        print("Done:", apply(a.mode, a.days))
    else:
        print("Dry run: add --yes to delete.")