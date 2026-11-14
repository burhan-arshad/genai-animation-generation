"""Daily automation through the Windows Task Scheduler (works even when the dashboard is closed).
The task runs `python -m shorts_agent.daily` at the chosen time, and also at logon and after a missed start,
so a laptop that was off at that time still makes the video as soon as it is on."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .config import REPO

TASK = "shorts-agent-daily"


def supported() -> bool:
    return os.name == "nt"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")          # no console window
    return w if w.exists() else exe


def _q(s: str) -> str:
    return str(s).replace("'", "''")


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _script(run_time: str, logon: bool) -> str:
    t2 = "$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME\n" if logon else ""
    triggers = "@($t1, $t2)" if logon else "@($t1)"
    return f"""
$ErrorActionPreference = 'Stop'
$a = New-ScheduledTaskAction -Execute '{_q(_pythonw())}' -Argument '-m shorts_agent.daily' -WorkingDirectory '{_q(REPO)}'
$t1 = New-ScheduledTaskTrigger -Daily -At '{_q(run_time)}'
{t2}$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger {triggers} -Settings $s -Force | Out-Null
"""


def install(run_time: str) -> None:
    """run_time: 'HH:MM' in this computer's time."""
    if not supported():
        raise RuntimeError("Automatic scheduling is only built in for Windows (use cron on Linux/Mac).")
    p = _ps(_script(run_time, logon=True))
    if p.returncode != 0:                       # the logon trigger can need Administrator: retry with the daily trigger only
        p = _ps(_script(run_time, logon=False))
    if p.returncode != 0:
        raise RuntimeError("Could not create the scheduled task: " + (p.stderr or p.stdout).strip()[:300])


def remove() -> None:
    if supported():
        _ps(f"Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false -ErrorAction SilentlyContinue")


def status() -> dict:
    out = {"installed": False, "run_time": "", "next_run": "", "last_run": ""}
    if not supported():
        return out
    p = _ps(f"""
$t = Get-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue
if ($t) {{
  $i = Get-ScheduledTaskInfo -TaskName '{TASK}'
  $d = $t.Triggers | Where-Object {{ $_.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger' }} | Select-Object -First 1
  Write-Output ("OK|" + $d.StartBoundary + "|" + $i.NextRunTime.ToString('s') + "|" + $i.LastRunTime.ToString('s'))
}} else {{ Write-Output 'NONE' }}
""")
    line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    if line.startswith("OK|"):
        _, start, nxt, last = (line.split("|") + ["", "", ""])[:4]
        m = re.search(r"T(\d\d:\d\d)", start)
        out.update(installed=True, run_time=m.group(1) if m else "",
                   next_run=nxt.replace("T", " ")[:16],
                   last_run="" if last.startswith(("1999", "1601")) else last.replace("T", " ")[:16])
    return out