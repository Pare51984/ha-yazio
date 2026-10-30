"""Turns Yazio's relative fasting plan into real local times."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util


def _cycle(plan: dict[str, Any]) -> int:
    return max(begin[0] for begin, _ in plan["periods"]) + 1


def windows_between(plan: dict[str, Any], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """All fasting windows overlapping [start, end). The plan repeats after its last day."""
    base = date.fromisoformat(plan["start_date"])
    cycle = _cycle(plan)
    tz = dt_util.get_default_time_zone()
    first = max(0, (dt_util.as_local(start).date() - base).days // cycle - 1)
    last = max(0, (dt_util.as_local(end).date() - base).days // cycle + 1)
    windows = []
    for rep in range(first, last + 1):
        offset = rep * cycle
        for (b_day, b_time), (e_day, e_time) in plan["periods"]:
            begin = datetime.combine(base + timedelta(days=offset + b_day), time.fromisoformat(b_time), tz)
            stop = datetime.combine(base + timedelta(days=offset + e_day), time.fromisoformat(e_time), tz)
            if stop > begin and stop > start and begin < end:
                windows.append((begin, stop))
    return sorted(windows)


def fasting_windows(plan: dict[str, Any], now: datetime) -> list[tuple[datetime, datetime]]:
    """Windows around now (from yesterday to a week ahead)."""
    return windows_between(plan, now - timedelta(days=2), now + timedelta(days=8))


def fasting_state(plan: dict[str, Any], now: datetime) -> tuple[str, dict[str, Any], datetime | None]:
    """State, attributes and the time of the next change."""
    windows = fasting_windows(plan, now)
    current = next(((b, e) for b, e in windows if b <= now < e), None)
    upcoming = next(((b, e) for b, e in windows if b > now), None)
    base = date.fromisoformat(plan["start_date"])
    today = dt_util.as_local(now).date()
    day_index = (today - base).days % _cycle(plan) if today >= base else None
    skipped = plan.get("skipped_meals", {}).get(day_index, []) if day_index is not None else []
    if current:
        state, change = "fasting", current[1]
        attrs = {"fasting_start": current[0].isoformat(), "fasting_end": current[1].isoformat()}
    else:
        state, change = "eating", upcoming[0] if upcoming else None
        attrs = {
            "fasting_start": upcoming[0].isoformat() if upcoming else None,
            "fasting_end": upcoming[1].isoformat() if upcoming else None,
        }
    attrs["next_change"] = change.isoformat() if change else None
    attrs["meals_to_skip_today"] = skipped
    return state, attrs, change


def plan_label(key: Any) -> str | None:
    """'16_8_early_fasting_v2' -> '16:8'."""
    if not isinstance(key, str):
        return None
    parts = key.split("_")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}:{parts[1]}"
    return None
