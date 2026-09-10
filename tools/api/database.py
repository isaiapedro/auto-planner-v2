from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def ensure_memo_jobs_schema() -> None:
    """Apply the additive memo-queue migration to existing local databases.

    Fresh databases receive the same definition from `pg_init.sql`; this keeps
    an already-running Personal vault upgrade-safe without a manual reset.
    """
    from sqlalchemy import text

    async with engine.begin() as connection:
        await connection.execute(text("""
            CREATE TABLE IF NOT EXISTS memo_jobs (
                id UUID PRIMARY KEY,
                audio_path TEXT NOT NULL UNIQUE,
                event_title TEXT,
                status TEXT NOT NULL CHECK (status IN ('queued', 'transcribing', 'done', 'error')),
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                transcript_path TEXT,
                queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await connection.execute(text(
            "ALTER TABLE memo_jobs ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ))
        await connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_memo_jobs_queue ON memo_jobs (status, queued_at)"
        ))


async def ensure_insight_audit_schema() -> None:
    """Upgrade the append-only audit constraint for the complete 1.2 review.

    Initializing a new database from ``pg_init.sql`` and upgrading a persistent
    local volume must accept the same inference types. This changes only the
    allowed-value check; existing audit rows remain untouched.
    """
    from sqlalchemy import text

    async with engine.begin() as connection:
        await connection.execute(text(
            "ALTER TABLE insight_inference_logs "
            "DROP CONSTRAINT IF EXISTS insight_inference_logs_inference_type_check"
        ))
        await connection.execute(text(
            "ALTER TABLE insight_inference_logs "
            "ADD CONSTRAINT insight_inference_logs_inference_type_check "
            "CHECK (inference_type IN ('routine', 'goals', 'future_plans', 'life_pillars'))"
        ))


async def ensure_routine_occurrence_schema() -> None:
    """Add idempotency and calendar-view fields to existing event tables."""
    from sqlalchemy import text

    async with engine.begin() as connection:
        # A routine occurrence has a stable key derived from its Personal
        # source and timing.  This makes apply/sync retry-safe without using a
        # mutable display title as identity.
        await connection.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS routine_key TEXT"
        ))
        await connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_routine_key "
            "ON events (routine_key) WHERE routine_key IS NOT NULL"
        ))
        await connection.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS duration_minutes "
            "INTEGER NOT NULL DEFAULT 60"
        ))
        await connection.execute(text(
            "ALTER TABLE events DROP CONSTRAINT IF EXISTS events_duration_minutes_check"
        ))
        await connection.execute(text(
            "ALTER TABLE events ADD CONSTRAINT events_duration_minutes_check "
            "CHECK (duration_minutes BETWEEN 5 AND 1440)"
        ))


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
