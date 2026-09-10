from __future__ import annotations

from services.planning.schemas import GeneratedSchedule, PlanningRecommendation, ScheduledBlock


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _preferred_window(preferred_time: str | None) -> tuple[int, int] | None:
    if not preferred_time:
        return None
    normalized = preferred_time.lower()
    if normalized == "morning":
        return (0, 12 * 60)
    if normalized == "afternoon":
        return (12 * 60, 17 * 60)
    if normalized == "evening":
        return (17 * 60, 24 * 60)
    return None


def _fits_preference(start_minutes: int, preferred_time: str | None) -> bool:
    window = _preferred_window(preferred_time)
    if window is None:
        return True
    return window[0] <= start_minutes < window[1]


def schedule_week(
    recommendations: list[PlanningRecommendation],
    week_availability: list[dict],
    fixed_blocks: list[dict],
) -> GeneratedSchedule:
    fixed = [
        ScheduledBlock(
            date=block["date"],
            start=block["start"],
            end=block["end"],
            title=block["title"],
            type="fixed",
        )
        for block in fixed_blocks
    ]

    intervals_by_date = {day["date"]: list(day["free_intervals"]) for day in week_availability}
    used_days_by_intention: dict[str, set[str]] = {}
    exploration: list[ScheduledBlock] = []

    ordered = sorted(recommendations, key=lambda item: (-item.priority, item.intention_id, item.practice))
    for recommendation in ordered:
        used_days_by_intention.setdefault(recommendation.intention_id, set())
        placed = 0
        for day in week_availability:
            if placed >= recommendation.frequency:
                break
            date_key = day["date"]
            if recommendation.spacing == "separate_days" and date_key in used_days_by_intention[recommendation.intention_id]:
                continue

            intervals = intervals_by_date.get(date_key, [])
            for index, interval in enumerate(intervals):
                duration = recommendation.duration_minutes
                if interval["duration_minutes"] < duration:
                    continue
                start_minutes = _to_minutes(interval["start"])
                if not _fits_preference(start_minutes, recommendation.preferred_time):
                    continue
                end_minutes = start_minutes + duration
                block = ScheduledBlock(
                    date=date_key,
                    start=interval["start"],
                    end=_to_hhmm(end_minutes),
                    title=recommendation.title or recommendation.practice.replace("_", " ").title(),
                    type="exploration",
                    intention_id=recommendation.intention_id,
                    practice=recommendation.practice,
                    evidence_ids=recommendation.evidence_ids,
                )
                exploration.append(block)
                used_days_by_intention[recommendation.intention_id].add(date_key)
                placed += 1

                remaining = interval["duration_minutes"] - duration
                updated_start = _to_hhmm(end_minutes)
                if remaining >= 15:
                    intervals[index] = {
                        **interval,
                        "start": updated_start,
                        "duration_minutes": remaining,
                    }
                else:
                    intervals.pop(index)
                break

    return GeneratedSchedule(fixed_blocks=fixed, exploration_blocks=exploration)
