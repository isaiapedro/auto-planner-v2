"""Build context objects for Claude insight generation — no raw audio, structured summaries only."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import text

from database import AsyncSessionLocal
from services import calendar as calendar_svc


async def build_context(period: str) -> dict:
    """
    Returns a structured context dict for the given period.
    Cap: ~4000 tokens of input data total.
    """
    intervals = {"daily": 1, "weekly": 7, "monthly": 30}
    days_back = intervals.get(period, 7)
    since = date.today() - timedelta(days=days_back)

    async with AsyncSessionLocal() as db:
        # transcripts (last N, capped at 20)
        t_rows = await db.execute(
            text(
                "SELECT transcript, mood, energy, sentiment::text, key_takeaways, extracted_at "
                "FROM interpretations "
                "WHERE extracted_at >= :since "
                "ORDER BY extracted_at DESC LIMIT 20"
            ),
            {"since": since},
        )
        transcripts = [dict(r._mapping) for r in t_rows.fetchall()]

        # feature summary
        agg_row = await db.execute(
            text(
                "SELECT "
                "  AVG(mood)::REAL   AS avg_mood, "
                "  AVG(energy)::REAL AS avg_energy, "
                "  COUNT(*)          AS memo_count "
                "FROM interpretations WHERE extracted_at >= :since"
            ),
            {"since": since},
        )
        agg = dict(agg_row.fetchone()._mapping)

        # top topics
        topic_rows = await db.execute(
            text(
                "SELECT unnest(topics) AS topic, COUNT(*) AS cnt "
                "FROM interpretations WHERE extracted_at >= :since "
                "GROUP BY topic ORDER BY cnt DESC LIMIT 10"
            ),
            {"since": since},
        )
        top_topics = [{"topic": r.topic, "count": r.cnt} for r in topic_rows.fetchall()]

        # event completion
        evt_row = await db.execute(
            text(
                "SELECT "
                "  COUNT(*) FILTER (WHERE status='confirmed') AS confirmed, "
                "  COUNT(*) AS total "
                "FROM events WHERE scheduled_at >= :since"
            ),
            {"since": since},
        )
        evt = dict(evt_row.fetchone()._mapping)

        # current schedule config
        cfg_row = await db.execute(
            text(
                "SELECT wake_time::text, sleep_time::text, domain_weights, fixed_blocks "
                "FROM schedule_config ORDER BY updated_at DESC LIMIT 1"
            )
        )
        cfg = dict(cfg_row.fetchone()._mapping) if cfg_row.rowcount else {}

        # previous period insight (for continuity)
        prev_row = await db.execute(
            text(
                "SELECT narrative FROM insights "
                "WHERE period_type = :period "
                "ORDER BY period_start DESC LIMIT 1"
            ),
            {"period": period},
        )
        prev = prev_row.fetchone()
        previous_narrative = prev[0] if prev else None

        # dashboard snapshot
        dash_rows = await db.execute(
            text(
                "SELECT metric_id, metric_value, metadata "
                "FROM dashboard_metrics "
                "WHERE computed_for_date = (SELECT MAX(computed_for_date) FROM dashboard_metrics)"
            )
        )
        dashboard = [dict(r._mapping) for r in dash_rows.fetchall()]

        # active goals — the allocation driver (replaces domain_weights)
        goal_rows = await db.execute(
            text(
                "SELECT title, kind::text, domain, target_date::text, cadence "
                "FROM goals WHERE status = 'active' ORDER BY created_at"
            )
        )
        goals = [dict(r._mapping) for r in goal_rows.fetchall()]

    # live calendar — best-effort; insight generation must not fail if the
    # one-time OAuth setup (scripts/google_oauth_setup.py) hasn't run yet
    try:
        busy_windows = await asyncio.to_thread(calendar_svc.summarize_busy_windows, days_ahead=14)
    except Exception as exc:
        busy_windows = []
        calendar_error = str(exc)
    else:
        calendar_error = None

    return {
        "period": period,
        "period_start": since.isoformat(),
        "transcripts": [
            {
                "text": t["transcript"][:500] if t["transcript"] else "",  # cap per entry
                "mood": t["mood"],
                "energy": t["energy"],
                "sentiment": t["sentiment"],
                "takeaways": t["key_takeaways"],
                "date": str(t["extracted_at"])[:10],
            }
            for t in transcripts
        ],
        "summary": {
            "avg_mood": agg["avg_mood"],
            "avg_energy": agg["avg_energy"],
            "memo_count": agg["memo_count"],
            "top_topics": top_topics,
            "events_confirmed": evt["confirmed"],
            "events_total": evt["total"],
        },
        "schedule": cfg,
        "goals": goals,
        "busy_windows": busy_windows,
        "calendar_error": calendar_error,
        "dashboard": dashboard,
        "previous_narrative": previous_narrative,
    }
