import subprocess

import pytest

from shorts_agent import automation


def test_install_builds_the_task(monkeypatch):
    scripts = []
    monkeypatch.setattr(automation, "supported", lambda: True)
    monkeypatch.setattr(automation, "_ps", lambda s: scripts.append(s) or subprocess.CompletedProcess([], 0, "", ""))
    automation.install("12:30")
    assert len(scripts) == 1
    s = scripts[0]
    assert "12:30" in s and "shorts_agent.autopilot" in s and "--once" in s and "StartWhenAvailable" in s and "AtLogOn" in s


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