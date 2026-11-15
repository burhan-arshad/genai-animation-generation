from shorts_agent import director as D
from shorts_agent import propgen as P
from tests.test_director import mk_timing, story


def parts(n=5):
    return [P._p("box", (1, 1, 1), (i, 0, 0)) for i in range(n)]


def test_blueprint_is_cleaned():
    probs = []
    r = P.PropSet.model_validate({"props": [
        {"name": "Stone Giant!", "desc": "a giant", "span": 99, "parts": parts() + [P._p("teapot", (1, 1, 1))]},
        {"name": "tiny", "desc": "x", "span": 1, "parts": parts(2)}]})
    out = P.clean_props(r.props, probs)
    assert list(out) == ["stone_giant"] and out["stone_giant"]["span"] == 12 and len(out["stone_giant"]["parts"]) == 5
    assert probs and "tiny" in probs[0]


def test_bad_slab_and_label_are_dropped():
    assert P.clean_part(P.Part.model_validate(P._p("slab", (0.1, 0, 0), pts=[(0, 0), (1, 1)]))) is None
    assert P.clean_part(P.Part.model_validate(P._p("label", (1, 1, 0), text=""))) is None
    assert P.clean_part(P.Part.model_validate(P._p("label", (1, 1, 0), text="SEE THE GIANT")))["text"] == "SEE THE GIANT"


def test_custom_objects_can_be_shown_and_are_required():
    shots = [D._s(i, "main", f, c, ["may"], [D._a("may", "center", "happy")], props=[("stone_giant", 2, -1, 1, "")])
             for i, (f, c) in enumerate([("close", "push_in"), ("wide", "crane_down"), ("medium", "truck_left"), ("full", "orbit_left"), ("close", "handheld")])]
    data, problems, _ = D.build(story(shots), mk_timing(), 1914, "none", custom={"stone_giant"}, need_props=True)
    assert problems == [] and all(s["props"][0]["name"] == "stone_giant" for s in data["shots"])
    shots2 = [D._s(0, "main", "close", "push_in", ["may"], [D._a("may", "center")])]
    _, problems2, _ = D.build(story(shots2), mk_timing(), 1914, "none", strict=False, custom={"stone_giant"}, need_props=True)
    assert any("nothing of the topic" in p for p in problems2)


def test_unknown_objects_are_dropped():
    shots = [D._s(0, "main", "close", "push_in", ["may"], [D._a("may", "center")], props=[("dragon", 0, 0, 1, "")])]
    data, _, warns = D.build(story(shots), mk_timing(), 1914, "none", strict=False)
    assert data["shots"][0]["props"] == [] and warns