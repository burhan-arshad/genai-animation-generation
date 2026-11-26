import json

from shorts_agent import linecheck as lc

LINES = ["The ship was found drifting in 1872.", "Its crew had vanished.", "Investigators believed a storm was behind it.", "BAD the captain was a pirate.",
         "The lifeboat was gone.", "Nothing was ever proved.", "One theory says fear made them leave.", "So what really happened?"]
EV = [{"id": "E1", "title": "Mary Celeste", "source": "Wikipedia", "url": "u1",
       "text": "The ship was found drifting in 1872 by the Dei Gratia. The crew had vanished and the lifeboat was gone. Investigators believed a storm was behind it."}]


def make(tmp_path, lines=LINES):
    (tmp_path / "script.json").write_text(json.dumps({"title": "Mary Celeste", "sources": ["a"], "lines": [{"text": t} for t in lines]}))
    (tmp_path / "research.json").write_text(json.dumps({"topic": "Mary Celeste", "evidence": EV,
                                                       "lines": [{"text": t, "evidence": ["E1"], "numbers": []} for t in lines]}))


def stub(fix_text):
    def fake(prompt, schema, system=None, temperature=0.0, task="x", images=None):
        data = json.loads(prompt)
        if schema is lc.LineVerdicts:
            return lc.LineVerdicts(lines=[lc.LineVerdict(i=p["i"], ok="BAD" not in p["line"], issue="not in the evidence" if "BAD" in p["line"] else "") for p in data])
        return lc.Fixes(lines=[lc.Fix(i=l["i"], text=fix_text) for l in data["lines"]])
    return fake


def setup(monkeypatch, fix_text):
    monkeypatch.setattr(lc, "generate_structured", stub(fix_text))
    monkeypatch.setattr(lc, "web_evidence", lambda *a, **k: [])
    monkeypatch.setenv("FACT_REPAIR_ROUNDS", "2")


def test_supported_script_is_left_alone(tmp_path, monkeypatch):
    setup(monkeypatch, "x")
    make(tmp_path, [l.replace("BAD ", "") for l in LINES])
    assert lc.verify_project(tmp_path) == "verified"
    assert len(json.loads((tmp_path / "script.json").read_text())["lines"]) == 8


def test_an_unsupported_line_is_rewritten(tmp_path, monkeypatch):
    setup(monkeypatch, "The crew had vanished.")
    make(tmp_path)
    assert lc.verify_project(tmp_path) == "verified_with_notes"
    lines = [l["text"] for l in json.loads((tmp_path / "script.json").read_text())["lines"]]
    assert len(lines) == 8 and not any("BAD" in l for l in lines)


def test_a_line_that_cannot_be_fixed_is_removed(tmp_path, monkeypatch):
    setup(monkeypatch, "BAD again")
    make(tmp_path)
    assert lc.verify_project(tmp_path) == "verified_with_notes"
    assert len(json.loads((tmp_path / "script.json").read_text())["lines"]) == 7


def test_an_invented_name_is_caught_without_the_model(tmp_path, monkeypatch):
    setup(monkeypatch, "The lifeboat was gone.")
    lines = [l.replace("BAD ", "") for l in LINES]
    lines[3] = "Then Captain Zorblax boarded the ship."
    make(tmp_path, lines)
    assert lc.verify_project(tmp_path) == "verified_with_notes"
    assert "Zorblax" not in (tmp_path / "script.json").read_text()


def test_a_bad_first_line_fails_the_script(tmp_path, monkeypatch):
    setup(monkeypatch, "BAD still")
    lines = list(LINES)
    lines[0] = "BAD the ship was found in 1872."
    make(tmp_path, lines)
    try:
        lc.verify_project(tmp_path)
        assert False, "must fail"
    except lc.FactCheckFailed:
        pass