from __future__ import annotations

from datetime import date, datetime, timedelta

from services import calendar as calendar_svc

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _weekday_key(day: date) -> str:
    return WEEKDAY_KEYS[day.weekday()]


def _calendar_busy_for_date(day: date, calendar_events: list[dict]) -> list[tuple[int, int]]:
    day_str = day.isoformat()
    busy: list[tuple[int, int]] = []
    for event in calendar_events:
        start = event.get("start")
        end = event.get("end")
        if not start or not end or "T" not in start:
            continue
        if start[:10] != day_str:
            continue
        busy.append((_to_minutes(start[11:16]), _to_minutes(end[11:16])))
    return busy


def _fixed_busy_for_date(day: date, fixed_blocks: list[dict]) -> list[tuple[int, int]]:
    weekday = _weekday_key(day)
    busy: list[tuple[int, int]] = []
    for block in fixed_blocks:
        if weekday not in {d.lower()[:3] for d in block.get("days", [])}:
            continue
        start = _to_minutes(block["start"])
        busy.append((start, start + int(block["duration_minutes"])))
    return busy


def compute_daily_free_intervals(
    day: date,
    wake_time: str,
    sleep_time: str,
    buffer_minutes: int,
    fixed_blocks: list[dict],
    calendar_events: list[dict],
) -> list[dict]:
    window_start = _to_minutes(wake_time)
    window_end = _to_minutes(sleep_time) - buffer_minutes
    if window_end <= window_start:
        return []

    busy = _merge(_calendar_busy_for_date(day, calendar_events) + _fixed_busy_for_date(day, fixed_blocks))
    free: list[dict] = []
    cursor = window_start
    for busy_start, busy_end in busy:
        free_end = min(busy_start, window_end)
        if cursor < free_end:
            duration = free_end - cursor
            if duration >= 15:
                free.append(
                    {
                        "date": day.isoformat(),
                        "start": _to_hhmm(cursor),
                        "end": _to_hhmm(free_end),
                        "duration_minutes": duration,
                    }
                )
        cursor = max(cursor, busy_end)
    if cursor < window_end:
        duration = window_end - cursor
        if duration >= 15:
            free.append(
                {
                    "date": day.isoformat(),
                    "start": _to_hhmm(cursor),
                    "end": _to_hhmm(window_end),
                    "duration_minutes": duration,
                }
            )
    return free


def compute_week_availability(
    week_start: date,
    horizon_days: int,
    wake_time: str,
    sleep_time: str,
    buffer_minutes: int,
    fixed_blocks: list[dict],
    calendar_events: list[dict] | None = None,
) -> list[dict]:
    events = calendar_events if calendar_events is not None else calendar_svc.list_upcoming_events(days_ahead=horizon_days + 7)
    days = [week_start + timedelta(days=offset) for offset in range(horizon_days)]
    return [
        {
            "date": day.isoformat(),
            "weekday": _weekday_key(day),
            "free_intervals": compute_daily_free_intervals(
                day,
                wake_time,
                sleep_time,
                buffer_minutes,
                fixed_blocks,
                events,
            ),
        }
        for day in days
    ]


def summarize_fixed_blocks_for_week(
    week_start: date,
    horizon_days: int,
    fixed_blocks: list[dict],
) -> list[dict]:
    blocks: list[dict] = []
    for offset in range(horizon_days):
        day = week_start + timedelta(days=offset)
        weekday = _weekday_key(day)
        for block in fixed_blocks:
            if weekday not in {d.lower()[:3] for d in block.get("days", [])}:
                continue
            start_minutes = _to_minutes(block["start"])
            end_minutes = start_minutes + int(block["duration_minutes"])
            blocks.append(
                {
                    "date": day.isoformat(),
                    "title": block["title"],
                    "start": block["start"],
                    "end": _to_hhmm(end_minutes),
                    "type": "fixed",
                }
            )
    return blocks


def planning_window_start(reference: date | None = None) -> date:
    return reference or date.today()
