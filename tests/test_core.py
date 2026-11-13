import datetime as dt
import json

from shorts_agent.factcheck_agent import quote_ok
from shorts_agent.schemas import Line, ScriptDraft, check_script, repair_caps
from shorts_agent.storyboard_agent import inject_host, static_check
from shorts_agent.styles import STYLES
from shorts_agent.uploader import build_metadata, next_publish_time

PA = STYLES["paper-atlas"]
EVID = [{"url": "u", "text": "Some of the gases dissolved in the synovial fluid leave the solution, making a bubble, or cavity."}]
CODE = "export function buildShots() {\n  const S = [], CUES = [];\n  return { shots: S, cues: CUES };\n}\n"


def draft(text, caps):
    return ScriptDraft(title="t", sources=["a", "b"], lines=[Line(text=text, caps=caps)])


def test_repair_adds_missing_highlight():
    d = repair_caps(draft("It was completely wrong", "COMPLETELY | WRONG"), 4)
    assert d.lines[0].caps == "*COMPLETELY | *WRONG"


def test_digits_in_spoken_text_are_flagged():
    problems = check_script(draft("In 1666 a fire began", "In *1666"), PA)
    assert any("numbers" in p for p in problems)


def test_quote_with_ellipsis_is_accepted():
    assert quote_ok("some of the gases dissolved in the synovial fluid... making a bubble, or cavity", "u", EVID)


def test_invented_quote_is_rejected():
    assert not quote_ok("the bubble instantly explodes with a loud bang every time", "u", EVID)


def test_quote_must_come_from_the_cited_url():
    assert not quote_ok("making a bubble, or cavity in the fluid", "other", EVID)


def test_inject_host_wraps_returned_shots():
    out = inject_host(CODE)
    assert out.startswith("import * as HOST") and "HOST.withHost(S)" in out


def test_static_check_rejects_llm_drawn_host():
    code = CODE + "import * as H from './core/hero.js';\nH.hero({});\n" + "// pad\n" * 80
    assert any("host" in p.lower() for p in static_check(code, STYLES["history"], 3))


def test_scenery_alias_collision_is_flagged():
    code = ("import * as S from './core/props.js';\nexport function buildShots() {\n  const S = [], CUES = [];\n"
            "  return { shots: S, cues: CUES };\n}\n" + "// padding\n" * 60)
    assert any("collision" in p for p in static_check(code, STYLES["history"], 3))


def test_era_check_flags_a_train_before_railways():
    body = "".join(f"SC.stage({{}}, t); SC.house(1,2,3); SC.crowd(1,2,3);\n" for _ in range(4)) + "SC.train(1, 2, 1, t);\n"
    code = ("import * as SC from './core/props.js';\nexport function buildShots() {\n  const S = [], CUES = [];\n" + body
            + "  return { shots: S, cues: CUES };\n}\n" + "// pad\n" * 40)
    assert any("Era error" in p for p in static_check(code, STYLES["history"], 3, year=1666))
    assert not any("Era error" in p for p in static_check(code, STYLES["history"], 3, year=1858))


def test_metadata_limits(tmp_path):
    (tmp_path / "script.json").write_text(json.dumps(
        {"title": "A " * 80, "sources": ["x: http://e"], "lines": [{"text": "Hook line.", "caps": "*Hook"}]}))
    m = build_metadata(tmp_path, "history")
    assert len(m["title"]) <= 100 and "Sources:" in m["description"] and "#historyfacts" in m["description"]
    assert sum(len(t) + 1 for t in m["tags"]) <= 450


def test_metadata_uses_the_niche_hashtags(tmp_path):
    (tmp_path / "script.json").write_text(json.dumps(
        {"title": "The Post-it note", "sources": ["x: http://e"], "lines": [{"text": "Hook line.", "caps": "*Hook"}]}))
    assert "#inventions" in build_metadata(tmp_path, "inventions")["description"]


def test_publish_time_is_in_the_future():
    t = dt.datetime.strptime(next_publish_time(17), "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc)
    assert t > dt.datetime.now(dt.timezone.utc)
