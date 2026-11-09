"""Deterministic video QA with ffprobe/ffmpeg. No LLM, no quota."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MIN_DUR, MAX_DUR = 20.0, 58.0


def probe(video: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height:format=duration", "-of", "json", str(video)],
                       capture_output=True, text=True)
    info = json.loads(p.stdout or "{}")
    streams = info.get("streams", [])
    vid = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {"duration": float(info.get("format", {}).get("duration", 0) or 0),
            "width": vid.get("width"), "height": vid.get("height"),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def analyze(video: Path) -> dict:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-vf", "blackdetect=d=0.4:pix_th=0.06,freezedetect=n=-60dB:d=2",
         "-af", "silencedetect=noise=-50dB:d=1.5,ebur128=peak=true:framelog=quiet",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = p.stderr
    last = lambda pat: (re.findall(pat, err) or [None])[-1]
    f = lambda x: float(x) if x is not None else None
    return {"lufs": f(last(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS")),
            "peak_dbfs": f(last(r"Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS")),
            "freezes": [float(x) for x in re.findall(r"freeze_duration:\s*([\d.]+)", err)],
            "blacks": [float(x) for x in re.findall(r"black_duration:\s*([\d.]+)", err)],
            "silences": [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", err)]}


def run_qa(video: Path) -> dict:
    meta, a, issues = probe(video), analyze(video), []
    add = lambda lvl, msg: issues.append({"level": lvl, "msg": msg})
    if not MIN_DUR <= meta["duration"] <= MAX_DUR:
        add("FAIL", f"duration {meta['duration']:.1f}s outside {MIN_DUR:.0f}-{MAX_DUR:.0f}s")
    if (meta["width"], meta["height"]) != (1080, 1920):
        add("FAIL", f"resolution {meta['width']}x{meta['height']}, expected 1080x1920")
    if not meta["has_audio"]:
        add("FAIL", "no audio stream")
    if a["lufs"] is None:
        add("WARN", "could not measure loudness")
    elif not -20 <= a["lufs"] <= -11:
        add("WARN", f"integrated loudness {a['lufs']} LUFS (target about -14)")
    if a["peak_dbfs"] is not None and a["peak_dbfs"] > -1.0:
        add("WARN", f"peak {a['peak_dbfs']} dBFS is close to clipping")
    for name, key in (("silence", "silences"), ("black frames", "blacks"), ("frozen picture", "freezes")):
        if a[key]:
            add("WARN", f"{name}: {len(a[key])} segment(s), longest {max(a[key]):.1f}s")
    status = "failed" if any(i["level"] == "FAIL" for i in issues) else ("passed_with_warnings" if issues else "passed")
    return {"status": status, "meta": meta, "audio_video": a, "issues": issues}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--name", default="final")
    args = ap.parse_args()
    qa = run_qa(args.project / "renders" / f"{args.name}.mp4")
    (args.project / "qa.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    print(qa["status"], "|", qa["meta"])
    for i in qa["issues"]:
        print(f"  [{i['level']}] {i['msg']}")