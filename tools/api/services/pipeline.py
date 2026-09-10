"""Durable, transcript-only memo worker.

The HTTP request only stores audio and enqueues a database job.  This worker is
the sole place that runs Whisper, so model inference never blocks API requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from config import settings
from database import AsyncSessionLocal, ensure_memo_jobs_schema
from services import whisper as whisper_svc
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def process_memo_pipeline(
    obs_id: str,
    audio_path: str,
    event_title: str | None = None,
) -> None:
    """Create immutable transcript and observation records for a claimed job."""
    try:
        transcript = await asyncio.to_thread(whisper_svc.transcribe_sync, audio_path)

        recorded_at = datetime.now(timezone.utc)
        transcript_dir = Path(settings.personal_transcripts_path)
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_filename = f"{recorded_at.strftime('%Y-%m-%dT%H-%M-%S')}_{obs_id}.txt"
        transcript_header = f"# recorded_at: {recorded_at.isoformat()}\n\n"
        transcript_path = transcript_dir / transcript_filename
        partial_path = transcript_path.with_suffix(".txt.writing")
        async with aiofiles.open(partial_path, "w", encoding="utf-8") as f:
            await f.write(transcript_header + transcript)
        partial_path.replace(transcript_path)

        # The observation is intentionally transcript-only: no sentiment,
        # embedding, entity extraction, vault annotation, or metrics are run.
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO observations (id, source_type, file_path, payload) "
                    "VALUES (CAST(:id AS uuid), 'audio', :file_path, CAST(:payload AS jsonb)) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": obs_id, "file_path": audio_path, "payload": json.dumps({
                    "transcript_path": str(transcript_path),
                    "recorded_at": recorded_at.isoformat(), "event_title": event_title,
                })},
            )
            await db.execute(
                text(
                    "UPDATE memo_jobs SET status = 'done', transcript_path = :transcript_path, "
                    "error = NULL, completed_at = NOW(), updated_at = NOW() "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": obs_id, "transcript_path": str(transcript_path)},
            )
            await db.commit()
    except Exception as exc:
        logger.exception("Memo transcription failed for job %s", obs_id)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE memo_jobs SET "
                    "status = CASE WHEN attempts >= :max_attempts THEN 'error' ELSE 'queued' END, "
                    "error = :error, available_at = NOW() + (:retry_seconds * INTERVAL '1 second'), "
                    "updated_at = NOW() "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {
                    "id": obs_id,
                    "error": str(exc)[:2000],
                    "max_attempts": settings.memo_worker_max_attempts,
                    "retry_seconds": settings.memo_worker_retry_seconds,
                },
            )
            await db.commit()


async def _claim_next_memo_job() -> dict | None:
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text(
                "SELECT id::text, audio_path, event_title FROM memo_jobs "
                "WHERE status = 'queued' AND available_at <= NOW() ORDER BY queued_at "
                "FOR UPDATE SKIP LOCKED LIMIT 1"
            )
        )
        job = row.mappings().first()
        if job is None:
            return None
        await db.execute(
            text(
                "UPDATE memo_jobs SET status = 'transcribing', attempts = attempts + 1, "
                "started_at = NOW(), updated_at = NOW() WHERE id = CAST(:id AS uuid)"
            ),
            {"id": job["id"]},
        )
        await db.commit()
        return dict(job)


async def run_memo_worker() -> None:
    """Process one job at a time; recover interrupted jobs on every API start."""
    await ensure_memo_jobs_schema()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE memo_jobs SET status = 'queued', updated_at = NOW() WHERE status = 'transcribing'")
        )
        await db.commit()

    while True:
        job = await _claim_next_memo_job()
        if job is None:
            await asyncio.sleep(settings.memo_worker_poll_seconds)
            continue
        await process_memo_pipeline(job["id"], job["audio_path"], job["event_title"])
