"""Gemini voice: an expressive narrator (Gemini text-to-speech) that ACTS the story instead of reading it.
  1. a voice director (LLM) writes, for every script line, the emotion, energy, pace and a short acting note
     (data/voice_plan.json: the storyboard director reads it too, so the people on screen react the way the narrator feels);
  2. the lines are cut into 1-6 scenes at the places where the emotion changes (VOICE_SEGMENTS, default 5);
  3. every scene is spoken in ONE Gemini TTS request with the actor's character and the scene's direction;
  4. the scenes are joined into data/narration.wav (lead and outro silence added). words.py then finds every word with Whisper
     and rebuilds data/lines.json, exactly as it does for a recorded voice.
Any failure (no key, quota, strange audio) raises, and runner.py falls back to the local Kokoro voice for that video.
  python -m shorts_agent.gemini_voice voices | audition [Voice ...] | project <folder>"""
from __future__ import annotations

import array
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from pydantic import BaseModel

from . import brand, llm
from .config import REPO

RATE = 24000
DEFAULT_MODELS = "gemini-2.5-flash-preview-tts,gemini-2.5-pro-preview-tts"
MAX_TOTAL = 56.5                                   # seconds: qa.py rejects videos over 58 s
ASSETS = REPO / "brand" / "assets"

VOICES = {
    "Puck": "Upbeat", "Fenrir": "Excitable", "Sadachbia": "Lively", "Zephyr": "Bright", "Charon": "Informative", "Kore": "Firm", "Leda": "Youthful",
    "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going", "Autonoe": "Bright", "Enceladus": "Breathy", "Iapetus": "Clear", "Umbriel": "Easy-going",
    "Algieba": "Smooth", "Despina": "Smooth", "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative", "Laomedeia": "Upbeat", "Achernar": "Soft",
    "Alnilam": "Firm", "Schedar": "Even", "Gacrux": "Mature", "Pulcherrima": "Forward", "Achird": "Friendly", "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle",
    "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}
EMOTIONS = ["curious", "excited", "shocked", "amused", "tense", "awe", "mocking", "warm", "serious", "triumphant", "sad", "deadpan"]
ENERGIES = ["low", "medium", "high"]
PACES = ["slow", "normal", "fast"]
INTENSITY = {"subtle": "natural and restrained, small emotions", "normal": "expressive and lively, clear emotions", "dramatic": "theatrical, big emotions, strong contrasts"}
DEFAULT_PERSONA = ("the History Student: a quick-witted, warm young historian who tells true stories to a friend, curious, a little cheeky, "
                   "and genuinely amazed by the facts")
SAMPLE_TEXT = "In eighteen sixty-nine, workers digging a well found a giant stone man. But he was no ancient giant. He was a joke, and it started with an argument."
# narrator emotion -> the mood a person on screen shows (the storyboard director and the host's intro use it)
MOOD_FOR = {"curious": "think", "excited": "happy", "shocked": "shock", "amused": "laugh", "tense": "worried", "awe": "happy", "mocking": "smug",
            "warm": "happy", "serious": "neutral", "triumphant": "proud", "sad": "sad", "deadpan": "tired"}


class LineDirection(BaseModel):
    i: int
    emotion: str
    energy: str
    pace: str
    note: str


class VoicePlan(BaseModel):
    lines: list[LineDirection]


# ───────────── settings ─────────────
def settings() -> dict:
    v = brand.load().get("voice", {})
    return {"engine": str(v.get("engine", "gemini")), "voice": v.get("gemini_voice") if v.get("gemini_voice") in VOICES else "Puck",
            "persona": (v.get("persona") or DEFAULT_PERSONA).strip(), "intensity": v.get("intensity") if v.get("intensity") in INTENSITY else "normal",
            "direct": str(v.get("direct", "1")) not in ("0", "false", "False", "no")}


def wanted() -> bool:
    return settings()["engine"] == "gemini" and bool(os.getenv("GEMINI_API_KEY")) and (os.getenv("VOICE_ENGINE") or "gemini").lower() != "kokoro"


# ───────────── the voice director ─────────────
DIRECTOR = """You are a voice director. A narrator will record a short true-story video (about 45 seconds) for a young audience. For EVERY script line decide how it must be acted.
Think about what is happening in the story at that moment and what a great storyteller would feel: a hook that makes the viewer lean in, a calm set-up, tension building,
a turn that is a surprise, the big reveal, a dry joke, a punchline. The delivery must change from line to line: a monotone read is a failure.
For each line return: i (the line index), emotion (one of {emo}), energy (low, medium, high), pace (slow, normal, fast), note (at most 12 words of acting direction,
for example: "quiet, leaning in like a secret", "gasping, then fast", "dry, one beat of silence before the last word").
Rules: the hook lines are curious or tense with high energy and a quick pace; reveals slow down; jokes are deadpan or amused; the last line is warm or triumphant.
Never use the same emotion on more than three lines in a row. Intensity of the whole performance: {intensity}."""


def default_plan(lines: list[str]) -> VoicePlan:
    """Rules instead of an LLM: used when the director cannot be reached."""
    out, n = [], len(lines)
    for i, t in enumerate(lines):
        low = t.strip().lower()
        if i < 2:
            e, en, pc, note = ("curious" if i == 0 else "tense"), "high", "normal", "leaning in, hooking the viewer"
        elif i == n - 1:
            e, en, pc, note = "warm", "high", "normal", "a smile in the voice, a punchline"
        elif re.match(r"(but|until|suddenly|yet|except)\b", low):
            e, en, pc, note = "shocked", "high", "normal", "a turn: sudden, surprised"
        elif re.match(r"(then|so)\b", low):
            e, en, pc, note = "tense", "medium", "normal", "building, moving the story on"
        elif "?" in t:
            e, en, pc, note = "curious", "medium", "normal", "asking, genuinely wondering"
        elif i >= n - 4:
            e, en, pc, note = "amused", "medium", "slow", "letting the irony land"
        else:
            e, en, pc, note = "warm", "medium", "normal", "storyteller, clear and friendly"
        out.append(LineDirection(i=i, emotion=e, energy=en, pace=pc, note=note))
    return VoicePlan(lines=out)


def clean_plan(plan: VoicePlan, lines: list[str]) -> VoicePlan:
    by = {d.i: d for d in plan.lines}
    base = {d.i: d for d in default_plan(lines).lines}
    out = []
    for i in range(len(lines)):
        d = by.get(i) or base[i]
        out.append(LineDirection(i=i, emotion=d.emotion if d.emotion in EMOTIONS else base[i].emotion, energy=d.energy if d.energy in ENERGIES else "medium",
                                 pace=d.pace if d.pace in PACES else "normal", note=re.sub(r"\s+", " ", d.note).strip()[:90]))
    return VoicePlan(lines=out)


def make_plan(script: dict, direct: bool, intensity: str) -> tuple[VoicePlan, bool]:
    lines = [l["text"] for l in script["lines"]]
    if not direct:
        return default_plan(lines), False
    body = "\n".join(f"{i}: {t}" for i, t in enumerate(lines))
    try:
        p = llm.generate_structured(f"TITLE: {script.get('title', '')}\nSCRIPT:\n{body}\n\nDirect every line.", VoicePlan,
                                    system=DIRECTOR.format(emo=", ".join(EMOTIONS), intensity=INTENSITY[intensity]), temperature=0.7, task="storyboard")
        return clean_plan(p, lines), True
    except Exception as e:                           # quota or a bad answer: rules are better than no direction
        print(f"[voice] the voice director failed ({type(e).__name__}): using rule-based direction")
        return default_plan(lines), False


# ───────────── scenes ─────────────
def sentences(lines: list[str]) -> list[list[int]]:
    """Group the lines into whole sentences: a scene is never cut in the middle of one."""
    groups, cur = [], []
    for i, t in enumerate(lines):
        cur.append(i)
        if re.search(r'[.?!]["\')]*$', t.strip()) or i == len(lines) - 1:
            groups.append(cur)
            cur = []
    return groups


def scenes(plan: VoicePlan, lines: list[str], max_scenes: int) -> list[list[int]]:
    """Cut the sentences into at most max_scenes scenes where the emotion changes (the hook and the last line always stand alone when there is room)."""
    by = {d.i: d for d in plan.lines}
    groups = sentences(lines)
    if max_scenes <= 1 or len(groups) <= 1:
        return [[i for g in groups for i in g]]
    emo = lambda g: by[g[0]].emotion
    out: list[list[int]] = [list(groups[0])]
    for g in groups[1:]:
        if emo(g) != emo([out[-1][-1]]) and len(out[-1]) >= 2:
            out.append(list(g))
        else:
            out[-1].extend(g)
    while len(out) > max_scenes:                      # merge the smallest neighbouring pair
        k = min(range(len(out) - 1), key=lambda j: len(out[j]) + len(out[j + 1]))
        out[k:k + 2] = [out[k] + out[k + 1]]
    return out


def direction_for(plan: VoicePlan, idxs: list[int], intensity: str) -> str:
    by = {d.i: d for d in plan.lines}
    ds = [by[i] for i in idxs]
    emos = list(dict.fromkeys(d.emotion for d in ds))
    en = {"low": 1, "medium": 2, "high": 3}
    pace = max((d.pace for d in ds), key=lambda p: {"slow": 0, "normal": 1, "fast": 2}[p]) if len({d.pace for d in ds}) > 1 else ds[0].pace
    notes = "; ".join(f"{d.note}" for d in ds if d.note)[:360]
    return (f"{INTENSITY[intensity]}. Feelings in order: {' then '.join(emos)}. Energy {'rising' if en[ds[-1].energy] > en[ds[0].energy] else 'steady' if en[ds[-1].energy] == en[ds[0].energy] else 'settling'}, "
            f"pace {pace}, brisk Shorts narration. Line by line: {notes}")


def prompt_for(persona: str, direction: str, text: str, simple: bool = False) -> str:
    if simple:
        return f"Say this naturally, with real feeling, like a storyteller: {text}"
    return (f"You are voicing {persona}.\nPerformance for this part: {direction}\n"
            "Speak ONLY the words of the transcript below, exactly as written. Do not read these instructions.\n\nTranscript:\n" + text)


# ───────────── Gemini TTS ─────────────
def tts_call(model: str, prompt: str, voice: str) -> bytes:
    """One request to Gemini text-to-speech. Returns 16-bit mono PCM at 24 kHz."""
    from google import genai
    from google.genai import types
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise llm.Skip("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=key, http_options=llm._http_options(types))
    resp = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(
        response_modalities=["AUDIO"], temperature=0.9,
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
    part = resp.candidates[0].content.parts[0]
    data = part.inline_data.data
    if isinstance(data, str):
        import base64
        data = base64.b64decode(data)
    return bytes(data)


def synth(prompt_full: str, prompt_simple: str, voice: str, expected: float) -> bytes:
    models = [m.strip() for m in (os.getenv("GEMINI_TTS_MODELS") or os.getenv("GEMINI_TTS_MODEL") or DEFAULT_MODELS).split(",") if m.strip()]
    last: Exception | None = None
    for attempt in range(3):
        for spec in models:
            used, limit = llm._used_today(spec), llm._daily_limit(spec)
            if used >= limit - llm.SAFETY_MARGIN:
                last = llm.BudgetExceeded(f"{spec}: {used}/{limit} voice requests used today")
                continue
            try:
                pcm = tts_call(spec, prompt_full if attempt == 0 else prompt_simple, voice)
            except llm.Skip:
                raise
            except Exception as e:
                llm._log(spec, "tts", 0, 0, False)
                last = e
                print(f"[voice] {spec}: {type(e).__name__}: {str(e)[:140]}")
                if llm._classify(e) == "fatal":
                    continue
                time.sleep(2)
                continue
            secs = len(pcm) / 2 / RATE
            llm._log(spec, "tts", len(prompt_full) // 4, int(secs * 25), True)
            if expected * 0.5 <= secs <= expected * 2.0 + 2.0:
                return pcm
            last = RuntimeError(f"the voice returned {secs:.1f} s of audio for about {expected:.1f} s of text")
            print(f"[voice] {last}")
    raise last or RuntimeError("no voice model available")


# ───────────── audio ─────────────
def trim(pcm: bytes, thr: int = 450, keep: float = 0.05) -> bytes:
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    if not len(a):
        return pcm
    first = next((i for i, v in enumerate(a) if abs(v) > thr), 0)
    last = len(a) - 1 - next((i for i, v in enumerate(reversed(a)) if abs(v) > thr), 0)
    k = int(keep * RATE)
    return a[max(0, first - k): min(len(a), last + k)].tobytes()


def silence(sec: float) -> bytes:
    return bytes(int(sec * RATE) * 2)


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def fit_duration(path: Path, max_s: float = MAX_TOTAL) -> float:
    """A narration longer than the Shorts limit is sped up a little (pitch kept), up to 15%."""
    with wave.open(str(path), "rb") as w:
        dur = w.getnframes() / w.getframerate()
    if dur <= max_s:
        return dur
    ratio = min(1.15, dur / max_s)
    tmp = path.with_suffix(".fit.wav")
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-filter:a", f"atempo={ratio:.3f}", "-ar", str(RATE), "-ac", "1", str(tmp)], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("could not shorten the narration:\n" + p.stderr[-300:])
    os.replace(tmp, path)
    print(f"[voice] narration was {dur:.1f} s: sped up x{ratio:.2f}")
    return dur / ratio


# ───────────── the stage ─────────────
def synthesize(project: Path) -> float:
    """data/narration.wav + data/voice_plan.json for a project. Returns seconds taken. Raises on any failure (the caller falls back to Kokoro)."""
    t0 = time.time()
    project = Path(project)
    s = settings()
    script = json.loads((project / "script.json").read_text(encoding="utf-8"))
    lines = [l["text"] for l in script["lines"]]
    plan, directed = make_plan(script, s["direct"], s["intensity"])
    max_scenes = max(1, min(8, int(os.getenv("VOICE_SEGMENTS", "5") or 5))) if s["direct"] else 1
    cut = scenes(plan, lines, max_scenes)
    print(f"[voice] actor {s['voice']}, {len(cut)} scene(s), directed by {'the AI voice director' if directed else 'rules'}, intensity {s['intensity']}")
    pcm = silence(float(script.get("lead", 0.3)))
    for k, idxs in enumerate(cut):
        text = " ".join(lines[i] for i in idxs)
        words = len(text.split())
        d = direction_for(plan, idxs, s["intensity"])
        audio = trim(synth(prompt_for(s["persona"], d, text), prompt_for(s["persona"], d, text, simple=True), s["voice"], words / 2.8))
        print(f"[voice] scene {k + 1}/{len(cut)}: lines {idxs[0]}-{idxs[-1]}, {len(audio) / 2 / RATE:.1f} s")
        pcm += audio + silence(float(script.get("gap", 0.18)) + (0.12 if k < len(cut) - 1 else 0))
    pcm += silence(float(script.get("outro", 1.2)))
    (project / "data").mkdir(exist_ok=True)
    wav = project / "data" / "narration.wav"
    write_wav(wav, pcm)
    fit_duration(wav)
    for f in ("lines.json", "words.json", "words.txt"):          # words.py rebuilds them from the audio
        (project / "data" / f).unlink(missing_ok=True)
    (project / "data" / "voice_plan.json").write_text(json.dumps({"actor": s["voice"], "intensity": s["intensity"], "directed": directed, "scenes": cut,
                                                                 "lines": [d.model_dump() for d in plan.lines]}, indent=1), encoding="utf-8")
    return time.time() - t0


def load_plan(project: Path) -> dict[int, dict]:
    """The narrator's emotion per line, for the storyboard (empty when the project used another voice)."""
    f = Path(project) / "data" / "voice_plan.json"
    try:
        return {d["i"]: d for d in json.loads(f.read_text(encoding="utf-8"))["lines"]}
    except (OSError, ValueError, KeyError):
        return {}


# ───────────── dashboard and command line ─────────────
def sample(name: str, persona: str | None = None, intensity: str | None = None) -> Path:
    """A short audition of one actor, acting the first lines of a story (brand/assets/gemini_<Name>.wav)."""
    if name not in VOICES:
        raise ValueError("unknown voice")
    s = settings()
    persona, intensity = persona or s["persona"], intensity or s["intensity"]
    d = f"{INTENSITY[intensity]}. Feelings in order: curious, then tense, then amused. Pace normal, brisk Shorts narration."
    pcm = synth(prompt_for(persona, d, SAMPLE_TEXT), prompt_for(persona, d, SAMPLE_TEXT, simple=True), name, len(SAMPLE_TEXT.split()) / 2.8)
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / f"gemini_{name}.wav"
    write_wav(out, trim(pcm))
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["voices"]:
        for k, v in VOICES.items():
            print(f"{k:14s} {v}")
    elif a[:1] == ["audition"]:
        for name in (a[1:] or ["Puck", "Fenrir", "Sadachbia", "Charon", "Kore", "Sulafat"]):
            try:
                print(f"  {name}: ok -> {sample(name)}")
            except Exception as e:
                print(f"  {name}: failed ({type(e).__name__}: {str(e)[:120]})")
    elif a[:1] == ["project"] and len(a) == 2:
        print(f"done in {synthesize(Path(a[1])):.0f} s")
    else:
        print("usage: python -m shorts_agent.gemini_voice voices | audition [Voice ...] | project <folder>")
