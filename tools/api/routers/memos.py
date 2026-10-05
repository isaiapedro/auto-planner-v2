import mimetypes
import logging
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile

from config import settings
from database import AsyncSessionLocal
from schemas import MemoHistoryItem, MemoStatusResponse, MemoUploadResponse
from sqlalchemy import text

router = APIRouter(prefix="/memos", tags=["memos"])
logger = logging.getLogger(__name__)

_AUDIO_SUFFIXES = {".m4a", ".wav", ".mp3", ".ogg", ".opus", ".aac", ".mp4", ".webm", ".3gp", ".amr", ".flac"}
_MIME_SUFFIXES = {
    "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/ogg": ".ogg", "audio/opus": ".opus",
    "audio/aac": ".aac", "audio/webm": ".webm", "audio/flac": ".flac",
    "video/3gpp": ".3gp", "audio/3gpp": ".3gp",
}
_RECORDED_AT_HEADER = re.compile(r"^# recorded_at:\s*(.+?)\s*$", re.MULTILINE)


def _legacy_recorded_at(memo_id: str, fallback_date: str) -> tuple[datetime, bool]:
    """Recover a migrated memo's exact capture time without altering its files.

    Some older transcripts predate timestamp headers. For those, retain only
    their trustworthy date and tell the client not to render an invented time.
    """
    transcript_root = Path(settings.personal_transcripts_path).resolve()
    try:
        candidates = sorted(transcript_root.glob(f"*{memo_id}*.txt"))
        for candidate in candidates:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(transcript_root):
                continue
            header = _RECORDED_AT_HEADER.search(resolved.read_text(encoding="utf-8", errors="replace"))
            if not header:
                continue
            timestamp = datetime.fromisoformat(header.group(1).replace("Z", "+00:00"))
            return (timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc), True)
    except (OSError, ValueError):
        logger.exception("Could not recover migrated memo timestamp")
    return datetime.fromisoformat(fallback_date).replace(tzinfo=timezone.utc), False


def _read_transcript(path: str | None) -> str | None:
    """Read only a transcript inside the configured Personal vault."""
    if not path:
        return None

    try:
        transcript_root = Path(settings.personal_transcripts_path).resolve()
        transcript_path = Path(path).resolve()
        if not transcript_path.is_relative_to(transcript_root):
            logger.error("Refused memo transcript outside Personal transcript root")
            return None
        return transcript_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Could not read memo transcript")
        return None


def _legacy_memo_items() -> list[MemoHistoryItem]:
    """Expose migrated immutable records without importing them into the DB.

    Historic records predate the durable job table.  They stay canonical in
    `memos/records/`; only their original transcript section is returned.
    """
    records_dir = Path(settings.personal_memos_path) / "records"
    try:
        if not records_dir.is_dir() or not records_dir.resolve().is_relative_to(Path(settings.personal_memos_path).resolve()):
            return []
    except OSError:
        return []

    items: list[MemoHistoryItem] = []
    for record in records_dir.glob("*.md"):
        try:
            content = record.read_text(encoding="utf-8")
            obs_id = re.search(r"^obs_id:\s*([0-9a-f-]{36})\s*$", content, re.MULTILINE)
            date_value = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", content, re.MULTILINE)
            if not obs_id or not date_value:
                continue
            event = re.search(r'^event:\s*"(.*)"\s*$', content, re.MULTILINE)
            transcript = re.search(r"^## Transcript[^\n]*\n\n(.*?)(?=\n## |\Z)", content, re.MULTILINE | re.DOTALL)
            captured_at, recorded_at_known = _legacy_recorded_at(obs_id.group(1), date_value.group(1))
            items.append(MemoHistoryItem(
                id=uuid.UUID(obs_id.group(1)),
                status="done",
                event_title=event.group(1) if event else None,
                created_at=captured_at,
                recorded_at_known=recorded_at_known,
                transcript=transcript.group(1).strip() if transcript else None,
            ))
        except (OSError, ValueError):
            logger.exception("Could not read migrated memo record")
    return items


def _audio_suffix(file: UploadFile) -> str:
    """Choose a safe suffix without trusting an Android filename alone."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in _AUDIO_SUFFIXES:
        return suffix
    content_type = (file.content_type or "").lower().split(";", 1)[0]
    if content_type in _MIME_SUFFIXES:
        return _MIME_SUFFIXES[content_type]
    guessed, _ = mimetypes.guess_type(file.filename or "")
    if guessed in _MIME_SUFFIXES:
        return _MIME_SUFFIXES[guessed]
    # Android/Expo sometimes reports application/octet-stream. ffmpeg (used by
    # faster-whisper) identifies the container during transcription.
    if content_type in {"", "application/octet-stream"}:
        return ".audio"
    raise HTTPException(status_code=400, detail="The upload is not recognised as audio")


async def _create_memo_records(obs_id: str, audio_path: Path, event_title: str | None) -> None:
    """Persist the linkable observation and its transcription job together."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO observations (id, source_type, file_path, payload) "
                "VALUES (CAST(:id AS uuid), 'audio', :audio_path, CAST(:payload AS jsonb)) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": obs_id,
                "audio_path": str(audio_path),
                "payload": json.dumps({"event_title": event_title}),
            },
        )
        await db.execute(
            text(
                "INSERT INTO memo_jobs (id, audio_path, event_title, status) "
                "VALUES (CAST(:id AS uuid), :audio_path, :event_title, 'queued')"
            ),
            {"id": obs_id, "audio_path": str(audio_path), "event_title": event_title},
        )
        await db.commit()


@router.post("/upload", response_model=MemoUploadResponse)
async def upload_memo(
    file: UploadFile,
    event_title: str | None = None,
    memo_id: str | None = None,
):
    suffix = _audio_suffix(file)
    if memo_id:
        try:
            obs_id = str(uuid.UUID(memo_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="memo_id must be a UUID") from exc
    else:
        obs_id = str(uuid.uuid4())

    # Raw recordings are a primary Personal-domain record. Keep them in the
    # mounted Personal vault before accepting the job; never make duration or
    # later enrichment failures able to discard a recording.
    audio_dir = Path(settings.personal_memos_path) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    dest = audio_dir / f"{obs_id}{suffix}"
    if dest.exists():
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("SELECT status FROM memo_jobs WHERE id = CAST(:id AS uuid)"), {"id": obs_id}
            )
            status = row.scalar_one_or_none()
            if status:
                return MemoUploadResponse(job_id=obs_id, status=status)
            # An API/database interruption can happen after the atomic rename.
            # Recover that durable Personal recording rather than rejecting it.
        await _create_memo_records(obs_id, dest, event_title)
        return MemoUploadResponse(job_id=obs_id)
    partial = dest.with_suffix(dest.suffix + ".uploading")

    total = 0
    try:
        async with aiofiles.open(partial, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.memo_max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Audio file exceeds the 512 MiB safety limit")
                await f.write(chunk)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    await _create_memo_records(obs_id, dest, event_title)

    return MemoUploadResponse(job_id=obs_id)


@router.get("", response_model=list[MemoHistoryItem])
async def list_memos(limit: int | None = None):
    """Return Personal memo records, newest first.

    Audio paths and internal worker diagnostics deliberately never leave the
    Personal API. A completed transcript is read only from its configured
    Personal-domain directory. The authenticated mobile app receives the full
    history by default; callers may request a bounded prefix with ``limit``.
    """
    if limit is not None and not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    query = (
        "SELECT id, status, event_title, queued_at AS created_at, transcript_path, error "
        "FROM memo_jobs ORDER BY queued_at DESC"
    )
    if limit is not None:
        query += " LIMIT :limit"
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(query), {"limit": limit} if limit is not None else {})
        jobs = result.mappings().all()
    current_items = [
        MemoHistoryItem(
            id=job["id"],
            status=job["status"],
            event_title=job["event_title"],
            created_at=job["created_at"],
            recorded_at_known=True,
            transcript=_read_transcript(job["transcript_path"]) if job["status"] == "done" else None,
            error="Transcription could not be completed. Please retry later."
            if job["status"] == "error" else None,
        )
        for job in jobs
    ]
    current_ids = {item.id for item in current_items}
    merged = current_items + [item for item in _legacy_memo_items() if item.id not in current_ids]
    ordered = sorted(merged, key=lambda item: item.created_at, reverse=True)
    return ordered[:limit] if limit is not None else ordered


@router.get("/{job_id}/status", response_model=MemoStatusResponse)
async def get_memo_status(job_id: str):
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text("SELECT status, error FROM memo_jobs WHERE id = CAST(:id AS uuid)"), {"id": job_id}
        )
        job = row.mappings().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return MemoStatusResponse(
        job_id=job_id,
        status=job["status"],
        error="Transcription could not be completed. Please retry later."
        if job["status"] == "error" else None,
    )
