from __future__ import annotations

from services.planning.scheduler import _to_minutes, _to_hhmm
from services.planning.schemas import GeneratedSchedule, RepairAttempt, ScheduledBlock, ValidationResult


def repair_schedule(
    schedule: GeneratedSchedule,
    validation: ValidationResult,
    week_availability: list[dict],
) -> tuple[GeneratedSchedule, list[RepairAttempt]]:
    history: list[RepairAttempt] = []
    updated = schedule.model_copy(deep=True)
    intervals_by_date = {day["date"]: [dict(item) for item in day["free_intervals"]] for day in week_availability}

    violation_rules = {item.rule for item in validation.violations}
    if "maximum_daily_exploration" in violation_rules:
        updated, attempt = _remove_lowest_priority_block(updated)
        if attempt:
            history.append(attempt)

    if "no_overlap" in violation_rules or "does_not_overlap_fixed_blocks" in violation_rules:
        updated, attempt = _move_conflicting_block(updated, intervals_by_date)
        if attempt:
            history.append(attempt)

    if "duration_valid" in violation_rules:
        updated, attempt = _shorten_longest_block(updated)
        if attempt:
            history.append(attempt)

    return updated, history


def _remove_lowest_priority_block(schedule: GeneratedSchedule) -> tuple[GeneratedSchedule, RepairAttempt | None]:
    if not schedule.exploration_blocks:
        return schedule, None
    removed = schedule.exploration_blocks[-1]
    remaining = schedule.exploration_blocks[:-1]
    return (
        GeneratedSchedule(fixed_blocks=schedule.fixed_blocks, exploration_blocks=remaining),
        RepairAttempt(
            strategy="remove_lowest_priority",
            detail=f"Removed optional block {removed.title} on {removed.date}.",
        ),
    )


def _move_conflicting_block(
    schedule: GeneratedSchedule,
    intervals_by_date: dict[str, list[dict]],
) -> tuple[GeneratedSchedule, RepairAttempt | None]:
    blocks = list(schedule.exploration_blocks)
    if not blocks:
        return schedule, None

    for index, block in enumerate(blocks):
        conflict = _find_conflict(block, schedule)
        if conflict is None:
            continue
        moved = _relocate_block(block, intervals_by_date, schedule)
        if moved is None:
            continue
        blocks[index] = moved
        return (
            GeneratedSchedule(fixed_blocks=schedule.fixed_blocks, exploration_blocks=blocks),
            RepairAttempt(
                strategy="move_block",
                detail=f"Moved {block.title} from {block.date} {block.start} to {moved.date} {moved.start}.",
            ),
        )
    return schedule, None


def _shorten_longest_block(schedule: GeneratedSchedule) -> tuple[GeneratedSchedule, RepairAttempt | None]:
    if not schedule.exploration_blocks:
        return schedule, None
    longest = max(schedule.exploration_blocks, key=lambda block: _to_minutes(block.end) - _to_minutes(block.start))
    start = _to_minutes(longest.start)
    end = _to_minutes(longest.end)
    if end - start <= 30:
        return schedule, None
    shortened_end = end - 15
    updated = longest.model_copy(update={"end": _to_hhmm(shortened_end)})
    blocks = [updated if block is longest else block for block in schedule.exploration_blocks]
    return (
        GeneratedSchedule(fixed_blocks=schedule.fixed_blocks, exploration_blocks=blocks),
        RepairAttempt(strategy="shorten_block", detail=f"Shortened {longest.title} by 15 minutes."),
    )


def _find_conflict(block: ScheduledBlock, schedule: GeneratedSchedule) -> ScheduledBlock | None:
    start = _to_minutes(block.start)
    end = _to_minutes(block.end)
    for other in schedule.exploration_blocks:
        if other is block or other.date != block.date:
            continue
        if start < _to_minutes(other.end) and _to_minutes(other.start) < end:
            return other
    for fixed in schedule.fixed_blocks:
        if fixed.date != block.date:
            continue
        if start < _to_minutes(fixed.end) and _to_minutes(fixed.start) < end:
            return fixed
    return None


def _relocate_block(
    block: ScheduledBlock,
    intervals_by_date: dict[str, list[dict]],
    schedule: GeneratedSchedule,
) -> ScheduledBlock | None:
    duration = _to_minutes(block.end) - _to_minutes(block.start)
    for day in intervals_by_date:
        for interval in intervals_by_date[day]:
            if interval["duration_minutes"] < duration:
                continue
            candidate = block.model_copy(
                update={
                    "date": day,
                    "start": interval["start"],
                    "end": _to_hhmm(_to_minutes(interval["start"]) + duration),
                }
            )
            if _find_conflict(candidate, schedule) is None:
                return candidate
    return None
