from shorts_agent import analytics as A
from shorts_agent import hooks
from shorts_agent import script_agent as S


def row(i, pct, views, **kw):
    r = {"id": i, "topic": f"Case {i}", "privacy": "public", "published": "2026-01-01T00:00:00Z", "views": views, "views7": views, "avg_pct": pct, "pct7": pct,
         "likes": 5, "comments": 1, "shares": 1, "kind": "hoax", "hook_words": 8, "hook_number": 0, "hook_contrast": 0, "hook_question": 0,
         "hook_year_first": 0, "end_question": 0, "avg_shot_s": 3.0, "moving_props": 3, "night_pct": 50, "closeup_pct": 10, "callouts": 4,
         "duration": 40, "music": "mystery", "voice": "Charon", "hook_line": "x", "hook_type": "", "end_type": "", "published_hour": 18}
    r.update(kw)
    return r


def test_kind_of():
    assert A.kind_of("The Piltdown Man Hoax") == "hoax" and A.kind_of("The Voynich Manuscript") == "code"
    assert A.kind_of("The Mary Celeste Abandonment") == "vanished" and A.kind_of("The Theft of the Mona Lisa") == "theft"
    assert A.kind_of("an unsolved mystery: the missing piece") == "unsolved" and A.kind_of("a mystery that was finally solved") == "solved"


def test_the_better_video_scores_higher():
    rows = [row(1, 40, 100), row(2, 70, 900), row(3, 55, 400)]
    A.with_perf(rows)
    assert rows[1]["perf"] > rows[2]["perf"] > rows[0]["perf"]


def test_insights_find_the_better_kind():
    rows = [row(i, 80, 900, kind="hoax") for i in range(4)] + [row(i + 10, 30, 100, kind="vanished") for i in range(4)]
    A.with_perf(rows)
    f = [x for x in A.insights(rows)["findings"] if x["key"] == "kind"]
    assert f and f[0]["best"] == "hoax" and f[0]["worst"] == "vanished"


def test_no_learning_before_enough_videos(monkeypatch):
    rows = [row(i, 50 + i, 100 + i) for i in range(3)]
    A.with_perf(rows)
    monkeypatch.setattr(A, "dataset", lambda: rows)
    monkeypatch.setenv("LEARN_MIN_VIDEOS", "8")
    assert A.hints("topic") == "" and A.preferred_kind() is None


def test_csv_export(monkeypatch):
    rows = [row(1, 50, 100), row(2, 60, 200)]
    A.with_perf(rows)
    monkeypatch.setattr(A, "dataset", lambda: rows)
    lines = A.export_csv().strip().splitlines()
    assert len(lines) == 3 and "topic" in lines[0] and "perf" in lines[0]


def test_hook_score_prefers_concrete_contradictions():
    assert hooks.score_hook("The table was set. Nobody was aboard.", "The coffee was still warm.") > hooks.score_hook("In eighteen seventy-two a ship was found drifting at sea", "")


def test_hook_ok_rejects_generic_and_long():
    assert hooks.hook_ok("Did you know ships can vanish", "") == "generic opener"
    assert hooks.hook_ok("word " * 14, "") and hooks.hook_ok("The ship was empty. Nobody knew why.", "") == ""


def test_the_better_formula_is_preferred_when_there_is_data(monkeypatch):
    monkeypatch.setenv("LEARN_EXPLORE", "0")
    assert hooks.pick([], [], seed=1, weights={"hooks": {"cold_open": 0.9, "challenge": 0.2}, "ends": {}})[0] == "cold_open"


def test_pick_hook_takes_the_best_valid_hook(monkeypatch):
    items = [{"id": "E1", "title": "T", "text": "The ship was found in 1872 with nobody aboard."}]
    good = S.HookIdea(line0="The table was set. Nobody was aboard.", line1="The coffee was still warm.", formula="a", evidence=["E1"], numbers=[])
    weak = S.HookIdea(line0="Did you know ships vanish", line1="x", formula="b", evidence=["E1"], numbers=[])
    wrong = S.HookIdea(line0="Nobody was aboard in 1999.", line1="Why?", formula="c", evidence=["E1"], numbers=["1999"])
    monkeypatch.setattr(S, "generate_structured", lambda *a, **k: S.HookList(hooks=[weak, wrong, good]))
    import shorts_agent.analytics as an
    monkeypatch.setattr(an, "hints", lambda *a, **k: "")
    assert S.pick_hook("topic", items).line0.startswith("The table")


def test_the_chosen_hook_replaces_the_first_two_lines():
    r = S.RScript(title="t", music="mystery", hook_type="", end_type="", hook_text="", end_question="", hook_candidates=[],
                  lines=[S.RLine(text=f"line {i}", caps="", evidence=["E9"], numbers=["5"]) for i in range(4)])
    h = S.HookIdea(line0="The ship was empty.", line1="Nobody knew why.", formula="empty ship", evidence=["E1"], numbers=[])
    S.apply_hook(r, h)
    assert [l.text for l in r.lines[:2]] == ["The ship was empty.", "Nobody knew why."] and r.lines[0].evidence == ["E1"] and r.lines[2].evidence == ["E9"]