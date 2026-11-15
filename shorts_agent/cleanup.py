"""One-off cleanup: keep only the History niche (the 'new niche' option stays in the dashboard).
python -m shorts_agent.cleanup          shows what would be deleted
python -m shorts_agent.cleanup --yes    deletes it"""
from __future__ import annotations

import argparse
import shutil

from . import niche, store
from .config import PROJECTS_ROOT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--keep", default="history")
    a = ap.parse_args()
    if not (niche.DIR / f"{a.keep}.json").exists():
        raise SystemExit(f"niches/{a.keep}.json not found: nothing was changed")
    jobs = [dict(r) for r in store.db().execute("SELECT * FROM jobs")]
    drop = [j for j in jobs if (j.get("style") or "history") != a.keep]
    root = PROJECTS_ROOT.resolve()
    folders = []
    for j in drop:
        p = (root / j["slug"]).resolve() if j.get("slug") else None
        if p and p.parent == root and p.exists():
            folders.append(p)
    if root.exists():
        folders += [p for p in root.glob("_props-*") if p.is_dir()]         # temporary prop-preview projects
    files = [p for p in sorted(niche.DIR.glob("*.json")) if not p.stem.startswith("_") and p.stem != a.keep]
    print(f"Keeping: niche '{a.keep}' and {len(jobs) - len(drop)} of its job(s)")
    print(f"Jobs to delete ({len(drop)}):")
    for j in drop:
        print(f"  #{j['id']} [{j.get('style')}] {j['status']}: {j['topic']}")
    print(f"Project folders to delete ({len(folders)}):")
    for p in folders:
        print("  ", p)
    print(f"Niche files to delete ({len(files)}):")
    for p in files:
        print("  ", p)
    if not a.yes:
        print("\nDry run: nothing was deleted. Run again with --yes to delete.")
        return
    for p in folders:
        shutil.rmtree(p, ignore_errors=True)
    store.delete_jobs([j["id"] for j in drop])
    for p in files:
        p.unlink()
    niche.load.cache_clear()
    print("\nDone.")


if __name__ == "__main__":
    main()