"""Full memo processing pipeline — replaces stub in routers/memos.py."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import aiofiles

from config import settings
from database import AsyncSessionLocal
from schemas import MemoFeatures
from services import ollama as ollama_svc
from services import vault as vault_svc
from services import whisper as whisper_svc

from sqlalchemy import text


async def process_memo_pipeline(
    obs_id: str,
    audio_path: str,
    job_registry: dict[str, dict],
    event_title: str | None = None,
) -> None:
    """
    Full async pipeline:
      audio → STT → feature extraction → embedding → PostgreSQL → Obsidian → metrics
    Updates job_registry[obs_id] at each step for status polling.
    """
    try:
        # ── 1. transcribe ──────────────────────────────────────────────────────
        job_registry[obs_id] = {"status": "transcribing", "error": None}
        try:
            transcript = await whisper_svc.transcribe(audio_path)
        finally:
            # Audio is transient — only the transcript is kept permanently.
            Path(audio_path).unlink(missing_ok=True)

        transcript_dir = Path(settings.evidence_vault_path) / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(transcript_dir / f"{obs_id}.txt", "w") as f:
            await f.write(transcript)

        # ── 2. extract features (Ollama structured output) ─────────────────────
        job_registry[obs_id]["status"] = "extracting"
        features: MemoFeatures = await ollama_svc.extract_features(transcript)

        # ── 3. generate embedding (Ollama nomic-embed-text) ────────────────────
        job_registry[obs_id]["status"] = "embedding"
        embedding: list[float] = await ollama_svc.embed(transcript)
        embedding_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

        # ── 4. persist to PostgreSQL ───────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            # observations row — audio itself was deleted after transcription;
            # only the transcript file is kept (see payload.transcript_path).
            await db.execute(
                text(
                    "INSERT INTO observations (id, source_type, file_path, payload) "
                    "VALUES (CAST(:id AS uuid), 'audio', NULL, CAST(:payload AS jsonb)) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": obs_id,
                    "payload": json.dumps(
                        {"transcript_path": str(transcript_dir / f"{obs_id}.txt"),
                         "event_title": event_title}
                    ),
                },
            )

            # interpretations row
            interp_id = str(uuid.uuid4())
            await db.execute(
                text(
                    "INSERT INTO interpretations "
                    "(id, obs_id, transcript, embedding, mood, energy, "
                    " topics, sentiment, key_takeaways) "
                    "VALUES (CAST(:id AS uuid), CAST(:obs_id AS uuid), :transcript, "
                    "        CAST(:embedding AS vector), :mood, :energy, "
                    "        :topics, CAST(:sentiment AS sentiment_t), :takeaways)"
                ),
                {
                    "id": interp_id,
                    "obs_id": obs_id,
                    "transcript": transcript,
                    "embedding": embedding_str,
                    "mood": features.mood,
                    "energy": features.energy,
                    "topics": features.topics,
                    "sentiment": features.sentiment.value,
                    "takeaways": features.key_takeaways,
                },
            )

            # graph entities + evidence_store
            for entity in features.entities:
                ent_result = await db.execute(
                    text(
                        "INSERT INTO graph_entities (name, category) "
                        "VALUES (:name, CAST(:cat AS entity_cat)) "
                        "ON CONFLICT (name, category) "
                        "DO UPDATE SET name = EXCLUDED.name "
                        "RETURNING id"
                    ),
                    {"name": entity.name, "cat": entity.type},
                )
                entity_id = str(ent_result.fetchone()[0])

                await db.execute(
                    text(
                        "INSERT INTO evidence_store (entity_id, obs_id, interp_id) "
                        "VALUES (CAST(:eid AS uuid), CAST(:oid AS uuid), CAST(:iid AS uuid))"
                    ),
                    {"eid": entity_id, "oid": obs_id, "iid": interp_id},
                )

            await db.commit()

        # ── 5. write Obsidian vault ────────────────────────────────────────────
        await vault_svc.write_memo(obs_id, event_title, transcript, features)

        # ── 6. recompute dashboard metrics ────────────────────────────────────
        await _recompute_metrics()

        job_registry[obs_id] = {"status": "done", "error": None}

    except Exception as exc:
        job_registry[obs_id] = {"status": "error", "error": str(exc)}
        raise


async def _recompute_metrics() -> None:
    """Execute all metric_registry SQL definitions and upsert into dashboard_metrics."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("SELECT metric_id, sql_definition, visualization_type FROM metric_registry")
        )
        metrics = rows.fetchall()

        for m in metrics:
            try:
                value_row = await db.execute(text(m.sql_definition))
                raw = value_row.fetchone()
                if raw is None:
                    continue

                scalar = raw[0]
                # Non-numeric metrics (topic_frequency, sentiment_distribution) return JSON text
                if isinstance(scalar, str) and (scalar.startswith("{") or scalar.startswith("[")):
                    metric_value = 0.0
                    metadata = {"data": scalar}
                else:
                    metric_value = float(scalar) if scalar is not None else 0.0
                    metadata = {}

                await db.execute(
                    text(
                        "INSERT INTO dashboard_metrics "
                        "(metric_id, computed_for_date, metric_value, metadata) "
                        "VALUES (:mid, CURRENT_DATE, :val, CAST(:meta AS jsonb)) "
                        "ON CONFLICT (metric_id, computed_for_date) "
                        "DO UPDATE SET metric_value = EXCLUDED.metric_value, "
                        "             metadata = EXCLUDED.metadata, "
                        "             computed_at = NOW()"
                    ),
                    {"mid": m.metric_id, "val": metric_value, "meta": json.dumps(metadata)},
                )
            except Exception:
                # Don't let one bad metric kill the whole recompute
                continue

        await db.commit()
