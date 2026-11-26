import datetime as dt

from shorts_agent import director as D
from shorts_agent import launch
from shorts_agent import topicgate as G
from tests.test_director import five, mk_timing, story


def test_evidence_must_match_the_topic():
    topic = "The Boston cop earthquake of 1925"
    wrong = [{"title": "1925 serum run to Nome", "text": "Sled dogs carried diphtheria serum across Alaska."}]
    right = [{"title": "1925 Charlevoix-Kamouraska earthquake", "text": "A strong earthquake shook Quebec and was felt in Boston."}]
    assert not G.evidence_ok(topic, wrong)[0] and G.evidence_ok(topic, right)[0]
    assert G.evidence_ok(topic, [{"url": "u", "text": "t"}])[0]                         # no titles to judge: not blocked


def test_script_must_mention_the_topic():
    assert G.script_misses("The Boston cop earthquake of 1925", "a dog sled raced through the snow") == ["boston", "earthquake"]
    assert G.script_misses("The Boston cop earthquake of 1925", "the earthquake shook the city") == []
    assert "too vague" in G.check_topic("history")


def test_effects_transitions_and_motion_are_cleaned():
    shots = five()
    shots[1] = D._s(1, "main", "wide", "crane_down", ["dad"], [D._a("dad", "left")], effect="Quake", transition="wipe",
                    props=[("water", 0, -1, 1, "", "", "rise")])
    shots[2] = D._s(2, "main", "medium", "truck_left", ["may"], [D._a("may", "right")], effect="volcano", transition="teleport")
    data, _, _ = D.build(story(shots), mk_timing(), 1914, "none")
    s1, s2 = data["shots"][1], data["shots"][2]
    assert s1["effect"] == "quake" and s1["transition"] == "wipe" and s1["props"][0]["move"] == "rise"
    assert s2["effect"] == "" and s2["transition"] == "cut"
    assert any(c["type"] == "rumble" for c in data["cues"])


def test_static_characters_are_a_problem_only_when_asked():
    _, problems, _ = D.build(story(five()), mk_timing(), 1914, "none")
    assert not any("static" in p for p in problems)
    shots = [D._s(i, "main", f, c, ["may"], [D._a("may", "center")]) for i, (f, c) in enumerate(
        [("wide", "push_in"), ("medium", "crane_down"), ("full", "truck_left"), ("wide", "orbit_left"), ("medium", "handheld")])]
    _, problems, _ = D.build(story(shots), mk_timing(), 1914, "none", need_acting=True)
    assert any("static" in p for p in problems)

