import json

import pytest

from shorts_agent import filmboard as F
from shorts_agent import series as S
from shorts_agent import store, styles
from tests.test_film import timing


def look(i):
    return {"id": i, "body": "#7FC8E8", "pattern": "plain", "patCol": "#6B422B", "hat": "none", "hatCol": "#8C5A3A", "neck": "none", "neckCol": "#F26B5B",
            "extra": [], "hair": "#2B2118", "hairStyle": "short", "skin": "#E0A97A", "dress": False, "kid": False}


EV = [{"id": f"E{i}", "title": f"Page {i % 3}", "source": "Wikipedia", "url": f"u{i % 3}",
       "text": f"The ship Mary Celeste was found drifting in 1872 with nobody aboard. Fact {i}."} for i in range(1, 13)]
SETS = [{"id": "deck", "kind": "sea", "time": "day", "sign": "", "deck": True, "dress": []}, {"id": "office", "kind": "room", "time": "day", "sign": "", "deck": False, "dress": []}]
BIBLE = {"title": "The Empty Deck", "logline": "A ship found drifting.", "place": "Atlantic", "date": "1872", "key_object": "lifeboat", "sets": SETS,
         "cast": [{"role": "the captain", "look": look("captain")}, {"role": "the mate", "look": look("mate")}, {"role": "an inspector", "look": look("inspector")}],
         "episodes": [{"title": f"Part {i}", "summary": "s", "reveals": ["r1", "r2"], "cliffhanger": "Where did they go?", "evidence": ["E1", "E2", "E3", "E4"]} for i in (1, 2, 3)],
         "evidence": EV, "minutes": 7, "topic": "The Mary Celeste Abandonment (1872)"}


def test_the_plan_is_repaired():
    plan = S.SeriesPlan.model_validate({
        "title": "Test", "logline": "x", "place": "Sea", "date": "1872", "key_object": "boat",
        "sets": [{"id": "Deck!", "kind": "sea", "time": "day", "sign": "", "deck": True, "dress": []}],
        "cast": [{"role": "captain", "look": look("Captain Bob")}, {"role": "x", "look": look("host")}, {"role": "mate", "look": look("mate")}],
        "episodes": [{"title": "One", "summary": "s", "reveals": [], "cliffhanger": "c", "evidence": ["E1", "E99"]},
                     {"title": "Two", "summary": "s", "reveals": [], "cliffhanger": "c", "evidence": []}]})
    assert S.fix_plan(plan, EV, 2) == []
    assert plan.key_object == "lifeboat" and [m.look.id for m in plan.cast] == ["captain_bob", "mate"] and plan.sets[0].id == "deck"
    assert "E99" not in plan.episodes[0].evidence and all(len(e.evidence) >= 8 for e in plan.episodes)


def test_a_series_becomes_episode_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    plan = S.SeriesPlan.model_validate({"title": "The Empty Deck", "logline": "l", "place": "Atlantic", "date": "1872", "key_object": "lifeboat", "sets": SETS,
                                        "cast": [{"role": "a", "look": look("a")}, {"role": "b", "look": look("b")}],
                                        "episodes": [{"title": f"E{i}", "summary": "s", "reveals": [], "cliffhanger": "c", "evidence": ["E1"]} for i in (1, 2)]})
    S.fix_plan(plan, EV, 2)
    monkeypatch.setattr(S, "gather", lambda topic: EV)
    monkeypatch.setattr(S, "make_plan", lambda topic, items, eps: plan)
    sid = S.create_series("The Mary Celeste Abandonment (1872)", 2)
    rows = [dict(r) for r in store.db().execute("SELECT * FROM jobs WHERE series_id=? ORDER BY ep_no", (sid,))]
    assert [(r["ep_no"], r["kind"], r["status"]) for r in rows] == [(1, "episode", "queued"), (2, "episode", "queued")]
    assert S.overview()[0]["episodes"][1]["job"]["id"] == rows[1]["id"]
    assert S.remove(sid) == 2 and S.overview() == []


def test_scene_cards_become_a_valid_film():
    n = 12
    script = {"title": "The Empty Deck: Episode 1", "lines": [{"text": f"line {i}", "ch": i // 4} for i in range(n)]}
    raw = {"set": "deck", "time": "night", "cast": ["captain", "nobody", "mate"], "object": "boat", "mood": "worried", "effect": "dutch", "fx": "rain",
           "reveals": [{"line": 5, "word": "stone", "object": "compass", "move": "rise"}, {"line": 99, "word": "x", "object": "compass", "move": "rise"}],
           "beats": [{"line": 6, "word": "stone", "mood": "shock"}], "callouts": [{"line": 5, "word": "stone", "text": "1872"}]}
    card = S.clean_card(raw, BIBLE, 2, 10)
    assert card["object"] == "lifeboat" and card["cast"] == ["captain", "mate"] and len(card["reveals"]) == 1 and card["time"] == "night"
    chapters = [(ci, [i for i in range(n) if i // 4 == ci], card if ci == 1 else S.default_card(BIBLE, ci, 3)) for ci in range(3)]
    draft = S.compile_draft(BIBLE, script, chapters, 2, 1, "CONTINUED")
    story, problems, warns = F.build(draft, timing(n=n), hook={"text": "PART ONE", "end_question": "NEXT: PART TWO"}, appear="first_last")
    assert problems == [], problems
    body = [s for s in story["shots"] if s["set"] != "study"]
    assert len(body) >= 8 and all(a["who"] in ("captain", "mate", "inspector") for s in body for a in s["actors"])
    assert {"deck", "deck_night"} <= set(story["sets"]) and "lifeboat" in story["custom"] and "compass" in story["custom"]


def test_the_episode_settings_are_restored(monkeypatch):
    monkeypatch.delenv("VOICE_MAX_SECONDS", raising=False)
    monkeypatch.setenv("QA_MIN_DUR", "20")
    with S.episode_env():
        import os
        assert os.environ["VOICE_MAX_SECONDS"] == "0" and os.environ["QA_MIN_DUR"] == "190"
    import os
    assert "VOICE_MAX_SECONDS" not in os.environ and os.environ["QA_MIN_DUR"] == "20"


def test_an_episode_is_written_chapter_by_chapter(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "get_series", lambda sid: {"bible": json.dumps(BIBLE)})
    monkeypatch.setattr(S, "prepare", lambda project: None)
    styles.set_active("mysteries")

    def fake(prompt, schema, system=None, temperature=0.0, task="x", images=None):
        if schema is S.ChapterList:
            return S.ChapterList(chapters=[S.Chapter(title=f"C{i}", purpose="p", evidence=["E1", "E2"]) for i in range(5)])
        return S.ChapterText(lines=[S.CLine(text=f"The ship was found drifting with nobody aboard number {j}.", evidence=["E1"], numbers=[]) for j in range(6)])

    monkeypatch.setattr(S, "generate_structured", fake)
    S.write_episode({"id": 1, "series_id": 1, "ep_no": 2}, tmp_path)
    script = json.loads((tmp_path / "script.json").read_text())
    research = json.loads((tmp_path / "research.json").read_text())
    assert len(script["lines"]) == 30 and {l["ch"] for l in script["lines"]} == {0, 1, 2, 3, 4}
    assert len(research["lines"]) == 30 and script["series"]["ep"] == 2 and script["series"]["next_title"] == "Part 3"
    assert script["hook"]["end_question"] == "NEXT: PART 3" and "number three" in script["lines"][3]["text"]