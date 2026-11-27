"""Publishing schedule: the next free slot for a video (days, times and time zone are settings of the Assistant tab)."""
from __future__ import annotations

import datetime as dt
import os
import re
from collections import Counter
from zoneinfo import ZoneInfo

from . import store

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
UTC = dt.timezone.utc


def _fill(times: list[tuple[int, int]], per_day: int, window: str) -> list[tuple[int, int]]:
    """With fewer publish times than videos per day, the missing times are spread over the day, as far from each other as possible."""
    m = re.fullmatch(r"\s*([01]?\d|2[0-3]):([0-5]\d)\s*-\s*([01]?\d|2[0-3]):([0-5]\d)\s*", window or "")
    lo, hi = (int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))) if m else (9 * 60, 22 * 60)
    if hi <= lo:
        lo, hi = 9 * 60, 22 * 60
    have = [h * 60 + mi for h, mi in times]
    grid = list(range(lo, hi + 1, 30))
    while len(have) < per_day:
        cands = [g for g in grid if g not in have]
        if not cands:
            break
        have.append(max(cands, key=lambda g: (min(abs(g - x) for x in have), -g)))
    return sorted((x // 60, x % 60) for x in have)


def settings() -> dict:
    tz = (os.getenv("SCHEDULE_TZ") or "UTC").strip()
    try:
        ZoneInfo(tz)
    except Exception:
        tz = "UTC"
    times = []
    for t in re.split(r"[,; ]+", os.getenv("SCHEDULE_TIMES") or "18:00"):
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", t.strip())
        if m:
            times.append((int(m.group(1)), int(m.group(2))))
    days = [DAYS.index(d[:3]) for d in re.split(r"[,; ]+", (os.getenv("SCHEDULE_DAYS") or "").lower()) if d[:3] in DAYS] or list(range(7))
    try:
        per_day = max(1, int(os.getenv("SCHEDULE_PER_DAY") or 1))
    except ValueError:
        per_day = 1
    times = sorted(set(times)) or [(18, 0)]
    return {"tz": tz, "times": _fill(times, per_day, os.getenv("SCHEDULE_WINDOW") or "09:00-22:00"), "days": sorted(set(days)), "per_day": per_day}


def _parse(s: str):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def taken() -> list[dt.datetime]:
    """Moments of videos already published or scheduled by this program."""
    out = []
    for (s,) in store.db().execute("SELECT publish_at FROM jobs WHERE status='uploaded' AND publish_at IS NOT NULL AND publish_at != ''"):
        d = _parse(s)
        if d:
            out.append(d)
    return out


def next_slots(n: int = 1, after: dt.datetime | None = None) -> list[dt.datetime]:
    """The next `n` free slots (UTC): on the chosen days and times, not before now + 20 minutes, at most `per_day` videos a day."""
    s = settings()
    z = ZoneInfo(s["tz"])
    now = after or dt.datetime.now(UTC)
    used = taken()
    per_day = Counter(u.astimezone(z).date() for u in used)
    out: list[dt.datetime] = []
    first = now.astimezone(z).date()
    for k in range(150):
        day = first + dt.timedelta(days=k)
        if day.weekday() not in s["days"]:
            continue
        for h, m in s["times"]:
            if per_day[day] >= s["per_day"]:
                break
            slot = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=z).astimezone(UTC)
            if slot <= now + dt.timedelta(minutes=20) or any(abs((slot - u).total_seconds()) < 3600 for u in used):
                continue
            out.append(slot)
            used.append(slot)
            per_day[day] += 1
            if len(out) >= n:
                return out
    return out


def iso(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")