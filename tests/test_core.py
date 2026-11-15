import datetime as dt
import json

from shorts_agent.factcheck_agent import quote_ok
from shorts_agent.schemas import Line, ScriptDraft, check_script, repair_caps
from shorts_agent.styles import STYLES
from shorts_agent.uploader import build_metadata, next_publish_time

TT = STYLES["tall-tale"]
EVID = [{"url": "u", "text": "Some of the gases dissolved in the synovial fluid leave the solution, making a bubble, or cavity."}]


def draft(text, caps):
    return ScriptDraft(title="t", sources=["a", "b"], lines=[Line(text=text, caps=caps)])


def test_repair_adds_missing_highlight():
    d = repair_caps(draft("It was completely wrong", "COMPLETELY | WRONG"), 4)
    assert d.lines[0].caps == "*COMPLETELY | *WRONG"


def test_digits_in_spoken_text_are_flagged():
    problems = check_script(draft("In 1666 a fire began", ""), TT)
    assert any("numbers" in p for p in problems)


def test_auto_captions_need_no_caps():
    d = ScriptDraft(title="t", sources=["a", "b"], lines=[Line(text="word " * 8, caps="") for _ in range(14)])
    assert check_script(d, TT) == []


def test_quote_with_ellipsis_is_accepted():
    assert quote_ok("some of the gases dissolved in the synovial fluid... making a bubble, or cavity", "u", EVID)


def test_invented_quote_is_rejected():
    assert not quote_ok("the bubble instantly explodes with a loud bang every time", "u", EVID)


def test_quote_must_come_from_the_cited_url():
    assert not quote_ok("making a bubble, or cavity in the fluid", "other", EVID)


def test_metadata_limits(tmp_path):
    (tmp_path / "script.json").write_text(json.dumps(
        {"title": "A " * 80, "sources": ["x: http://e"], "lines": [{"text": "Hook line.", "caps": "*Hook"}]}))
    m = build_metadata(tmp_path, "history")
    assert len(m["title"]) <= 100 and "Sources:" in m["description"] and "#historyfacts" in m["description"]
    assert sum(len(t) + 1 for t in m["tags"]) <= 450


def test_metadata_falls_back_for_an_unknown_niche(tmp_path):
    (tmp_path / "script.json").write_text(json.dumps(
        {"title": "The Post-it note", "sources": ["x: http://e"], "lines": [{"text": "Hook line.", "caps": "*Hook"}]}))
    assert "#shorts" in build_metadata(tmp_path, "no-such-niche")["description"]


def test_publish_time_is_in_the_future():
    t = dt.datetime.strptime(next_publish_time(17), "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc)
    assert t > dt.datetime.now(dt.timezone.utc)