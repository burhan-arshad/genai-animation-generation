import subprocess

import pytest
from fastapi.testclient import TestClient

from shorts_agent import api, automation


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    return TestClient(api.app)


def test_rejects_bad_time(client):
    r = client.post("/api/automation", json={"mode": "private", "run_time": "25:00"})
    assert r.status_code == 400 and "time" in r.json()["detail"]


def test_rejects_unknown_mode(client):
    r = client.post("/api/automation", json={"mode": "magic", "run_time": "12:30"})
    assert r.status_code == 400


def test_needs_youtube_login(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "TOKEN", tmp_path / "missing_token.json")
    r = client.post("/api/automation", json={"mode": "public", "run_time": "12:30"})
    assert r.status_code == 400 and "YouTube" in r.json()["detail"]


def test_off_removes_the_task(client, monkeypatch):
    called = []
    monkeypatch.setattr(api.automation, "remove", lambda: called.append(1))
    assert client.post("/api/automation", json={"mode": "off"}).status_code == 200
    assert called == [1]


def test_install_builds_the_task(monkeypatch):
    scripts = []
    monkeypatch.setattr(automation, "supported", lambda: True)
    monkeypatch.setattr(automation, "_ps", lambda s: scripts.append(s) or subprocess.CompletedProcess([], 0, "", ""))
    automation.install("12:30")
    assert len(scripts) == 1
    s = scripts[0]
    assert "12:30" in s and "shorts_agent.daily" in s and "StartWhenAvailable" in s and "AtLogOn" in s


def test_install_falls_back_without_the_logon_trigger(monkeypatch):
    scripts, codes = [], iter([1, 0])
    monkeypatch.setattr(automation, "supported", lambda: True)
    monkeypatch.setattr(automation, "_ps", lambda s: scripts.append(s) or subprocess.CompletedProcess([], next(codes), "", "denied"))
    automation.install("09:00")
    assert len(scripts) == 2 and "AtLogOn" in scripts[0] and "AtLogOn" not in scripts[1]


def test_install_reports_failure(monkeypatch):
    monkeypatch.setattr(automation, "supported", lambda: True)
    monkeypatch.setattr(automation, "_ps", lambda s: subprocess.CompletedProcess([], 1, "", "boom"))
    with pytest.raises(RuntimeError):
        automation.install("09:00")