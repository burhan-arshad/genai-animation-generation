import re

import pytest

from shorts_agent import niche, pipeline, store, styles, topics
from shorts_agent.doctor import check_hardcoded_paths, RESULTS
from shorts_agent.storyboard_agent import era_props


def test_shipped_niches_are_valid():
    names = niche.available()
    assert "history" in names
    for n in names:
        assert niche.validate(n, niche.load(n)) == []
        re.compile(niche.load(n)["topics"]["block_regex"])
        assert n in styles.STYLES and styles.STYLES[n].niche == n


def test_template_is_not_listed_as_a_niche():
    assert "_template" not in niche.available()


def test_unknown_niche_gives_a_helpful_error():
    with pytest.raises(SystemExit) as e:
        niche.load("nope")
    assert "Available" in str(e.value)


def test_niche_rules_reach_the_style():
    st = styles.STYLES["history"]
    assert st.engine == "tall-tale" and st.caps_mode == "auto" and "Faces do the acting" in st.board_rules
    assert era_props(st)["train"] == 1825
    assert era_props(styles.STYLES["tall-tale"]) == {}


def test_default_key_follows_env(monkeypatch):
    monkeypatch.delenv("NICHE", raising=False)
    monkeypatch.setenv("STYLE", "other")
    assert styles.default_key() == "other"
    monkeypatch.setenv("NICHE", "history")
    assert styles.default_key() == "history"


def test_topic_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    store.add_job("The Great Molasses Flood of 1919", "history")
    ideas = [topics.Idea(topic=t, year=y, region=r, angle="a") for t, y, r in [
        ("The Great Molasses Flood in Boston 1919", 1919, "United States"),      # duplicate
        ("The Spanish Flu pandemic of 1918", 1918, "Europe"),                     # blocked theme
        ("The Year Without a Summer", 1900, "Asia"),                              # region
        ("The Dancing Plague of 1518", 1900, "Europe"),                           # blocked theme (plague)
        ("Operation Mincemeat", 2005, "Europe"),                                  # year
        ("The Brooklyn Bridge opens in 1883", 1883, "United States"),             # ok
        ("The Golden Spike of 1869", 1869, "United States")]]                     # ok
    monkeypatch.setattr(topics, "generate_structured", lambda *a, **k: topics.IdeaList(ideas=ideas))
    monkeypatch.setattr(topics, "wikipedia_facts", lambda q: [{"url": "u", "text": "t"}] * 5)
    got = [i.topic for i in topics.suggest(2, "history")]
    assert got == ["The Brooklyn Bridge opens in 1883", "The Golden Spike of 1869"]


def test_thin_evidence_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    monkeypatch.setattr(topics, "wikipedia_facts", lambda q: [{"url": "u", "text": "t"}])
    cfg = niche.load("history")["topics"]
    i = topics.Idea(topic="The Brooklyn Bridge opens in 1883", year=1883, region="United States", angle="a")
    assert topics.reject_reason(i, cfg, re.compile(cfg["block_regex"], re.I), []) == "thin evidence"

def test_overload_is_not_a_video_failure():
    class E(Exception):
        code = 503
    assert pipeline.is_overload(E())
    assert not pipeline.is_overload(ValueError("bad script"))


def test_doctor_path_scan_ignores_escaped_newlines_but_finds_real_paths(tmp_path, monkeypatch):
    from shorts_agent import doctor
    pkg = tmp_path / "shorts_agent"
    pkg.mkdir()
    (pkg / "a.py").write_text('x = "CRASH:\\n" + y\n')
    (pkg / "b.py").write_text('p = r"D:\\\\AntiGravity\\\\shorts"\n')
    monkeypatch.setattr(doctor, "REPO", tmp_path)
    doctor.RESULTS.clear()
    doctor.check_hardcoded_paths()
    level, _, detail = doctor.RESULTS[-1]
    assert level == "warn" and "b.py" in detail and "a.py" not in detail
