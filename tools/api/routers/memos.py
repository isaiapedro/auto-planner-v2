import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from config import settings
from schemas import MemoStatusResponse, MemoUploadResponse
from services.pipeline import process_memo_pipeline

router = APIRouter(prefix="/memos", tags=["memos"])

# In-memory job registry — sufficient for v1 single-process deployment
_job_status: dict[str, dict] = {}


@router.post("/upload", response_model=MemoUploadResponse)
async def upload_memo(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    event_title: str | None = None,
):
    if not file.filename or not file.filename.endswith((".m4a", ".wav", ".mp3", ".ogg")):
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    obs_id = str(uuid.uuid4())
    # Audio is only needed transiently for transcription — only the transcript is
    # kept permanently. process_memo_pipeline deletes this file once done.
    tmp_dir = Path(settings.evidence_vault_path) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix
    dest = tmp_dir / f"{obs_id}{suffix}"

    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    _job_status[obs_id] = {"status": "queued", "error": None}
    background_tasks.add_task(process_memo_pipeline, obs_id, str(dest), _job_status, event_title)

    return MemoUploadResponse(job_id=obs_id)


@router.get("/{job_id}/status", response_model=MemoStatusResponse)
async def get_memo_status(job_id: str):
    job = _job_status.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return MemoStatusResponse(job_id=job_id, **job)
