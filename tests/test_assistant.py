import datetime as dt
import json

from shorts_agent import autopilot, quality, schedule, store

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 25, 10, 0, tzinfo=UTC)        # a Wednesday


def env(monkeypatch, **kw):
    for k, v in {"SCHEDULE_TZ": "UTC", "SCHEDULE_TIMES": "18:00", "SCHEDULE_DAYS": "", "SCHEDULE_PER_DAY": "1", **kw}.items():
        monkeypatch.setenv(k, v)


def test_next_slot_today_then_tomorrow(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    env(monkeypatch)
    s1 = schedule.next_slots(1, after=NOW)[0]
    assert s1 == dt.datetime(2026, 11, 25, 18, 0, tzinfo=UTC)
    jid = store.add_job("x y z", "mysteries")
    store.set_job(jid, status="uploaded", publish_at=schedule.iso(s1))
    assert schedule.next_slots(1, after=NOW)[0] == dt.datetime(2026, 11, 26, 18, 0, tzinfo=UTC)


def test_days_times_and_zone(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    env(monkeypatch, SCHEDULE_DAYS="mon")
    assert schedule.next_slots(1, after=NOW)[0] == dt.datetime(2026, 11, 30, 18, 0, tzinfo=UTC)
    env(monkeypatch, SCHEDULE_TZ="America/New_York", SCHEDULE_TIMES="12:00", SCHEDULE_DAYS="")
    assert schedule.next_slots(1, after=NOW)[0] == dt.datetime(2026, 11, 25, 17, 0, tzinfo=UTC)
    env(monkeypatch, SCHEDULE_TIMES="09:00, 18:00", SCHEDULE_PER_DAY="2")
    got = schedule.next_slots(2, after=dt.datetime(2026, 11, 25, 6, 0, tzinfo=UTC))
    assert [g.hour for g in got] == [9, 18] and got[0].day == got[1].day == 25


def test_quality_score_rewards_a_complete_video(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "PROJECTS_ROOT", tmp_path)
    p = tmp_path / "001-x"
    p.mkdir()
    shots = [{"set": "a", "camera": c, "props": [{"name": "coin"}], "actors": [{"beats": [{"t": 1}], "arms": {"r": "down"}, "x0": 1, "x1": 1}]}
             for c in ("push_in", "pan_left", "drift", "crane_down", "handheld")]
    (p / "story.json").write_text(json.dumps({"shots": [{"set": "study"}] + shots}))
    (p / "qa.json").write_text(json.dumps({"meta": {"duration": 45}}))
    (p / "thumb.jpg").write_bytes(b"x")
    s, why = quality.score({"slug": "001-x", "fact_status": "verified", "qa_status": "passed"})
    assert s == 100 and why == []
    s2, why2 = quality.score({"slug": "001-x", "fact_status": "verified_with_notes", "qa_status": "passed_with_warnings"})
    assert s2 == 84 and len(why2) == 2


def test_assistant_settings_are_checked_and_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "PATH", tmp_path / "autopilot.json")
    assert autopilot.save({"mode": "magic"}) and autopilot.save({"sched_times": "25:99"})
    assert autopilot.save({"buffer": "abc"}) and autopilot.save({"sched_tz": "Mars/Base"})
    assert autopilot.save({"mode": "private", "buffer": "3", "sched_times": "18:00, 09:30"}) == []
    assert autopilot.load()["mode"] == "private" and autopilot.load()["buffer"] == "3"
    assert autopilot.env_overrides()["SCHEDULE_TIMES"] == "18:00, 09:30" and "MIN_SOURCES" not in autopilot.env_overrides()


def test_a_video_over_its_token_cap_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "jobs.db")
    jid = store.add_job("a b c", "mysteries")
    store.set_job(jid, tokens=999999)
    notes = []
    assert autopilot.work_job(jid, {"tokens_per_video": "1000", "stage_failures": "2"}, notes) == "dropped"
    assert store.get_job(jid)["status"] == "dropped" and notes