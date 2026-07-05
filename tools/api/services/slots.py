"""Deterministic weekly slot generator + assigner — the two-block model's T(E) made concrete.

generate_weekly_slots computes a fixed grid of 2-hour candidate slots per
weekday, guaranteed by construction to be inside [wake_time, sleep_time -
buffer_minutes], and to never overlap fixed_blocks or any observed calendar
busy window.

assign_slots_to_goals fills those slots with goals via plain priority math —
no LLM involved. Local models (llama3.2, qwen3:8b) proved unreliable or too
slow on CPU-only hardware for this; since slot generation already guarantees
correctness, the remaining step is pure prioritization, which deterministic
code does perfectly and instantly.
"""
from __future__ import annotations

import re
from datetime import date

SLOT_MINUTES = 120
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def generate_weekly_slots(
    wake_time: str,
    sleep_time: str,
    buffer_minutes: int,
    fixed_blocks: list[dict],
    busy_windows: list[dict],
) -> list[dict]:
    """
    fixed_blocks: [{title, days: ["mon",...], start: "HH:MM", duration_minutes}]
    busy_windows: [{date, weekday, busy: [["HH:MM","HH:MM"], ...]}] (from
        calendar.summarize_busy_windows) — unioned across all observed dates
        per weekday, so a slot is only offered if free on every occurrence
        seen in the lookahead window.

    Returns a flat, stably-indexed list: [{id, weekday, start, duration_minutes}]
    """
    window_start = _to_minutes(wake_time)
    window_end = _to_minutes(sleep_time) - buffer_minutes

    busy_by_weekday: dict[str, list[tuple[int, int]]] = {d: [] for d in WEEKDAYS}
    for entry in busy_windows:
        wd = entry.get("weekday")
        if wd not in busy_by_weekday:
            continue
        for s, e in entry.get("busy", []):
            busy_by_weekday[wd].append((_to_minutes(s), _to_minutes(e)))

    for block in fixed_blocks:
        start = _to_minutes(block["start"])
        end = start + block["duration_minutes"]
        for day in block.get("days", []):
            if day in busy_by_weekday:
                busy_by_weekday[day].append((start, end))

    slots = []
    slot_id = 0
    for day in WEEKDAYS:
        busy = _merge(busy_by_weekday[day])
        cursor = window_start
        for b_start, b_end in busy:
            free_end = min(b_start, window_end)
            while cursor + SLOT_MINUTES <= free_end:
                slots.append({"id": slot_id, "weekday": day, "start": _to_hhmm(cursor), "duration_minutes": SLOT_MINUTES})
                slot_id += 1
                cursor += SLOT_MINUTES
            cursor = max(cursor, b_end)
        while cursor + SLOT_MINUTES <= window_end:
            slots.append({"id": slot_id, "weekday": day, "start": _to_hhmm(cursor), "duration_minutes": SLOT_MINUTES})
            slot_id += 1
            cursor += SLOT_MINUTES

    return slots


def _desired_weekly_count(goal: dict) -> int:
    if goal["kind"] == "routine":
        cadence = (goal.get("cadence") or "").lower()
        if "daily" in cadence:
            return 7
        m = re.match(r"(\d+)\s*x", cadence)
        if m:
            return min(int(m.group(1)), 7)
        return 2  # unparseable cadence — modest default

    # long_term: urgency scales with proximity to target_date
    target = goal.get("target_date")
    if not target:
        return 1
    days_left = (date.fromisoformat(target) - date.today()).days
    if days_left <= 30:
        return 3
    if days_left <= 90:
        return 2
    return 1


def assign_slots_to_goals(slots: list[dict], goals: list[dict]) -> list[dict]:
    """
    Weighted round-robin: each pass, goals with the most remaining demand go
    first; each goal takes at most one slot per pass, preferring a weekday it
    hasn't used yet (spreads a goal's sessions across the week). Deterministic,
    O(slots x goals), no LLM.

    Returns [{slot_id, goal_title}, ...].
    """
    remaining = {g["title"]: _desired_weekly_count(g) for g in goals}
    assigned_days: dict[str, set[str]] = {g["title"]: set() for g in goals}
    available = sorted(slots, key=lambda s: s["id"])
    assignments = []

    while available and any(v > 0 for v in remaining.values()):
        order = sorted((t for t, v in remaining.items() if v > 0), key=lambda t: (-remaining[t], t))
        progressed = False
        for title in order:
            if not available:
                break
            slot = next((s for s in available if s["weekday"] not in assigned_days[title]), available[0])
            available.remove(slot)
            assignments.append({"slot_id": slot["id"], "goal_title": title})
            assigned_days[title].add(slot["weekday"])
            remaining[title] -= 1
            progressed = True
        if not progressed:
            break

    return assignments
