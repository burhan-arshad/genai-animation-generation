"""Loudness-normalise the render (video stream copied, not re-encoded) and cut a cover frame.
LONGFORM_WIDE=1 (long episodes): the vertical film is put in the middle of a 1920x1080 frame with a blurred copy of itself behind it."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

WIDE = ["-filter_complex", "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=40:6[bg];[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]


def finalize(project: Path, src: str = "final", dst: str = "final_norm") -> Path:
    r = project / "renders"
    out = r / f"{dst}.mp4"
    vid = WIDE if os.getenv("LONGFORM_WIDE") == "1" else ["-c:v", "copy"]
    cmd = ["ffmpeg", "-y", "-i", str(r / f"{src}.mp4"), *vid,
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("loudness step failed:\n" + p.stderr[-800:])
    subprocess.run(["ffmpeg", "-y", "-ss", "2.0", "-i", str(out), "-frames:v", "1", "-q:v", "2",
                    str(r / "cover.jpg")], capture_output=True)
    return out