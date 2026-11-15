from shorts_agent import director as D


def mk_timing():
    spec = [("In nineteen fourteen a couple mailed their daughter", 0.3, 3.5), ("to her grandma", 3.7, 5.0), ("with stamps on her coat", 5.2, 7.4),
            ("The clerk checked the rules", 7.6, 9.4), ("and nothing said he could not do it", 9.6, 18.0)]
    lines, words = [], []
    for i, (txt, s, e) in enumerate(spec):
        lines.append({"i": i, "text": txt, "start": s, "end": e})
        ws = txt.split()
        step = (e - s) / len(ws)
        words += [{"w": w, "line": i, "s": s + k * step, "e": s + (k + 1) * step} for k, w in enumerate(ws)]
    return D.Timing(lines, words, 18.5)


def story(shots, sets=None, year=1914, cast=True):
    return D.Story.model_validate({
        "year": year,
        "cast": [{"id": "may", "look": D._look("#7FC8E8", kid=True)}, {"id": "dad", "look": D._look("#6FA35A")}] if cast else [],
        "sets": sets or [D._set("main", "street", dress=[D._d("car", 1, -3), D._d("barrel", -3, -1)])],
        "shots": shots})


def five():
    return [D._s(0, "main", "close", "push_in", ["may"], [D._a("may", "center", "happy", beats=[("mailed", "shock", "", "pop")])]),
            D._s(1, "main", "wide", "crane_down", ["dad"], [D._a("dad", "left")]),
            D._s(2, "main", "medium", "truck_left", ["may"], [D._a("may", "right")]),
            D._s(3, "main", "full", "orbit_left", ["dad"], [D._a("dad", "center")]),
            D._s(4, "main", "close", "handheld", ["may"], [D._a("may", "center")])]


def test_good_story_has_no_problems_and_resolves_times():
    data, problems, _ = D.build(story(five()), mk_timing(), 1914, "first")
    assert problems == []
    first = data["shots"][0]
    assert first["at"] == 0 and first["framing"] == "wide"                       # the host needs a wide first shot
    assert any(a["who"] == "host" for a in first["actors"])
    may = next(a for a in first["actors"] if a["who"] == "may")
    assert 0 < may["beats"][0]["t"] < 3.5
    assert [s["id"] for s in data["shots"]][:2] == ["S01", "S02"] and data["cues"][0]["type"] in ("whoosh", "pop")


def test_bad_values_are_cleaned_not_fatal():
    shots = five()
    shots[1]["framing"], shots[1]["camera"] = "banana", "spin"
    shots[2]["actors"].append(D._a("ghost", "center"))
    data, _, warns = D.build(story(shots), mk_timing(), 1914, "none")
    assert data["shots"][1]["framing"] == "medium" and data["shots"][1]["camera"] in D.CAMERAS
    assert all(a["who"] != "ghost" for s in data["shots"] for a in s["actors"]) and warns


def test_era_filter_and_street_flags():
    old, _, _ = D.build(story(five(), year=1850), mk_timing(), None, "none")
    assert [d["item"] for d in old["sets"][0]["dress"]] == ["barrel"] and old["era"]["cars"] is False
    new, _, _ = D.build(story(five(), year=1930), mk_timing(), None, "none")
    assert {d["item"] for d in new["sets"][0]["dress"]} == {"car", "barrel"} and new["era"]["cars"] is True


def test_long_shots_are_split():
    data, _, _ = D.build(story(five()), mk_timing(), 1914, "none")
    late = [s for s in data["shots"] if s["at"] >= 9.5]
    assert len(late) > 1 and all(s["end"] - s["at"] <= 5.0 for s in data["shots"])


def test_plain_mode_drops_scenery_and_overlays():
    shots = five()
    shots[0]["callouts"] = [{"text": "idaho 1914", "word": "idaho", "style": "label"}]
    data, _, _ = D.build(story(shots), mk_timing(), 1914, "none", plain=True)
    assert data["sets"][0]["dress"] == [] and all(s["callouts"] == [] for s in data["shots"])


def test_callouts_are_cleaned():
    shots = five()
    shots[0]["callouts"] = [{"text": "idaho <b>1914</b>", "word": "nineteen", "style": "weird"}]
    data, _, _ = D.build(story(shots), mk_timing(), 1914, "none")
    c = data["shots"][0]["callouts"][0]
    assert c["text"] == "IDAHO B1914/B" and c["style"] == "pop"


def test_missing_cast_is_a_problem_for_the_llm():
    _, problems, _ = D.build(story(five(), cast=False), mk_timing(), 1914, "none")
    assert any("cast" in p for p in problems)


def test_to_js_embeds_the_story():
    data, _, _ = D.build(story(five()), mk_timing(), 1914, "none")
    js = D.to_js(data)
    assert "buildFromStory" in js and '"shots"' in js and "__STORY__" not in js