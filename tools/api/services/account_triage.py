"""Private, command-triggered memo triage with typed, reviewable destinations.

The service intentionally keeps raw transcript text in-process only.  Durable
run and proposal artifacts contain IDs and SHA-256 evidence hashes, never
transcript content, source paths, or arbitrary model-selected file paths.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from config import settings
from schemas import (
    AccountAuditEventResponse,
    AccountProposalResponse,
    AccountRunAuditResponse,
    AccountTriageRunResponse,
)
from services.llm.ollama import OllamaPlanner
from services.observability import log_event


_KINDS = {
    "planner_future_task": "personal_planner",
    "career_note": "personal_career_strategy",
    "finance_note": "personal_finance",
    # This is deliberately an outbound *request*, not a write into Knowledge:
    # private observations must not be copied into an objective knowledge domain.
    "knowledge_technology_research_request": "knowledge_technology",
    "manual_review": "personal_planner",
}
_MAX_TRANSCRIPT_CHARS = 12_000
_TRIAGE_SCHEMA_VERSION = "1.0"
_LOGGER = logging.getLogger(__name__)
_SYSTEM_INSTRUCTION = (
    "You route private personal memos into a review inbox. Return only structured proposals. "
    "Never claim facts not stated in a memo. Never choose paths, write files, schedule work, "
    "or infer health/psychological state. A knowledge request is only a research question, "
    "not a conclusion or an instruction to ingest sources."
)


class _ModelProposal(BaseModel):
    kind: Literal[
        "planner_future_task", "career_note", "finance_note",
        "knowledge_technology_research_request", "manual_review",
    ]
    title: str = Field(min_length=1, max_length=140)
    summary: str = Field(min_length=1, max_length=800)
    confidence: Literal["high", "medium", "low"]
    memo_ids: list[str] = Field(min_length=1, max_length=20)


class _ModelOutput(BaseModel):
    proposals: list[_ModelProposal] = Field(default_factory=list, max_length=12)


def _inbox_root() -> Path:
    # `personal_insights_path` is Personal/planner/insights; its parent is the
    # declared Planner vault. This avoids a second mutable root configuration.
    root = (Path(settings.personal_insights_path).resolve().parent / "account_inbox")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _personal_root() -> Path:
    """Resolve the mounted Personal root from the declared Planner vault."""
    return Path(settings.personal_insights_path).resolve().parents[1]


def _validate_catalog_target(target: str) -> str:
    """Refuse routing if the checked-in catalog no longer authorizes it.

    The account catalog is a required authorization contract. Missing or
    malformed contracts stop triage rather than silently widening authority.
    """
    if target not in set(_KINDS.values()):
        raise ValueError("Unsupported account proposal target")
    try:
        from services.account_catalog import AccountCatalogError, validate_account_catalog
        validate_account_catalog().require_destination(target)
    except (ImportError, AttributeError) as exc:
        # A partial deployment must never widen routing privileges.
        raise ValueError("Account catalog is unavailable") from exc
    except AccountCatalogError as exc:
        raise ValueError("Account proposal target is not authorized by catalog") from exc
    return target


def _validate_catalog_targets(targets: set[str]) -> tuple[str, str]:
    """Validate all required targets against one complete contract snapshot."""
    try:
        from services.account_catalog import AccountCatalogError, validate_account_catalog
        result = validate_account_catalog()
        for target in targets:
            result.require_destination(target)
        return result.catalog_fingerprint, result.catalog.schema_version
    except (ImportError, AttributeError) as exc:
        raise ValueError("Account catalog is unavailable") from exc
    except AccountCatalogError as exc:
        raise ValueError("Account proposal target is not authorized by catalog") from exc


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.writing")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(partial, path)


def _atomic_create_json(path: Path, payload: dict) -> bool:
    """Publish an immutable JSON artifact, returning False if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.writing")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        # hard-link publication is atomic and refuses to replace an existing
        # artifact. Both files are inside one Personal mount.
        os.link(partial, path)
        return True
    except FileExistsError:
        return False
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _proposal_lock(proposal_id: str):
    """Serialize resolution of a single proposal across API workers."""
    import fcntl

    lock_path = _inbox_root() / ".locks" / f"{proposal_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Account inbox artifact is invalid") from exc


def _public_proposal(payload: dict) -> AccountProposalResponse:
    # Deliberately whitelist public fields; evidence hashes and internal paths
    # remain artifact-only, and raw memo material is never serialised here.
    return AccountProposalResponse.model_validate({
        key: payload[key] for key in (
            "id", "run_id", "kind", "target", "title", "summary", "confidence",
            "status", "requires_confirmation", "memo_ids", "created_at", "resolved_at",
        )
    })


def _resolution_events(proposal_id: str) -> list[dict]:
    root = _inbox_root() / "resolution_events" / proposal_id
    return [_read_json(path) for path in sorted(root.glob("*.json"))]


def _with_resolution(payload: dict) -> dict:
    """Derive mutable-looking API state from immutable artifacts only."""
    events = _resolution_events(payload["id"])
    if not events:
        return {**payload, "status": "proposed", "resolved_at": None}
    if len(events) != 1:
        raise ValueError("Account proposal has an invalid resolution history")
    event = events[0]
    resolution = event.get("resolution")
    if resolution not in {"accepted", "dismissed"}:
        raise ValueError("Account proposal has an invalid resolution history")
    return {**payload, "status": resolution, "resolved_at": event.get("occurred_at")}


def _safe_error_class(error: Exception) -> str:
    """Expose only a bounded failure category, never model/library details."""
    if isinstance(error, (TimeoutError,)):
        return "timeout"
    if isinstance(error, (ValueError,)):
        return "validation"
    return "model_unavailable"


def _log_lifecycle(name: str, **event: object) -> None:
    """Only IDs, counts, categories, timings, model names and error classes."""
    log_event(_LOGGER, name, **event)


def _proposal_path(proposal_id: str) -> Path:
    try:
        canonical = str(uuid.UUID(proposal_id))
    except ValueError as exc:
        raise ValueError("Invalid proposal ID") from exc
    return _inbox_root() / "proposals" / f"{canonical}.json"


async def create_run(
    memo_rows: list[dict], instruction: str | None,
) -> AccountTriageRunResponse:
    """Create an immutable triage run from explicitly selected completed memos."""
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    allowed_ids = {str(row["id"]) for row in memo_rows}
    try:
        catalog_sha256, catalog_schema_version = _validate_catalog_targets(set(_KINDS.values()))
        # Validate every possible fixed mapping before sending private content to
        # the model. This prevents a stale/malformed contract from becoming an
        # LLM-routing side channel.
    except ValueError as exc:
        _log_lifecycle(
            "account_catalog_denied", run_id=str(run_id), memo_count=len(allowed_ids),
            outcome="denied", error_class="catalog_invalid",
        )
        raise
    instruction_hash = hashlib.sha256((instruction or "").encode("utf-8")).hexdigest()
    model_id = settings.ollama_planning_model
    _log_lifecycle(
        "account_triage_started", run_id=str(run_id), memo_count=len(allowed_ids),
        model_id=model_id, outcome="started",
    )
    transcript_context = []
    evidence = []
    for row in memo_rows:
        transcript = row["transcript"]
        transcript_context.append({"memo_id": str(row["id"]), "text": transcript[:_MAX_TRANSCRIPT_CHARS]})
        evidence.append({
            "memo_id": str(row["id"]),
            "transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        })

    used_llm = False
    status = "completed"
    model_proposals: list[_ModelProposal]
    fallback_error_class: str | None = None
    try:
        output = await OllamaPlanner().generate_structured(
            system_prompt=_SYSTEM_INSTRUCTION,
            user_prompt=json.dumps({
                "instruction": instruction or "Route actionable items into typed proposals.",
                "allowed_kinds": sorted(_KINDS),
                "memos": transcript_context,
            }),
            schema=_ModelOutput.model_json_schema(),
        )
        parsed = _ModelOutput.model_validate(output)
        # Reject stray memo IDs rather than allowing the model to attach unseen
        # evidence to a proposal.
        model_proposals = [
            proposal for proposal in parsed.proposals
            if set(proposal.memo_ids).issubset(allowed_ids)
        ]
        used_llm = True
    except Exception as exc:
        # Availability of local Ollama is not a reason to drop captured memos.
        # A deterministic proposal keeps the run visible for manual routing.
        status = "needs_manual_review"
        fallback_error_class = _safe_error_class(exc)
        model_proposals = [_ModelProposal(
            kind="manual_review",
            title="Review selected memos for account routing",
            summary="Local synthesis was unavailable. Review this private memo set and choose a destination manually.",
            confidence="low",
            memo_ids=sorted(allowed_ids),
        )]

    proposal_ids: list[uuid.UUID] = []
    for proposal in model_proposals:
        proposal_id = uuid.uuid4()
        proposal_ids.append(proposal_id)
        _atomic_create_json(_proposal_path(str(proposal_id)), {
            "id": str(proposal_id), "run_id": str(run_id), "kind": proposal.kind,
            "target": _validate_catalog_target(_KINDS[proposal.kind]), "title": proposal.title.strip(),
            "summary": proposal.summary.strip(), "confidence": proposal.confidence,
            "status": "proposed", "requires_confirmation": True,
            "memo_ids": proposal.memo_ids, "created_at": now.isoformat(), "resolved_at": None,
            "evidence": [item for item in evidence if item["memo_id"] in proposal.memo_ids],
        })

    # This run is immutable: it records only evidence hashes plus proposal IDs.
    duration_ms = int((time.perf_counter() - started) * 1000)
    completed_at = datetime.now(timezone.utc).isoformat()
    _atomic_create_json(_inbox_root() / "runs" / f"{run_id}.json", {
        "id": str(run_id), "status": status, "memo_ids": sorted(allowed_ids),
        "proposal_ids": [str(item) for item in proposal_ids], "used_llm": used_llm,
        "created_at": now.isoformat(), "completed_at": completed_at, "evidence": evidence,
        "provenance": {
            "model_id": model_id, "catalog_sha256": catalog_sha256,
            "catalog_schema_version": catalog_schema_version,
            "triage_schema_version": _TRIAGE_SCHEMA_VERSION,
            "instruction_sha256": instruction_hash, "duration_ms": duration_ms,
            "outcome": "completed" if used_llm else "fallback",
            "error_class": fallback_error_class,
        },
    })
    if used_llm:
        _log_lifecycle(
            "account_triage_completed", run_id=str(run_id), memo_count=len(allowed_ids),
            proposal_count=len(proposal_ids), duration_ms=duration_ms, model_id=model_id,
            outcome="completed",
        )
    else:
        _log_lifecycle(
            "account_triage_fallback", run_id=str(run_id), memo_count=len(allowed_ids),
            proposal_count=len(proposal_ids), duration_ms=duration_ms, model_id=model_id,
            outcome="fallback", error_class=fallback_error_class,
        )
    return AccountTriageRunResponse(
        id=run_id, status=status, memo_ids=[uuid.UUID(item) for item in sorted(allowed_ids)],
        proposal_ids=proposal_ids, used_llm=used_llm, created_at=now,
    )


def list_proposals(status: str | None = None) -> list[AccountProposalResponse]:
    if status is not None and status not in {"proposed", "accepted", "dismissed"}:
        raise ValueError("Invalid proposal status")
    paths = sorted((_inbox_root() / "proposals").glob("*.json"), reverse=True)
    rows = [_with_resolution(_read_json(path)) for path in paths]
    return [_public_proposal(row) for row in rows if status is None or row.get("status") == status]


def get_run(run_id: str) -> AccountTriageRunResponse:
    try:
        canonical = str(uuid.UUID(run_id))
    except ValueError as exc:
        raise ValueError("Invalid run ID") from exc
    payload = _read_json(_inbox_root() / "runs" / f"{canonical}.json")
    return AccountTriageRunResponse.model_validate(payload)


def get_run_audit(run_id: str) -> AccountRunAuditResponse:
    """Return a redacted, metadata-only lifecycle timeline for one run."""
    try:
        canonical = str(uuid.UUID(run_id))
    except ValueError as exc:
        raise ValueError("Invalid run ID") from exc
    payload = _read_json(_inbox_root() / "runs" / f"{canonical}.json")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Account triage run has no provenance")
    events: list[dict] = [{
        "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"account:triage-start:{canonical}")),
        "event_type": "triage_started", "occurred_at": payload["created_at"], "run_id": canonical,
        "memo_count": len(payload.get("memo_ids", [])), "model_id": provenance.get("model_id"),
        "outcome": "started",
    }, {
        "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"account:triage:{canonical}")),
        "event_type": "triage_completed" if provenance.get("outcome") == "completed" else "triage_fallback",
        "occurred_at": payload.get("completed_at", payload["created_at"]), "run_id": canonical,
        "memo_count": len(payload.get("memo_ids", [])),
        "proposal_count": len(payload.get("proposal_ids", [])),
        "duration_ms": provenance.get("duration_ms"), "model_id": provenance.get("model_id"),
        "outcome": provenance.get("outcome"), "error_class": provenance.get("error_class"),
    }]
    for proposal_id in payload.get("proposal_ids", []):
        for event in _resolution_events(str(proposal_id)):
            events.append({
                "event_id": event["id"],
                "event_type": f"proposal_{event['resolution']}",
                "occurred_at": event["occurred_at"], "run_id": canonical,
                "proposal_id": str(proposal_id), "proposal_kind": event["proposal_kind"],
                "target": event["target"], "outcome": event["resolution"],
            })
    events.sort(key=lambda item: (item["occurred_at"], item["event_id"]))
    return AccountRunAuditResponse.model_validate({
        "run_id": canonical, "status": payload["status"], "created_at": payload["created_at"],
        "model_id": provenance.get("model_id"), "catalog_sha256": provenance["catalog_sha256"],
        "catalog_schema_version": provenance["catalog_schema_version"],
        "triage_schema_version": provenance["triage_schema_version"],
        "instruction_sha256": provenance["instruction_sha256"],
        "duration_ms": provenance.get("duration_ms"), "outcome": provenance["outcome"],
        "events": events,
    })


def _accepted_destination(payload: dict) -> Path:
    """Return the only append-only target path permitted for a proposal kind."""
    proposal_id = str(uuid.UUID(payload["id"]))
    kind = payload["kind"]
    if kind == "planner_future_task":
        return _inbox_root() / "accepted" / "personal_planner" / f"{proposal_id}.json"
    if kind == "career_note":
        return _personal_root() / "career_strategy" / "account_notes" / f"{proposal_id}.json"
    if kind == "finance_note":
        return _personal_root() / "finance" / "account_notes" / f"{proposal_id}.json"
    if kind == "knowledge_technology_research_request":
        # Knowledge stays objective. This is an outbound, private request for
        # later source selection and explicit ingestion—not a Knowledge write.
        return _inbox_root() / "outbound_research_requests" / f"{proposal_id}.json"
    if kind == "manual_review":
        return _inbox_root() / "accepted" / "manual_review" / f"{proposal_id}.json"
    raise ValueError("Unsupported account proposal kind")


def resolve_proposal(proposal_id: str, resolution: Literal["accepted", "dismissed"]) -> AccountProposalResponse:
    path = _proposal_path(proposal_id)
    if not path.is_file():
        raise FileNotFoundError("Proposal not found")
    with _proposal_lock(proposal_id):
        payload = _read_json(path)
        effective = _with_resolution(payload)
        if effective["status"] != "proposed":
            if effective["status"] == resolution:
                return _public_proposal(effective)
            raise ValueError("Proposal has already been resolved differently")
        now = datetime.now(timezone.utc).isoformat()
        if resolution == "accepted":
            try:
                _validate_catalog_target(payload["target"])
            except ValueError:
                _log_lifecycle(
                    "account_catalog_denied", proposal_id=payload["id"], proposal_kind=payload["kind"],
                    target=payload["target"], outcome="denied", error_class="catalog_invalid",
                )
                raise
            # A fixed adapter path makes acceptance useful without allowing a
            # model-provided path or broad domain mutation. It is published once
            # before the immutable resolution event.
            _atomic_create_json(_accepted_destination(payload), {
                "proposal_id": payload["id"], "kind": payload["kind"], "target": payload["target"],
                "title": payload["title"], "summary": payload["summary"],
                "memo_ids": payload["memo_ids"], "accepted_at": now,
            })
        event = {
            "id": str(uuid.uuid4()), "proposal_id": payload["id"], "run_id": payload["run_id"],
            "resolution": resolution, "proposal_kind": payload["kind"], "target": payload["target"],
            "occurred_at": now,
        }
        if not _atomic_create_json(
            _inbox_root() / "resolution_events" / payload["id"] / f"{event['id']}.json", event,
        ):
            raise ValueError("Could not record proposal resolution")
        _log_lifecycle(
            f"account_proposal_{resolution}", run_id=payload["run_id"], proposal_id=payload["id"],
            proposal_kind=payload["kind"], target=payload["target"], outcome=resolution,
        )
        return _public_proposal(_with_resolution(payload))
