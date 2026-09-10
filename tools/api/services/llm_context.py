"""Build review context from durable observations and immutable transcripts.

The memo pipeline is deliberately transcript-only. This module must not revive
the retired enrichment path (sentiment, embeddings, entities, takeaways, or
metrics) by reading the legacy ``interpretations`` table.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from config import settings
from database import AsyncSessionLocal
from services import calendar as calendar_svc


_RECORD_ID = re.compile(r"^obs_id:\s*([0-9a-f-]{36})\s*$", re.MULTILINE)
_RECORD_DATE = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_RECORD_TRANSCRIPT = re.compile(
    r"^## Transcript[^\n]*\n\n(.*?)(?=\n## |\Z)", re.MULTILINE | re.DOTALL
)
_GOAL_ROW = re.compile(r"^\|\s*([A-Z]+-\d+)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)


async def build_context(period: str) -> dict:
    """
    Returns a structured context dict for the given period.
    Cap: ~4000 tokens of input data total.
    """
    intervals = {"daily": 1, "weekly": 7, "monthly": 30}
    days_back = intervals.get(period, 7)
    since = date.today() - timedelta(days=days_back)

    async with AsyncSessionLocal() as db:
        # Transcript-backed observations (last N, capped at 20).  The DB stores
        # an immutable Personal-domain pointer; transcript text stays on disk.
        t_rows = await db.execute(
            text(
                "SELECT id::text AS obs_id, payload->>'transcript_path' AS transcript_path, captured_at "
                "FROM observations "
                "WHERE source_type = 'audio' AND captured_at >= :since "
                "  AND payload ? 'transcript_path' "
                "ORDER BY captured_at DESC LIMIT 20"
            ),
            {"since": since},
        )
        transcript_rows = [dict(r._mapping) for r in t_rows.fetchall()]
        transcripts = [
            {
                "obs_id": row["obs_id"],
                "text": _read_transcript_text(row["transcript_path"]),
                "captured_at": row["captured_at"],
            }
            for row in transcript_rows
        ]
        # Memos recorded before the durable job table were migrated as immutable
        # Personal records. Include their original Transcript section as
        # evidence, but deliberately ignore retired mood/sentiment/takeaway
        # fields in those legacy documents.
        transcripts.extend(_legacy_record_transcripts_since(since))
        transcripts = _deduplicate_and_limit_transcripts(transcripts)
        memo_refs = [t["obs_id"] for t in transcripts]

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

        # previous period insight (for continuity)
        prev_row = await db.execute(
            text(
                "SELECT narrative, inference_bundle FROM insights "
                "WHERE period_type = :period "
                "ORDER BY period_start DESC LIMIT 1"
            ),
            {"period": period},
        )
        prev = prev_row.fetchone()
        previous_narrative = prev[0] if prev else None
        previous_bundle = prev[1] if prev else None

        # Local scheduling state is context, never proof that a registry goal
        # has progressed. Registry goals are loaded separately below.
        goal_rows = await db.execute(
            text(
                "SELECT title, kind::text, domain, target_date::text, cadence "
                "FROM goals WHERE status = 'active' ORDER BY created_at"
            )
        )
        scheduled_goals = [dict(r._mapping) for r in goal_rows.fetchall()]

    # live calendar — best-effort; insight generation must not fail if the
    # one-time OAuth setup (scripts/google_oauth_setup.py) hasn't run yet
    try:
        busy_windows = await asyncio.to_thread(calendar_svc.summarize_busy_windows, days_ahead=14)
    except Exception as exc:
        busy_windows = []
        calendar_error = str(exc)
    else:
        calendar_error = None

    behavioral_context = _load_behavioral_context()
    routine_adherence = await _compute_routine_adherence(since, db_session=None)
    citation_catalog = _load_citation_catalog()
    registry_goals = _load_goal_registry()
    pillar_taxonomy = _load_pillar_taxonomy()

    return {
        "period": period,
        "period_start": since.isoformat(),
        "transcripts": [
            {
                "text": t["text"][:500],  # cap per entry
                "date": str(t["captured_at"])[:10],
            }
            for t in transcripts
        ],
        "summary": {
            "memo_count": len(transcripts),
            "events_confirmed": evt["confirmed"],
            "events_total": evt["total"],
        },
        "goals": registry_goals,
        "scheduled_goals": scheduled_goals,
        "pillar_taxonomy": pillar_taxonomy,
        "busy_windows": busy_windows,
        "calendar_error": calendar_error,
        # Dashboard metrics can be backed by legacy enrichment tables. Reviews
        # receive only scoped transcripts, events, goals, and routine data.
        "dashboard": [],
        "previous_narrative": previous_narrative,
        "previous_inference_bundle": previous_bundle,
        "memo_refs": memo_refs,
        "behavioral_context": behavioral_context,
        "routine_adherence": routine_adherence,
        "citation_catalog": citation_catalog,
    }


def _read_transcript_text(path_value: str | None) -> str:
    """Read only transcript files inside the configured Personal boundary."""
    if not path_value:
        return ""
    transcript_root = Path(settings.personal_transcripts_path).resolve()
    try:
        path = Path(path_value).resolve()
        path.relative_to(transcript_root)
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        # A missing/legacy pointer is not a reason to fail a whole review.
        return ""


def _legacy_record_transcripts_since(since: date) -> list[dict]:
    """Read only canonical migrated memo records inside Personal Planner."""
    memo_root = Path(settings.personal_memos_path).resolve()
    records_root = memo_root / "records"
    try:
        if not records_root.is_dir() or not records_root.resolve().is_relative_to(memo_root):
            return []
    except OSError:
        return []

    records: list[dict] = []
    for record in records_root.glob("*.md"):
        try:
            content = record.read_text(encoding="utf-8")
            memo_id = _RECORD_ID.search(content)
            recorded_on = _RECORD_DATE.search(content)
            transcript = _RECORD_TRANSCRIPT.search(content)
            if not memo_id or not recorded_on or not transcript:
                continue
            captured_at = date.fromisoformat(recorded_on.group(1))
            text_value = transcript.group(1).strip()
            if captured_at >= since and text_value:
                records.append({"obs_id": memo_id.group(1), "text": text_value, "captured_at": captured_at})
        except (OSError, ValueError):
            # One malformed historic record must not hide the rest of the
            # explicitly selected Personal evidence.
            continue
    return records


def _deduplicate_and_limit_transcripts(transcripts: list[dict]) -> list[dict]:
    """Keep recent non-empty transcript evidence, newest first, by memo UUID."""
    unique: dict[str, dict] = {}
    for transcript in transcripts:
        memo_id = transcript.get("obs_id")
        text_value = transcript.get("text", "").strip()
        if memo_id and text_value and memo_id not in unique:
            unique[memo_id] = {**transcript, "text": text_value}
    return sorted(unique.values(), key=lambda item: str(item["captured_at"]), reverse=True)[:20]


def _load_goal_registry() -> list[dict[str, str]]:
    """Load only IDs and titles from the canonical Personal goal registry."""
    path = Path(settings.personal_insights_path) / "archive" / "long_term_goals.md"
    try:
        return [
            {"id": goal_id, "title": title.strip()}
            for goal_id, title in _GOAL_ROW.findall(path.read_text(encoding="utf-8"))
        ]
    except OSError:
        return []


def _load_pillar_taxonomy() -> list[dict[str, object]]:
    """Load the declared taxonomy; it is category coverage, not evidence."""
    path = Path(settings.personal_insights_path) / "archive" / "pillars.txt"
    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        value = line.strip()
        if not value or value.startswith("---"):
            continue
        if not value.startswith("-"):
            current = {"name": value.replace("-", "_").replace(" ", "_"), "topics": []}
            groups.append(current)
            continue
        if current is not None:
            topic = value[1:].split(":", 1)[0].strip().replace(" ", "_")
            current["topics"].append(topic)
    return groups


def _load_behavioral_context() -> str | None:
    """Read the canonical Insights system contract, trimmed to 1500 chars."""
    insights_path = Path(settings.personal_insights_path) / "system"
    parts: list[str] = []
    for fname in ("BEHAVIOR.md", "SKILLS.md"):
        fpath = insights_path / fname
        try:
            content = fpath.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## {fname}\n{content}")
        except (OSError, FileNotFoundError):
            pass
    if not parts:
        return None
    combined = "\n\n".join(parts)
    return combined[:1500]


def _load_citation_catalog() -> list[str]:
    """Expose only local evidence paths that an insight may cite."""
    root = Path(settings.knowledge_root_path)
    base = root / "health" / "wiki"
    try:
        return [
            f"knowledge/health/wiki/{path.relative_to(base).as_posix()}"
            for path in sorted(base.rglob("*.md"))[:120]
        ]
    except OSError:
        return []


async def _compute_routine_adherence(since: date, db_session=None) -> dict | None:
    """Compare routine_calendar.json planned events vs confirmed events in DB."""
    # Load routine calendar
    routine_path = Path(settings.personal_insights_path) / "routine_objects" / "routine_calendar.json"
    if not routine_path.exists():
        return None

    try:
        with routine_path.open(encoding="utf-8") as f:
            routine_data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    events = routine_data.get("events", [])
    period_events = [
        e for e in events
        if e.get("date") and date.fromisoformat(e["date"]) >= since
    ]
    if not period_events:
        return None

    planned_titles = [e["title"].lower() for e in period_events]
    planned_count = len(period_events)

    # Query confirmed events in DB for the period
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(
                "SELECT LOWER(title) AS title FROM events "
                "WHERE scheduled_at >= :since AND status = 'confirmed'"
            ),
            {"since": since},
        )
        confirmed_titles = {r.title for r in rows.fetchall()}

    matched = sum(1 for t in planned_titles if t in confirmed_titles)
    missed = [t for t in planned_titles if t not in confirmed_titles][:10]

    return {
        "planned": planned_count,
        "confirmed": matched,
        "adherence_rate": round(matched / planned_count, 2) if planned_count else 0.0,
        "missed": missed,
    }
