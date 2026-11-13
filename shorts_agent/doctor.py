"""Environment check for new installs.  python -m shorts_agent.doctor [--ping]

--ping sends one tiny request to every model named in your chains (uses a little quota) to catch wrong names and bad keys."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import brand, llm, niche, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR, SKILL_PY

RESULTS: list[tuple[str, str, str]] = []
TASKS = ["research", "script", "factcheck", "storyboard", "storyboard_hard", "topics"]


def add(level: str, label: str, detail: str = "") -> None:
    RESULTS.append((level, label, detail))


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else ""
    except Exception as e:
        return f"error: {e}"


def check_tools() -> None:
    add("ok" if sys.version_info >= (3, 10) else "fail", "Python >= 3.10", sys.version.split()[0])
    node = shutil.which("node")
    if not node:
        add("fail", "Node.js 22+", "not found: install from nodejs.org")
    else:
        v = run(["node", "--version"])
        major = int(re.sub(r"\D.*", "", v.lstrip("v")) or 0)
        add("ok" if major >= 22 else "fail", "Node.js 22+", v)
    for tool in ("ffmpeg", "ffprobe"):
        add("ok" if shutil.which(tool) else "fail", tool, run([tool, "-version"]) if shutil.which(tool) else "not found: install FFmpeg and add it to PATH")
    chrome = [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "chrome")]
    chrome += [p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if os.path.exists(p)]
    chrome = [c for c in chrome if c]
    add("ok" if chrome else "warn", "Google Chrome (used by the renderer)", chrome[0] if chrome else "not found")


def check_engine() -> None:
    ok = (SKILL_DIR / "SKILL.md").exists() and (SKILL_DIR / "styles" / "paper-atlas" / "example" / "src" / "shots.js").exists()
    add("ok" if ok else "fail", "Engine pack folder (SKILL_DIR)", str(SKILL_DIR) if ok else
        f"{SKILL_DIR} does not look like the engine pack (needs SKILL.md and styles/). Set SKILL_DIR in .env")
    if SKILL_PY.is_file():
        try:
            r = subprocess.run([str(SKILL_PY), "-c", "import faster_whisper, kokoro_onnx, numpy"],
                               capture_output=True, text=True)
            add("ok" if r.returncode == 0 else "fail", "Voice + timing models (Kokoro, Whisper)",
                "importable" if r.returncode == 0 else "missing: run the engine pack's scripts/setup.sh (Git Bash on Windows)")
        except OSError as e:
            add("fail", "Engine Python (SKILL_PY)", f"{SKILL_PY} cannot be run: {e}")
    else:
        add("fail", "Engine Python (SKILL_PY)", f"{SKILL_PY} is not a file: set SKILL_PY in .env to the venv's python.exe")
    
    if SKILL_PY.exists():
        r = subprocess.run([str(SKILL_PY), "-c", "import faster_whisper, kokoro_onnx, numpy"], capture_output=True, text=True)
        add("ok" if r.returncode == 0 else "fail", "Voice + timing models (Kokoro, Whisper)",
            "importable" if r.returncode == 0 else "missing: run the engine pack's scripts/setup.sh (Git Bash on Windows)")
    else:
        add("fail", "Engine Python (SKILL_PY)", f"{SKILL_PY} not found: run the engine pack's scripts/setup.sh")
    try:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        add("ok", "Projects folder is writable", str(PROJECTS_ROOT))
    except OSError as e:
        add("fail", "Projects folder", str(e))


def provider_ready(spec: str) -> tuple[bool, str]:
    provider, _ = llm._split(spec)
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY")), "GEMINI_API_KEY"
    P = re.sub(r"\W", "_", provider).upper()
    return bool(os.getenv(f"PROVIDER_{P}_URL") and os.getenv(f"PROVIDER_{P}_KEY")), f"PROVIDER_{P}_URL and PROVIDER_{P}_KEY"


def check_llm(ping: bool) -> set[str]:
    specs: set[str] = set()
    if not (REPO / ".env").exists():
        add("fail", ".env file", "missing: copy .env.example to .env and fill it in")
    for task in TASKS:
        try:
            chain = llm._models_for(task)
        except RuntimeError as e:
            add("fail", f"model chain '{task}'", str(e))
            continue
        specs.update(chain)
        ready = [s for s in chain if provider_ready(s)[0]]
        add("ok" if ready else "fail", f"model chain '{task}'",
            " -> ".join(chain) + ("" if ready else "   (no model in this chain has its API key set)"))
    for s in sorted(specs):
        ok, need = provider_ready(s)
        if not ok:
            add("warn", f"model {s}", f"skipped at run time: {need} not set")
    if ping:
        for s in sorted(specs):
            if provider_ready(s)[0]:
                ok, msg = llm.ping(s)
                add("ok" if ok else "warn", f"ping {s}", msg)
    return specs


def check_config() -> None:
    try:
        key = styles.default_key()
        add("ok" if key in styles.STYLES else "fail", f"active niche '{key}'",
            "available: " + ", ".join(niche.available()))
    except Exception as e:
        add("fail", "niche", str(e))
    try:
        b = brand.load()
        ch = b["character"]
        add("ok" if ch["preset"] in ch["presets"] else "fail", "brand.json", f"channel '{b['channel']['name']}', preset '{ch['preset']}', host appears: {ch['appear']}")
    except Exception as e:
        add("fail", "brand.json", str(e))
    add("ok" if (REPO / "overlay").exists() else "fail", "overlay/ folder (host and scenery code)")
    add("ok" if (REPO / "client_secret.json").exists() else "warn", "YouTube client_secret.json", "needed only for uploading")
    add("ok" if (REPO / "token.json").exists() else "warn", "YouTube login (token.json)", "run: python -m shorts_agent.uploader login")
    add("ok" if os.getenv("SMTP_USER") and os.getenv("SMTP_APP_PASSWORD") else "warn", "e-mail alerts", "optional")


def check_hardcoded_paths() -> None:
    bad = []
    for p in (REPO / "shorts_agent").glob("*.py"):
        if p.name == "doctor.py":
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if re.search(r"\b[A-Z]:\\{1,2}[A-Za-z]|/Users/\w+", line) and "os.environ" not in line:
                bad.append(f"{p.name}:{n}")
    add("ok" if not bad else "warn", "no machine-specific paths in the code", ", ".join(bad[:6]) if bad else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ping", action="store_true", help="send one tiny request to every configured model")
    a = ap.parse_args()
    check_tools()
    check_engine()
    check_config()
    check_llm(a.ping)
    check_hardcoded_paths()
    tag = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    for level, label, detail in RESULTS:
        print(f"{tag[level]} {label}" + (f": {detail}" if detail else ""))
    fails = sum(1 for r in RESULTS if r[0] == "fail")
    print(f"\n{fails} problem(s) to fix." if fails else "\nEverything required is in place.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
