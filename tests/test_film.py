import json
import re
from pathlib import Path

import pytest

from shorts_agent import filmboard as F
from shorts_agent.director import Timing

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "styles" / "film" / "example" / "src" / "core"
A, B, Pr, S, L = F._actor, F._beat, F._prop, F._shot, F._look


def js_list(file: str, name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[(.*?)\];", (ENGINE / file).read_text(encoding="utf-8"), re.S)
    return re.findall(r"'([^']+)'", m.group(1))


def timing(n=12, each=3.0):
    lines, words = [], []
    for i in range(n):
        s, e = 0.3 + i * each, 0.3 + (i + 1) * each - 0.2
        lines.append({"i": i, "text": f"line {i} word{i} stone", "start": s, "end": e})
        for k, w in enumerate(["line", str(i), f"word{i}", "stone"]):
            words.append({"w": w, "line": i, "s": s + k * (e - s) / 4, "e": s + (k + 1) * (e - s) / 4})
    return Timing(lines, words, 0.3 + n * each + 1.0)


def good_draft(lines=range(2, 10), **over):
    cast = [L("amy", "#7FC8E8", hat="bonnet", hatCol="#F4EAD0", hairStyle="long", dress=True), L("bob", "#C98B2E", pattern="vest", hat="cap", extra=["mustache"])]
    sets = [{"id": "a", "kind": "field", "time": "day", "sign": "", "deck": False, "dress": [{"item": "barn", "x": 80, "d": 0, "s": 1.0}]},
            {"id": "b", "kind": "street", "time": "dusk", "sign": "SHOP", "deck": False, "dress": []}]
    cams = ["push_in", "pan_right", "pull_out", "drift", "crane_down", "handheld", "punch_in", "pan_left"]
    frs = ["wide", "medium", "full", "medium", "wide", "full", "medium", "wide"]
    shots = []
    for i, ln in enumerate(lines):
        shots.append(S(ln, "", "ab"[i % 2], frs[i % 8], cams[i % 8], 50, "cut", "none", "none",
                       [A("amy", 30, 45 if i % 2 else 30, face="r", mood="happy", arms="present", talk=True, beats=[B("stone", "shock", "both_up", "jump")]), A("bob", 70, face="l", mood="smug", arms="hip")],
                       [Pr("barrel", 55, 1, 1.0, "stone", "rise" if i % 2 else "drop")], [{"text": f"YEAR {i}", "word": "stone", "style": "label"}], "scene"))
    d = {"title": "The Test Story Here", "place": "Idaho", "date": "1914", "intro_lines": 2, "outro_lines": 2, "intro_prop": "scroll", "outro_stamp": "HOAX",
         "cast": cast, "sets": sets, "custom_props": [], "shots": shots}
    d.update(over)
    return F.StoryDraft.model_validate(d)


def test_vocabulary_matches_the_engine():
    props_js = (ENGINE / "props.js").read_text(encoding="utf-8")
    block = props_js[props_js.index("export const P = {"):props_js.index("// ---- custom props")]
    names = set(re.findall(r"^  (\w+)\(g, o\)", block, re.M))
    assert names == set(F.PROPS)
    arms = re.search(r"export const ARMS = \{(.*?)\};", (ENGINE / "people.js").read_text(encoding="utf-8"), re.S).group(1)
    assert set(re.findall(r"(\w+): \[", arms)) >= set(F.ARMS)
    assert js_list("people.js", "MOODS") == F.MOODS and js_list("people.js", "HATS") == F.HATS and js_list("people.js", "HAIRS") == F.HAIRS
    assert js_list("people.js", "NECKS") == F.NECKS and js_list("people.js", "PATTERNS") == F.PATTERNS and js_list("people.js", "EXTRAS") == F.EXTRAS
    assert js_list("film.js", "CAMERAS") == F.CAMERAS and js_list("film.js", "TRANSITIONS") == F.TRANSITIONS and js_list("film.js", "ACTS") == [a for a in F.ACTS if a]
    assert js_list("film.js", "PROP_MOVES") == F.MOVES and js_list("film.js", "EFFECTS") == F.EFFECTS
    assert set(js_list("worlds.js", "KINDS")) == set(F.SET_KINDS) | {"study"} and js_list("worlds.js", "TIMES") == F.TIMES


def test_good_draft_becomes_a_story_without_problems():
    tm = timing()
    story, problems, warns = F.build(good_draft(), tm)
    assert problems == [] and warns == []
    shots = story["shots"]
    assert shots[0]["at"] == 0 and shots[-1]["end"] == round(tm.dur, 3)
    assert all(a["end"] == b["at"] for a, b in zip(shots, shots[1:])) or all(a["end"] <= b["at"] + 1e-6 for a, b in zip(shots, shots[1:]))
    assert [s["id"] for s in shots][:2] == ["S01", "S02"]
    assert shots[0]["set"] == "study" and shots[0]["actors"][0]["who"] == "hero" and shots[-1]["set"] == "study"
    assert any(c["style"] == "title" for c in shots[0]["callouts"]) and any(c["style"] == "stamp" for c in shots[-1]["callouts"])
    assert shots[2]["at"] == round(tm.start(2), 3)
    beat = shots[2]["actors"][0]["beats"][0]
    assert shots[2]["at"] <= beat["t"] <= shots[2]["end"] and beat["arms"] == {"l": "both_up", "r": "both_up"}
    assert "study" in story["sets"] and story["cast"].keys() == {"amy", "bob"}


def test_unknown_names_are_dropped_not_fatal():
    d = good_draft()
    d.shots[0].props[0].name = "dragon"
    d.shots[1].actors[0].who = "ghost"
    d.shots[2].framing, d.shots[2].camera = "banana", "spin"
    story, problems, warns = F.build(d, timing())
    assert any("dragon" in w for w in warns) and any("ghost" in w for w in warns)
    assert story["shots"][4]["framing"] in F.FRAMINGS and story["shots"][4]["camera"] in F.CAMERAS


def test_missing_objects_motion_and_callouts_are_fixed_in_code():
    d = good_draft()
    for s in d.shots:
        s.props, s.callouts = [], []
    story, problems, warns = F.build(d, timing())
    body = [s for s in story["shots"] if s["set"] != "study"]
    assert not any("objects" in p or "motion" in p or "callouts" in p.lower() for p in problems)
    shown = lambda s: s["props"] or story["sets"][s["set"]].get("dress")
    assert all(shown(s) for s in body)
    assert sum(1 for s in body for p in s["props"] if p["move"] not in ("pop", "none")) >= 2
    assert any(s["callouts"] for s in body) and warns


def test_people_are_still_required():
    d = good_draft()
    for s in d.shots:
        s.actors = []
    _, problems, _ = F.build(d, timing())
    assert any("People" in p for p in problems)

def test_missing_lines_are_filled_in_code():
    d = good_draft()
    d.shots = d.shots[:3]
    story, problems, warns = F.build(d, timing())
    assert not any("has no shot" in p for p in problems) and any("had no shot" in w for w in warns)
    assert len([s for s in story["shots"] if s["set"] != "study"]) >= 8


def test_long_shots_are_split():
    d = good_draft()
    d.shots = [d.shots[0]] + d.shots[2:] if False else d.shots
    tm = timing(n=12, each=3.0)
    d.shots = d.shots[:1] + d.shots[2:]            # shot for line 3 is gone: line 2's shot now lasts about 6 s
    story, _, _ = F.build(d, tm)
    assert all(s["end"] - s["at"] <= F.MAX_SHOT + 0.01 for s in story["shots"])


def test_custom_props_are_cleaned():
    d = good_draft(custom_props=[{"name": "Phono Graph!", "span": 9999, "parts": [
        {"shape": "rect", "x": 0, "y": 10, "w": 60, "h": 10, "rot": 0, "color": "#8C5A3A", "text": "", "pts": []},
        {"shape": "circle", "x": 0, "y": 40, "w": 30, "h": 30, "rot": 0, "color": "nope", "text": "", "pts": []},
        {"shape": "poly", "x": 0, "y": 0, "w": 1, "h": 1, "rot": 0, "color": "#F4C542", "text": "", "pts": [[0, 0], [10, 0], [5, 20]]},
        {"shape": "poly", "x": 0, "y": 0, "w": 1, "h": 1, "rot": 0, "color": "#F4C542", "text": "", "pts": [[0, 0]]}]}])
    d.intro_prop = "phono_graph"
    story, problems, warns = F.build(d, timing())
    assert "phono_graph" in story["custom"] and len(story["custom"]["phono_graph"]["parts"]) == 3 and story["custom"]["phono_graph"]["span"] == 700
    assert story["shots"][0]["panel"]["prop"] == "phono_graph"


def test_safe_mode_story_is_valid():
    tm = timing()
    story, _, _ = F.build(F.fallback(tm, {"title": "A Plain Story"}), tm)
    assert len(story["shots"]) == len(tm.lines) and story["shots"][0]["set"] == "study"


HOOK = {"text": "A 10-FOOT STONE MAN?", "end_question": "WOULD YOU HAVE PAID?"}


def test_cold_open_loop_and_end_question():
    tm = timing()
    story, problems, _ = F.build(good_draft(), tm, hook=HOOK, appear="first_last", cold=2.0, loop=True)
    shots = story["shots"]
    assert problems == []
    assert shots[0]["framing"] == "panel" and shots[0]["actors"] == [] and shots[0]["callouts"][0]["text"] == HOOK["text"] and shots[0]["end"] == 1.3
    assert shots[1]["actors"][0]["who"] == "hero" and shots[1]["at"] == 1.3                     # the host walks in after the cold open
    assert shots[-1]["framing"] == "panel" and shots[-1]["end"] == round(tm.dur, 3) and round(shots[-1]["end"] - shots[-1]["at"], 3) == 1.0
    assert any(c["text"] == HOOK["end_question"] for s in shots for c in s["callouts"])
    assert all(a["end"] <= b["at"] + 1e-6 for a, b in zip(shots, shots[1:]))


def test_host_setting_is_respected():
    tm = timing()
    first, p1, _ = F.build(good_draft(lines=range(2, 12)), tm, hook=HOOK, appear="first", cold=2.0, loop=True)
    assert p1 == [] and [s for s in first["shots"] if s["note"] == "host closes the story"] == []
    assert any(c["text"] == HOOK["end_question"] for s in first["shots"] for c in s["callouts"])      # the question still appears
    none, p2, _ = F.build(good_draft(lines=range(0, 12)), tm, hook=HOOK, appear="none", cold=2.0, loop=True)
    assert all(s["set"] != "study" for s in none["shots"]) and none["shots"][0]["at"] == 0.0 and none["shots"][-1]["end"] == round(tm.dur, 3)
    assert min(s["at"] for s in none["shots"]) == 0.0


def test_the_hosts_mood_follows_the_narrators_emotion():
    tm = timing()
    plan = {0: {"emotion": "shocked"}, 1: {"emotion": "amused"}, tm.lines[-1]["i"]: {"emotion": "triumphant"}}
    story, _, _ = F.build(good_draft(), tm, plan=plan)
    moods = [s["actors"][0]["mood"] for s in story["shots"] if s["set"] == "study"]
    assert moods[0] == "shock" and moods[1] == "laugh"


def test_default_build_has_no_cold_open_or_loop():
    story, _, _ = F.build(good_draft(), timing())
    assert all(s["framing"] != "panel" for s in story["shots"])

def test_a_long_line_is_split_not_rejected():
    tm = timing(n=12, each=8.0)                  # every line is about 8 s long
    story, problems, _ = F.build(good_draft(lines=range(2, 10)), tm)
    assert not any("has no shot" in p for p in problems)
    body = [s for s in story["shots"] if s["set"] != "study"]
    assert body and all(s["end"] - s["at"] <= F.MAX_SHOT + 0.01 for s in body)

def test_only_a_coin_may_spin():
    d = good_draft()
    d.shots[0].props[0].name, d.shots[0].props[0].move = "globe", "spin"
    d.shots[1].props[0].name, d.shots[1].props[0].move = "coin", "spin"
    story, _, _ = F.build(d, timing())
    moves = {p["name"]: p["move"] for s in story["shots"] for p in s["props"] if p["name"] in ("globe", "coin")}
    assert moves["globe"] == "grow" and moves["coin"] == "spin"

def test_extra_mystery_objects_need_no_ai_drawing():
    d = good_draft()
    d.shots[0].props[0].name = "lifeboat"
    d.shots[1].props[0].name = "boat"                       # an alias of lifeboat
    d.intro_prop = "lantern"
    story, problems, warns = F.build(d, timing())
    assert not any("lifeboat" in w or "'boat'" in w for w in warns)
    names = {p["name"] for s in story["shots"] for p in s["props"]}
    assert "lifeboat" in names and "boat" not in names
    assert story["custom"]["lifeboat"]["parts"] and "lantern" in story["custom"]


def test_the_extra_objects_follow_the_blueprint_rules():
    for n, c in F.EXTRA_PROPS.items():
        assert c["name"] == n and 60 <= c["span"] <= 700 and len(c["parts"]) >= 3
        for p in c["parts"]:
            assert p["shape"] in F.SHAPES and re.fullmatch(r"#[0-9a-fA-F]{6}", p["color"])
            assert -60 <= p["x"] <= 60 and -10 <= p["y"] <= 160
            assert p["shape"] != "poly" or len(p["pts"]) >= 3