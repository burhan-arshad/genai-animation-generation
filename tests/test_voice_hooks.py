import json
import wave
from pathlib import Path

import pytest

from shorts_agent import gemini_voice as gv
from shorts_agent import hooks


LINES = ["They dug up a ten-foot stone man in eighteen sixty-nine.", "But somebody had buried the giant there on purpose.", "And the reason is ridiculous.",
         "A cigar maker named George Hull", "argued with a preacher about giants in the Bible.", "So Hull decided to make one.", "He had a huge block of stone cut in Iowa,",
         "and a sculptor carved it into a giant.", "Then he buried it on a farm in Cardiff,", "for a whole year.", "Until diggers finally hit the stone foot.",
         "And the whole town went wild.", "People paid twenty-five cents to see him.", "But experts called him a fake.", "Even the showman P. T. Barnum built his own copy.",
         "Then Hull confessed. The giant was a hoax.", "Today he is still on display in Cooperstown.", "Would you have paid to see the giant?"]


# ───────────── hooks ─────────────
def test_good_script_passes_the_hook_checks():
    assert hooks.check(LINES) == []


def test_generic_and_vague_hooks_are_rejected():
    bad = ["Did you know that a long time ago something strange happened?"] + LINES[1:]
    assert any("generic" in p for p in hooks.check(bad))
    assert any("12 words" in p for p in hooks.check(["They dug up a ten-foot stone man and everybody in the whole town of Cardiff paid to look at it."] + LINES[1:]))


def test_a_weak_ending_and_no_turns_are_rejected():
    flat = LINES[:-1] + ["Anyway that was the story."]
    assert any("echo" in p for p in hooks.check(flat))
    no_turns = [LINES[0], LINES[1], LINES[2]] + ["He was a man. He made a giant. He hid it. It was found." for _ in range(10)] + [LINES[-1]]
    assert any("turn" in p for p in hooks.check(no_turns))


def test_formulas_rotate_and_avoid_recent_ones():
    seen = []
    h, e = [], []
    for i in range(12):
        a, b = hooks.pick(h, e, seed=i)
        assert a not in h[:4] and b not in e[:2]
        h.insert(0, a)
        e.insert(0, b)
        seen.append(a)
    assert len(set(seen)) >= 6


def test_job_id_from_project_folder():
    assert hooks.job_id_of(Path("D:/Shorts/012-the-cardiff-giant")) == 12 and hooks.job_id_of(Path("x")) is None


# ───────────── gemini voice ─────────────
def plan_of(emotions):
    return gv.VoicePlan(lines=[gv.LineDirection(i=i, emotion=e, energy="medium", pace="normal", note="n") for i, e in enumerate(emotions)])


def test_default_plan_varies_and_covers_every_line():
    p = gv.default_plan(LINES)
    assert [d.i for d in p.lines] == list(range(len(LINES)))
    assert len({d.emotion for d in p.lines}) >= 4 and p.lines[0].emotion == "curious" and p.lines[-1].emotion == "warm"


def test_scenes_follow_the_emotion_and_never_split_a_sentence():
    p = gv.clean_plan(gv.default_plan(LINES), LINES)
    cut = gv.scenes(p, LINES, 5)
    assert 2 <= len(cut) <= 5 and [i for c in cut for i in c] == list(range(len(LINES)))
    assert gv.scenes(p, LINES, 1) == [list(range(len(LINES)))]
    for c in cut:                                       # a scene ends where a sentence ends
        assert LINES[c[-1]].rstrip().endswith((".", "?", "!")) or c[-1] == len(LINES) - 1


def test_bad_plan_values_are_repaired():
    p = gv.clean_plan(plan_of(["furious", "curious"]), LINES[:4])
    assert len(p.lines) == 4 and all(d.emotion in gv.EMOTIONS for d in p.lines)


def test_prompt_never_asks_for_the_notes_to_be_read():
    pr = gv.prompt_for("the History Student", "excited, then tense", "Hello there.")
    assert "Do not read these instructions" in pr and pr.rstrip().endswith("Hello there.")


def fake_pcm(seconds):
    n = int(seconds * gv.RATE)
    return b"".join((3000 if (i // 40) % 2 else -3000).to_bytes(2, "little", signed=True) for i in range(n))


def test_synthesize_builds_the_narration_and_hands_over_to_whisper(tmp_path, monkeypatch):
    project = tmp_path
    (project / "data").mkdir()
    (project / "script.json").write_text(json.dumps({"title": "t", "lead": 0.3, "gap": 0.18, "outro": 1.2, "lines": [{"text": t} for t in LINES]}))
    for f in ("lines.json", "words.json"):
        (project / "data" / f).write_text("{}")
    calls = []

    def fake_tts(model, prompt, voice):
        calls.append((model, voice, prompt))
        words = len(prompt.split("Transcript:")[-1].split()) if "Transcript:" in prompt else len(prompt.split(":", 1)[-1].split())
        return fake_pcm(words / 2.8)

    monkeypatch.setattr(gv, "tts_call", fake_tts)
    monkeypatch.setattr(gv.llm, "_log", lambda *a, **k: None)
    monkeypatch.setattr(gv.llm, "_used_today", lambda s: 0)
    monkeypatch.setattr(gv, "make_plan", lambda script, direct, intensity: (gv.default_plan([l["text"] for l in script["lines"]]), False))
    monkeypatch.setattr(gv, "settings", lambda: {"engine": "gemini", "voice": "Puck", "persona": gv.DEFAULT_PERSONA, "intensity": "normal", "direct": True})
    gv.synthesize(project)
    assert 2 <= len(calls) <= 5 and all(c[1] == "Puck" for c in calls)
    with wave.open(str(project / "data" / "narration.wav")) as w:
        dur = w.getnframes() / w.getframerate()
    assert w.getframerate() == gv.RATE and 30 < dur < 60
    assert not (project / "data" / "lines.json").exists() and (project / "data" / "voice_plan.json").exists()
    assert gv.load_plan(project)[0]["emotion"] == "curious"


def test_a_failing_voice_raises_so_the_runner_can_use_kokoro(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "script.json").write_text(json.dumps({"title": "t", "lines": [{"text": t} for t in LINES]}))
    monkeypatch.setattr(gv, "tts_call", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(gv.llm, "_log", lambda *a, **k: None)
    monkeypatch.setattr(gv.llm, "_used_today", lambda s: 0)
    monkeypatch.setattr(gv.time, "sleep", lambda s: None)
    monkeypatch.setattr(gv, "make_plan", lambda script, direct, intensity: (gv.default_plan([l["text"] for l in script["lines"]]), False))
    with pytest.raises(RuntimeError):
        gv.synthesize(tmp_path)
    assert not (tmp_path / "data" / "narration.wav").exists()


def test_voice_is_not_wanted_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gv.wanted() is False


def test_long_narration_is_sped_up(tmp_path):
    f = tmp_path / "n.wav"
    gv.write_wav(f, fake_pcm(60.0))
    new = gv.fit_duration(f)
    assert new <= 56.6
