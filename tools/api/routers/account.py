"""Explicit Personal account triage and review-only proposal inbox."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from config import settings
from database import AsyncSessionLocal
from schemas import AccountProposalResponse, AccountRunAuditResponse, AccountTriageRequest, AccountTriageRunResponse
from services.account_triage import create_run, get_run, get_run_audit, list_proposals, resolve_proposal

router = APIRouter(prefix="/account", tags=["account"])


def _safe_transcript(path_value: str | None) -> str | None:
    if not path_value:
        return None
    try:
        root = Path(settings.personal_transcripts_path).resolve()
        path = Path(path_value).resolve()
        if not path.is_relative_to(root):
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


@router.post("/triage", response_model=AccountTriageRunResponse, status_code=201)
async def triage_memos(body: AccountTriageRequest):
    """Analyse explicitly selected completed memos; never runs automatically."""
    requested = [str(item) for item in body.memo_ids]
    if len(set(requested)) != len(requested):
        raise HTTPException(status_code=422, detail="memo_ids must be unique")
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT id::text AS id, status, transcript_path FROM memo_jobs "
            "WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": requested})
        rows = result.mappings().all()
    if len(rows) != len(requested) or any(row["status"] != "done" for row in rows):
        raise HTTPException(status_code=422, detail="Every memo_id must refer to a completed transcript")
    memo_rows = []
    for row in rows:
        transcript = _safe_transcript(row["transcript_path"])
        if transcript is None:
            raise HTTPException(status_code=409, detail="A selected completed transcript is unavailable")
        memo_rows.append({"id": row["id"], "transcript": transcript})
    try:
        return await create_run(memo_rows, body.instruction)
    except ValueError as exc:
        # The catalog is an authorization contract; refuse triage if it cannot
        # validate the selected destination vocabulary.
        raise HTTPException(status_code=503, detail="Account catalog is unavailable") from exc


@router.get("/runs", response_model=list[AccountTriageRunResponse])
async def list_runs(limit: int = Query(default=30, ge=1, le=100)):
    from services.account_triage import _inbox_root, _read_json
    paths = sorted((_inbox_root() / "runs").glob("*.json"), reverse=True)[:limit]
    return [AccountTriageRunResponse.model_validate(_read_json(path)) for path in paths]


@router.get("/runs/{run_id}", response_model=AccountTriageRunResponse)
async def read_run(run_id: str):
    try:
        return get_run(run_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Account triage run not found")


@router.get("/runs/{run_id}/audit", response_model=AccountRunAuditResponse)
async def read_run_audit(run_id: str):
    """Return provenance and lifecycle metadata only; no Personal evidence."""
    try:
        return get_run_audit(run_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Account triage audit is unavailable")


@router.get("/audit", response_model=list[AccountRunAuditResponse])
async def list_audit(limit: int = Query(default=30, ge=1, le=100)):
    """List redacted audit timelines without memo IDs, transcripts, or paths."""
    from services.account_triage import _inbox_root
    audits = []
    for path in sorted((_inbox_root() / "runs").glob("*.json"), reverse=True)[:limit]:
        try:
            audits.append(get_run_audit(path.stem))
        except (ValueError, FileNotFoundError):
            # Older runs predate provenance. Do not leak their artifact details.
            continue
    return audits


@router.get("/proposals", response_model=list[AccountProposalResponse])
async def proposals(status: str | None = Query(default="proposed")):
    try:
        return list_proposals(status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/accept", response_model=AccountProposalResponse)
async def accept_proposal(proposal_id: str):
    try:
        return resolve_proposal(proposal_id, "accepted")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Account proposal not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/dismiss", response_model=AccountProposalResponse)
async def dismiss_proposal(proposal_id: str):
    try:
        return resolve_proposal(proposal_id, "dismissed")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Account proposal not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
