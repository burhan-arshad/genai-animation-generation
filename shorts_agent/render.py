"""Parallel render: the film is cut into time slices, each slice is drawn by its own browser, then the slices are joined and
muxed with the finished mix. A finished slice is kept (.ok), so a stopped render resumes where it stopped."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import proc_flags, render_env


def workers() -> int:
    try:
        w = int(os.getenv("RENDER_WORKERS", "2") or 2)
    except ValueError:
        w = 2
    return max(1, min(4, w, (os.cpu_count() or 2) // 2 or 1))


def _ff(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + p.stderr[-400:])


def render_parallel(project: Path, out_name: str = "final") -> float:
    from .runner import StageError
    t0 = time.time()
    n, env = workers(), {**os.environ, **render_env(project=project)}
    fps = float(env["FPS"])
    dur = float(json.loads((project / "data" / "lines.json").read_text(encoding="utf-8"))["duration"])
    total = round(dur * fps)
    cuts = [round(total * k / n) for k in range(n + 1)]
    seg = project / "renders" / "seg"
    seg.mkdir(parents=True, exist_ok=True)
    (project / "logs").mkdir(exist_ok=True)
    print(f"[video] {n} parallel workers, {total} frames at {fps:g} fps", flush=True)
    running = []
    for k in range(n):
        if (seg / f"s{k}.ok").exists() and (seg / f"s{k}.mp4").exists():
            continue
        log = open(project / "logs" / f"video{k}.log", "w")
        cmd = ["node", "tools/capture.mjs", "video", f"renders/seg/s{k}.mp4", f"{cuts[k] / fps:.4f}", f"{cuts[k + 1] / fps:.4f}"]
        running.append((k, subprocess.Popen(cmd, cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=proc_flags()), log))
    for k, p, log in running:
        rc = p.wait()
        log.close()
        if rc != 0:
            raise StageError(f"render slice {k} failed (exit {rc}). See logs/video{k}.log")
        (seg / f"s{k}.ok").write_text("ok")
    (seg / "list.txt").write_text("".join(f"file 's{k}.mp4'\n" for k in range(n)), encoding="utf-8")
    joined = project / "renders" / "video_only.mp4"
    _ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(seg / "list.txt"), "-map", "0:v", "-c", "copy", str(joined)])
    mix = project / "data" / "mix.wav"
    out = project / "renders" / f"{out_name}.mp4"
    if mix.exists():
        _ff(["ffmpeg", "-y", "-i", str(joined), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", str(out)])
    else:
        shutil.copy(joined, out)
    shutil.rmtree(seg, ignore_errors=True)
    joined.unlink(missing_ok=True)
    return time.time() - t0