-- PIOS v3 — PostgreSQL schema
-- Run against the `pios` database (created by 01_init_pios.sh)
-- Idempotent: safe to re-run

CREATE EXTENSION IF NOT EXISTS vector;

-- ─── enums ───────────────────────────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE entity_cat    AS ENUM ('person','project','concept','location');
    CREATE TYPE period_t      AS ENUM ('daily','weekly','monthly');
    CREATE TYPE status_t      AS ENUM ('pending','confirmed','skipped');
    CREATE TYPE sentiment_t   AS ENUM ('positive','neutral','negative');
    CREATE TYPE goal_kind_t   AS ENUM ('long_term','routine');
    CREATE TYPE goal_status_t AS ENUM ('active','achieved','paused');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ─── layer 1: immutable observations ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS observations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type  VARCHAR(50) NOT NULL,          -- 'audio', 'note'
    file_path    TEXT        UNIQUE,
    payload      JSONB       NOT NULL DEFAULT '{}',
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_obs_captured ON observations (captured_at DESC);

-- Durable worker queue for local-only voice transcription.  The audio path is
-- Personal-domain data and is never exposed outside this database/API boundary.
CREATE TABLE IF NOT EXISTS memo_jobs (
    id              UUID PRIMARY KEY,
    audio_path      TEXT NOT NULL UNIQUE,
    event_title     TEXT,
    status          TEXT NOT NULL CHECK (status IN ('queued', 'transcribing', 'done', 'error')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    transcript_path TEXT,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    available_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memo_jobs_queue ON memo_jobs (status, queued_at);

-- ─── legacy enrichment compatibility (read-only; no active writer) ─────────────
--
-- The memo pipeline deliberately stores only durable audio, an immutable
-- transcript, and an observation pointer. These historical tables remain so
-- existing Personal databases can be opened without destructive migration, but
-- no current API path may write sentiment, embeddings, entities, or derived
-- metrics to them. New review context reads observations and transcript files.

CREATE TABLE IF NOT EXISTS interpretations (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    obs_id        UUID        REFERENCES observations(id) ON DELETE CASCADE,
    transcript    TEXT,
    embedding     vector(768),
    mood          REAL        CHECK (mood BETWEEN 0.0 AND 1.0),
    energy        REAL        CHECK (energy BETWEEN 0.0 AND 1.0),
    topics        TEXT[]      NOT NULL DEFAULT '{}',
    sentiment     sentiment_t,
    key_takeaways TEXT[]      NOT NULL DEFAULT '{}',
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interp_obs     ON interpretations (obs_id);
CREATE INDEX IF NOT EXISTS idx_interp_date    ON interpretations (extracted_at DESC);

-- HNSW index for semantic similarity search
-- Requires maintenance_work_mem >= 1GB for fast builds
-- Set: SET maintenance_work_mem = '2GB'; before running CREATE INDEX
CREATE INDEX IF NOT EXISTS idx_interp_embedding
    ON interpretations
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ─── layer 3: entity graph ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS graph_entities (
    id         UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(255) NOT NULL,
    category   entity_cat NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity UNIQUE (name, category)
);

CREATE INDEX IF NOT EXISTS idx_entity_lookup ON graph_entities (name, category);

CREATE TABLE IF NOT EXISTS evidence_store (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id  UUID        REFERENCES graph_entities(id) ON DELETE CASCADE,
    obs_id     UUID        REFERENCES observations(id)   ON DELETE CASCADE,
    interp_id  UUID        REFERENCES interpretations(id) ON DELETE CASCADE,
    confidence REAL        NOT NULL DEFAULT 1.0,
    linked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence_store (entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_obs    ON evidence_store (obs_id);

-- ─── events (schedule) ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT        NOT NULL,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER    NOT NULL DEFAULT 60 CHECK (duration_minutes BETWEEN 5 AND 1440),
    status          status_t    NOT NULL DEFAULT 'pending',
    memo_id         UUID        REFERENCES observations(id),
    google_event_id TEXT,       -- linked Google Calendar event, for move/remove
    calendar_id     TEXT,       -- which calendar google_event_id lives on
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_schedule ON events (scheduled_at, status);
ALTER TABLE events ADD COLUMN IF NOT EXISTS routine_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_routine_key
    ON events (routine_key) WHERE routine_key IS NOT NULL;

-- ─── insights (LLM-generated) ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insights (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    period_type             period_t    NOT NULL,
    period_start            DATE        NOT NULL,
    narrative               TEXT,
    schedule_recommendation JSONB,      -- {reasoning, blocks: [{action, ...}]}
    accepted                BOOLEAN     NOT NULL DEFAULT FALSE,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_insight_period UNIQUE (period_type, period_start)
);

CREATE INDEX IF NOT EXISTS idx_insights_period ON insights (period_type, period_start DESC);

-- Enrichment columns added for deterministic insight pipeline
ALTER TABLE insights ADD COLUMN IF NOT EXISTS memo_refs          UUID[]  DEFAULT '{}';
ALTER TABLE insights ADD COLUMN IF NOT EXISTS routine_adherence  JSONB   DEFAULT NULL;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS behavioral_context TEXT    DEFAULT NULL;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS inference_bundle   JSONB   DEFAULT NULL;

-- Immutable audit trail. A review may be regenerated, but every inference and
-- validation result remains available for continuity and inspection.
CREATE TABLE IF NOT EXISTS insight_inference_logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id      UUID        REFERENCES insights(id) ON DELETE SET NULL,
    inference_type  TEXT        NOT NULL,
    schema_version  TEXT        NOT NULL,
    status          TEXT        NOT NULL CHECK (status IN ('valid', 'invalid', 'failed')),
    input_hash      TEXT        NOT NULL,
    input_snapshot  JSONB       NOT NULL DEFAULT '{}',
    output          JSONB,
    citation_paths  JSONB       NOT NULL DEFAULT '[]',
    model           TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- `life_pillars` was added to the 1.2 Personal review contract after the
-- initial audit table. Recreate the named check on every idempotent schema
-- application so existing local volumes accept all contract sections too.
ALTER TABLE insight_inference_logs
    DROP CONSTRAINT IF EXISTS insight_inference_logs_inference_type_check;
ALTER TABLE insight_inference_logs
    ADD CONSTRAINT insight_inference_logs_inference_type_check
    CHECK (inference_type IN ('routine', 'goals', 'future_plans', 'life_pillars'));

CREATE INDEX IF NOT EXISTS idx_inference_logs_insight ON insight_inference_logs (insight_id, created_at DESC);

-- ─── goals ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS goals (
    id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT          NOT NULL,
    kind        goal_kind_t   NOT NULL,       -- 'long_term' (has a deadline) | 'routine' (recurring)
    domain      TEXT,                          -- free-text category, e.g. "health", "craft"
    target_date DATE,                          -- deadline, long_term goals only
    cadence     TEXT,                          -- e.g. "daily", "3x/week" — routine goals only
    status      goal_status_t NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status);

-- ─── planning runs (transactional weekly planning drafts) ─────────────────────

CREATE TABLE IF NOT EXISTS planning_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start      DATE        NOT NULL,
    week_end        DATE        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'draft',
    user_intention  TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planning_runs_status ON planning_runs (status, created_at DESC);

-- ─── analytics: metric registry + pre-computed values ────────────────────────

CREATE TABLE IF NOT EXISTS metric_registry (
    metric_id          VARCHAR(100) PRIMARY KEY,
    name               VARCHAR(255) NOT NULL,
    sql_definition     TEXT         NOT NULL,
    aggregation_period VARCHAR(20)  NOT NULL,   -- 'daily', 'weekly', 'monthly'
    visualization_type VARCHAR(50)  NOT NULL    -- 'line', 'bar', 'donut', 'gauge', 'number'
);

CREATE TABLE IF NOT EXISTS dashboard_metrics (
    id                SERIAL      PRIMARY KEY,
    metric_id         VARCHAR(100) REFERENCES metric_registry(metric_id) ON DELETE CASCADE,
    computed_for_date DATE         NOT NULL,
    metric_value      REAL         NOT NULL,
    metadata          JSONB        NOT NULL DEFAULT '{}',
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_metric_date UNIQUE (metric_id, computed_for_date)
);

CREATE INDEX IF NOT EXISTS idx_dash_lookup ON dashboard_metrics (metric_id, computed_for_date DESC);

-- ─── seed: metric registry ────────────────────────────────────────────────────

INSERT INTO metric_registry (metric_id, name, sql_definition, aggregation_period, visualization_type)
VALUES
(
    'mood_7d_avg',
    'Mood (7-day average)',
    $sql$
        SELECT COALESCE(AVG(mood), 0.5)::REAL
        FROM interpretations
        WHERE extracted_at >= NOW() - INTERVAL '7 days'
    $sql$,
    'daily', 'line'
),
(
    'energy_7d_avg',
    'Energy (7-day average)',
    $sql$
        SELECT COALESCE(AVG(energy), 0.5)::REAL
        FROM interpretations
        WHERE extracted_at >= NOW() - INTERVAL '7 days'
    $sql$,
    'daily', 'line'
),
(
    'topic_frequency',
    'Top Topics (7 days)',
    $sql$
        SELECT COALESCE(
            (SELECT json_object_agg(topic, cnt)
             FROM (
                 SELECT unnest(topics) AS topic, COUNT(*) AS cnt
                 FROM interpretations
                 WHERE extracted_at >= NOW() - INTERVAL '7 days'
                 GROUP BY topic ORDER BY cnt DESC LIMIT 5
             ) t),
            '{}'::json
        )::TEXT
    $sql$,
    'daily', 'bar'
),
(
    'event_completion_rate',
    'Event Completion Rate (7 days)',
    $sql$
        SELECT COALESCE(
            COUNT(*) FILTER (WHERE status = 'confirmed')::REAL / NULLIF(COUNT(*), 0),
            0.0
        )::REAL
        FROM events
        WHERE scheduled_at >= NOW() - INTERVAL '7 days'
    $sql$,
    'daily', 'gauge'
),
(
    'memo_streak_days',
    'Memo Streak (consecutive days)',
    $sql$
        WITH daily AS (
            SELECT DISTINCT extracted_at::DATE AS d FROM interpretations
        ),
        grouped AS (
            SELECT d,
                   d - (ROW_NUMBER() OVER (ORDER BY d) * INTERVAL '1 day')::INTERVAL AS grp
            FROM daily
        )
        SELECT COUNT(*)::REAL
        FROM grouped
        WHERE grp = (SELECT grp FROM grouped ORDER BY d DESC LIMIT 1)
    $sql$,
    'daily', 'number'
),
(
    'sentiment_distribution',
    'Sentiment Distribution (7 days)',
    $sql$
        SELECT COALESCE(
            (SELECT json_object_agg(sentiment, cnt)
             FROM (
                 SELECT sentiment::TEXT, COUNT(*) AS cnt
                 FROM interpretations
                 WHERE extracted_at >= NOW() - INTERVAL '7 days'
                   AND sentiment IS NOT NULL
                 GROUP BY sentiment
             ) t),
            '{}'::json
        )::TEXT
    $sql$,
    'daily', 'donut'
)
ON CONFLICT (metric_id) DO NOTHING;
