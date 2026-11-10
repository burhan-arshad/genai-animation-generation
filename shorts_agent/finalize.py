"""Loudness-normalise the render (video stream copied, not re-encoded) and cut a cover frame."""
from __future__ import annotations

import subprocess
from pathlib import Path


def finalize(project: Path, src: str = "final", dst: str = "final_norm") -> Path:
    r = project / "renders"
    out = r / f"{dst}.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(r / f"{src}.mp4"), "-c:v", "copy",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("loudness step failed:\n" + p.stderr[-800:])
    subprocess.run(["ffmpeg", "-y", "-ss", "2.0", "-i", str(out), "-frames:v", "1", "-q:v", "2",
                    str(r / "cover.jpg")], capture_output=True)
    return out