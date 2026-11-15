from shorts_agent import director as D
from tests.test_director import five, mk_timing, story


def test_open_set_keeps_its_colours():
    s = D.StorySet.model_validate(D._set("pitch", "open", wall="#112233", motif="#445566", floor="#6DBB4A", ceiling="", sign="Stars"))
    out = D._sets([s], 1992, D.DEFAULT_ERA, [], set())[0]
    assert out["kind"] == "open" and out["top"] == "#112233" and out["ground"] == "#6DBB4A" and out["stars"] is True and out["hills"] == ""


def test_host_is_framed_with_the_focus():
    data, _, _ = D.build(story(five()), mk_timing(), 1914, "first")
    assert "host" in data["shots"][0]["focus"]


def test_callout_keeps_slashes():
    shots = five()
    shots[0]["callouts"] = [{"text": "70/25 overs", "word": "nineteen", "style": "pop"}]
    data, _, _ = D.build(story(shots), mk_timing(), 1914, "none")
    assert data["shots"][0]["callouts"][0]["text"] == "70/25 OVERS"


def test_too_many_closeups_is_a_problem():
    shots = [D._s(i, "main", "close", c, ["may"], [D._a("may", "center")]) for i, c in enumerate(["push_in", "crane_down", "truck_left", "orbit_left", "handheld"])]
    _, problems, _ = D.build(story(shots), mk_timing(), 1914, "none")
    assert any("close-ups" in p for p in problems)