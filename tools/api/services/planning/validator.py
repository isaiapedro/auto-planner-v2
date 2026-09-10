from __future__ import annotations

from collections import Counter
from datetime import date

from config import settings
from services.planning.schemas import GeneratedSchedule, PlanningRecommendation, ScheduledBlock, ValidationResult, ValidationViolation


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def validate_schedule(
    schedule: GeneratedSchedule,
    recommendations: list[PlanningRecommendation],
    week_start: date,
    week_end: date,
    wake_time: str,
    sleep_time: str,
    buffer_minutes: int,
) -> ValidationResult:
    violations: list[ValidationViolation] = []
    wake = _to_minutes(wake_time)
    sleep = _to_minutes(sleep_time)
    latest_end = sleep - buffer_minutes

    all_blocks = schedule.exploration_blocks

    for block in all_blocks:
        start = _to_minutes(block.start)
        end = _to_minutes(block.end)
        block_date = date.fromisoformat(block.date)

        if block_date < week_start or block_date > week_end:
            violations.append(
                ValidationViolation(
                    block=block.title,
                    rule="date_inside_planning_horizon",
                    message=f"{block.title} is outside the planning horizon.",
                )
            )
        if end - start < 15 or end - start > 240:
            violations.append(
                ValidationViolation(
                    block=block.title,
                    rule="duration_valid",
                    message=f"{block.title} has an invalid duration.",
                )
            )
        if start < wake or end > latest_end:
            violations.append(
                ValidationViolation(
                    block=block.title,
                    rule="inside_waking_window",
                    message=f"{block.title} falls outside the waking window.",
                )
            )
        if end > latest_end:
            violations.append(
                ValidationViolation(
                    block=block.title,
                    rule="respects_sleep_buffer",
                    message=f"{block.title} overlaps the sleep buffer.",
                )
            )

    for left, right in _pairwise(all_blocks):
        if left.date != right.date:
            continue
        if _overlap(_to_minutes(left.start), _to_minutes(left.end), _to_minutes(right.start), _to_minutes(right.end)):
            violations.append(
                ValidationViolation(
                    block=left.title,
                    rule="no_overlap",
                    message=f"{left.title} overlaps {right.title}.",
                )
            )

    for fixed in schedule.fixed_blocks:
        for block in schedule.exploration_blocks:
            if fixed.date != block.date:
                continue
            if _overlap(_to_minutes(fixed.start), _to_minutes(fixed.end), _to_minutes(block.start), _to_minutes(block.end)):
                violations.append(
                    ValidationViolation(
                        block=block.title,
                        rule="does_not_overlap_fixed_blocks",
                        message=f"{block.title} overlaps fixed block {fixed.title}.",
                    )
                )

    counts_by_intention = Counter(block.intention_id for block in schedule.exploration_blocks if block.intention_id)
    for recommendation in recommendations:
        actual = counts_by_intention.get(recommendation.intention_id, 0)
        if actual > recommendation.frequency:
            violations.append(
                ValidationViolation(
                    block=recommendation.title or recommendation.practice,
                    rule="frequency_constraints",
                    message=(
                        f"{recommendation.intention_id} has {actual} blocks but only "
                        f"{recommendation.frequency} were requested."
                    ),
                )
            )

    daily_minutes: Counter[str] = Counter()
    for block in schedule.exploration_blocks:
        daily_minutes[block.date] += _to_minutes(block.end) - _to_minutes(block.start)
    for day, minutes in daily_minutes.items():
        if minutes > settings.max_daily_exploration_minutes:
            hours = minutes // 60
            mins = minutes % 60
            violations.append(
                ValidationViolation(
                    block=day,
                    rule="maximum_daily_exploration",
                    message=(
                        f"{day} contains {hours}h{mins:02d} of exploration; "
                        f"maximum is {settings.max_daily_exploration_minutes // 60}h."
                    ),
                )
            )

    return ValidationResult(valid=len(violations) == 0, violations=violations)


def _pairwise(blocks: list[ScheduledBlock]):
    for index, left in enumerate(blocks):
        for right in blocks[index + 1 :]:
            yield left, right
