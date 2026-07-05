# PIOS v3 — Personal Intelligence Operating System (Mobile)

**Revision:** v3.0 — Mobile-First Rewrite
**Supersedes:** PIOS v2 (7-layer server-centric pipeline)

---

## 1. Vision & Core Philosophy

PIOS v3 is a **local-first mobile intelligence system** for continuous personal growth. It transforms lived experience — captured as voice memos — into structured data, deterministic dashboards, and LLM-generated insights, all under full user control.

Three unyielding principles:

- **Digital Sovereignty:** Personal data processed locally first. Cloud LLM receives only anonymized summaries, never raw audio.
- **Immutable Observations:** Audio files and transcripts are append-only. Never deleted, never modified.
- **Regenerable Knowledge:** All dashboards, insights, and wiki entries are derived artifacts. Lose the DB, reconstruct from raw files.

---

## 2. Three-Pillar Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PILLAR 1: CAPTURE                                          │
│  User input — event confirmation, audio memos, schedule     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼  (async backend pipeline)
┌─────────────────────────────────────────────────────────────┐
│  PILLAR 2: DASHBOARD                                        │
│  Deterministic — SQL aggregation, zero LLM, structured data │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼  (scheduled + on-demand)
┌─────────────────────────────────────────────────────────────┐
│  PILLAR 3: INTELLIGENCE                                     │
│  LLM — insights, weekly/monthly reviews, schedule recs      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Pillar 1 — Capture (User Input)

### 3.1 Event Confirmation Flow

Every scheduled event triggers a push notification:

```
Notification: "Did you complete [Morning Run]?"
        │
        ├── YES → "Want to save an audio memo?" ──► YES → Record Screen
        │                                       └── NO  → Mark confirmed
        └── NO  → "Skipped or postponed?"       ──► Mark skipped
```

Event state machine: `pending → confirmed | skipped`

### 3.2 Free-Form Memo

User can record a memo at any time from the Home screen. Not attached to an event unless the user explicitly links it.

### 3.3 Audio Recording Stack

Tech: **React Native + Expo** with `expo-audio`

```typescript
import { useAudioRecorder, RecordingPresets } from 'expo-audio';

const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

await AudioModule.requestRecordingPermissionsAsync();
await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
await recorder.prepareToRecordAsync();
recorder.record();

// on stop:
await recorder.stop();
const uri = recorder.uri; // .m4a, 44100Hz, 128kbps AAC
```

**Preset:** `HIGH_QUALITY` → `.m4a`, 44100Hz, 2ch, 128kbps AAC
**Background recording:** Android requires foreground service + persistent notification.

→ Ref: [[raw/docs/Audio (expo-audio)|expo-audio Docs]]
→ Ref: [[blog_manager/raw/docs/react_native/components-and-apis|React Native APIs]]

### 3.4 First-Launch Schedule Wizard

Collected once at onboarding, stored in `schedule_config`:

- Wake time / sleep time
- Fixed commitments (recurring meetings, classes)
- Goal domains + weights (Σωᵢ = 1.0)
- Daily available hours

### 3.5 Schedule Change Flow (Ongoing)

```
Weekly review completes
        │
        ▼
LLM returns schedule_recommendation JSONB diff
        │
        ▼
Mobile shows: [Current Block] → [Proposed Block]  
        │
        ├── ACCEPT → POST /insights/schedule/accept → apply diff to events
        └── REJECT → discard, no state change
```

→ Ref: [[blog_manager/raw/docs/typescript/index|TypeScript]]
→ Ref: [[blog_manager/raw/docs/javascript/classes|JavaScript]]

---

## 4. Pillar 2 — Dashboard (Deterministic)

**Zero LLM involvement.** All metrics computed via SQL over `interpretations` and `events`.

### 4.1 Dashboard Metrics

| Metric | Source | Computation |
|--------|--------|-------------|
| Mood trend (7d) | `interpretations.mood` | Rolling avg |
| Energy trend (7d) | `interpretations.energy` | Rolling avg |
| Topic frequency | `interpretations.topics[]` | unnest + count |
| Event completion rate | `events.status` | confirmed / total |
| Memo streak | `observations.captured_at` | consecutive days |
| Sentiment distribution | `interpretations.sentiment` | group by |

### 4.2 Pre-computation Strategy

Metrics are computed on each memo ingestion and written to `dashboard_metrics`. The mobile app reads from this table — never runs aggregation queries directly.

```sql
INSERT INTO dashboard_metrics (metric_id, computed_for_date, metric_value)
SELECT 'mood_7d_avg', CURRENT_DATE,
       AVG(mood) FILTER (WHERE extracted_at >= NOW() - INTERVAL '7 days')
FROM interpretations
ON CONFLICT (metric_id, computed_for_date) DO UPDATE
  SET metric_value = EXCLUDED.metric_value;
```

→ Ref: [[blog_manager/raw/docs/postgresql~18/ddl-partitioning|PostgreSQL 18]]
→ Ref: [[blog_manager/raw/docs/sqlite/lang_transaction|SQLite Transactions]]

---

## 5. Pillar 3 — Intelligence (LLM)

**Triggered by:** schedule (daily/weekly/monthly) or user tap. Never automatic on memo ingestion.

### 5.1 Review Cadence

| Period | Trigger | Inputs | Outputs |
|--------|---------|--------|---------|
| Daily | Midnight cron | Last 24h transcripts + features | Summary narrative |
| Weekly | Sunday 22:00 | 7d transcripts + dashboard metrics | Insight narrative + schedule diff |
| Monthly | 1st of month | 4-week batch + all weekly insights | Identity drift analysis + long-term recs |

### 5.2 LLM Context Construction

```python
context = {
    "period": "weekly",
    "transcripts": [...],          # batch of raw transcripts
    "features_summary": {...},     # aggregated JSONB from interpretations
    "schedule_config": {...},      # current blocks + domain weights
    "dashboard_metrics": {...},    # pre-computed values
    "previous_insight": "..."      # last period's narrative for continuity
}
```

LLM receives only **anonymized, structured summaries**. No raw audio ever leaves device.

### 5.3 Insight Storage

```sql
INSERT INTO insights (period_type, period_start, narrative, schedule_recommendation, accepted)
VALUES ('weekly', '2026-06-30', '...', '{"blocks": [...]}', false);
```

→ Ref: [[blog_manager/raw/docs/fastapi/index|FastAPI]]
→ Ref: [[blog_manager/raw/docs/async/index|Async Python]]
→ Ref: [[blog_manager/raw/docs/python~3.14/glossary|Python 3.14]]

---

## 6. Backend Processing Pipeline

```
[Mobile: .m4a audio upload]
          │
          ▼
[FastAPI POST /memos/upload]
  - saves file to evidence_vault/audio/
  - creates observations record
  - enqueues background task
          │
          ▼ (asyncio background task)
[faster-whisper → transcript]
  WhisperModel("large-v3", device="cuda", compute_type="float16")
  segments, info = model.transcribe(audio_path, vad_filter=True)
          │
          ▼
[Ollama /api/chat + JSON Schema → feature extraction]
  POST localhost:11434/api/chat
  format: { "type": "object", "properties": {...} }
  → mood, energy, topics, entities, sentiment, key_takeaways
          │
          ▼
[Ollama /api/embed → vector(768)]
  POST localhost:11434/api/embed
  model: "nomic-embed-text"
          │
          ├──► SQLite (device sync copy via /sync endpoint)
          ├──► PostgreSQL + pgvector (server)
          └──► Obsidian vault .md write
```

→ Ref: [[raw/docs/faster-whisper Guide Fast Local Speech-to-Text with Whisper, CUDA, and Batching|faster-whisper Guide]]
→ Ref: [[raw/docs/Ollama Structured Chat API|Ollama Structured Chat API]]
→ Ref: [[blog_manager/raw/docs/requests/index|Python Requests]]

---

## 7. Feature Extraction Schema

Ollama structured output JSON Schema enforced via `format` field:

```json
{
  "type": "object",
  "properties": {
    "mood":            { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "energy":          { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "topics":          { "type": "array",  "items": { "type": "string" } },
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "type": { "type": "string", "enum": ["person","project","concept","location"] }
        },
        "required": ["name", "type"]
      }
    },
    "sentiment":       { "type": "string", "enum": ["positive","neutral","negative"] },
    "key_takeaways":   { "type": "array",  "items": { "type": "string" } },
    "event_confirmed": { "type": "boolean" }
  },
  "required": ["mood","energy","topics","entities","sentiment","key_takeaways"]
}
```

---

## 8. Data Model

### 8.1 SQLite — Device Local (offline-first buffer)

```sql
CREATE TABLE events (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,   -- ISO 8601
    status      TEXT DEFAULT 'pending' CHECK (status IN ('pending','confirmed','skipped')),
    memo_id     TEXT REFERENCES memos(id)
);

CREATE TABLE memos (
    id            TEXT PRIMARY KEY,
    audio_path    TEXT NOT NULL,
    transcript    TEXT,
    features_json TEXT,            -- JSON blob, denormalized for local reads
    synced_at     TEXT             -- NULL until server confirms
);

CREATE TABLE sync_queue (
    memo_id      TEXT PRIMARY KEY,
    retry_count  INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);
```

→ Ref: [[blog_manager/raw/docs/sqlite/lang_transaction|SQLite Transactions]]

### 8.2 PostgreSQL — Server

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE entity_cat AS ENUM ('person','project','concept','location');
CREATE TYPE period_t   AS ENUM ('daily','weekly','monthly');
CREATE TYPE status_t   AS ENUM ('pending','confirmed','skipped');
CREATE TYPE sentiment_t AS ENUM ('positive','neutral','negative');

-- Immutable observations (append-only)
CREATE TABLE observations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type  VARCHAR(50) NOT NULL,  -- 'audio', 'note'
    file_path    TEXT UNIQUE,
    payload      JSONB NOT NULL,
    captured_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Interpreted features + semantic embedding
CREATE TABLE interpretations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    obs_id       UUID REFERENCES observations(id) ON DELETE CASCADE,
    transcript   TEXT,
    embedding    vector(768),            -- nomic-embed-text
    mood         REAL CHECK (mood BETWEEN 0.0 AND 1.0),
    energy       REAL CHECK (energy BETWEEN 0.0 AND 1.0),
    topics       TEXT[],
    sentiment    sentiment_t,
    key_takeaways TEXT[],
    extracted_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Graph entities extracted from transcripts
CREATE TABLE graph_entities (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name     VARCHAR(255) NOT NULL,
    category entity_cat NOT NULL,
    CONSTRAINT uq_entity UNIQUE (name, category)
);

-- Evidence links: entity ↔ observation ↔ interpretation
CREATE TABLE evidence_store (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   UUID REFERENCES graph_entities(id) ON DELETE CASCADE,
    obs_id      UUID REFERENCES observations(id) ON DELETE CASCADE,
    interp_id   UUID REFERENCES interpretations(id) ON DELETE CASCADE,
    confidence  REAL DEFAULT 1.0,
    linked_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Scheduled events
CREATE TABLE events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title        TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status       status_t DEFAULT 'pending',
    obs_id       UUID REFERENCES observations(id)
);

-- LLM-generated insights + schedule recommendations
CREATE TABLE insights (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_type              period_t NOT NULL,
    period_start             DATE NOT NULL,
    narrative                TEXT,
    schedule_recommendation  JSONB,     -- diff: [{block_id, old, new}]
    accepted                 BOOLEAN DEFAULT FALSE,
    generated_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Pre-computed dashboard values
CREATE TABLE dashboard_metrics (
    id               SERIAL PRIMARY KEY,
    metric_id        VARCHAR(100) NOT NULL,
    computed_for_date DATE NOT NULL,
    metric_value     REAL NOT NULL,
    metadata         JSONB DEFAULT '{}'::jsonb,
    computed_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_metric_date UNIQUE (metric_id, computed_for_date)
);

-- Schedule config (set on first launch, modified via LLM recommendations)
CREATE TABLE schedule_config (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wake_time    TIME NOT NULL,
    sleep_time   TIME NOT NULL,
    domain_weights JSONB NOT NULL,  -- {"technology": 0.3, "health": 0.2, ...}
    fixed_blocks JSONB NOT NULL,    -- [{title, days, start, duration}]
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX ON observations (captured_at);
CREATE INDEX ON interpretations USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON interpretations (extracted_at);
CREATE INDEX ON events (scheduled_at, status);
CREATE INDEX ON dashboard_metrics (metric_id, computed_for_date);
```

**HNSW config** (from [[raw/docs/pgvector README|pgvector README]]):

```sql
-- On server with sufficient RAM:
SET maintenance_work_mem = '2GB';
CREATE INDEX ON interpretations USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

→ Ref: [[raw/docs/pgvector README|pgvector README]]
→ Ref: [[raw/docs/pgvector-python examples|pgvector-python bulk load]]
→ Ref: [[blog_manager/raw/docs/postgresql~18/ddl-partitioning|PostgreSQL 18 Partitioning]]

---

## 9. API Design (FastAPI)

```
POST   /memos/upload              → ingest audio, queue processing      (Pillar 1, no LLM)
GET    /memos/{job_id}/status     → poll processing state               (Pillar 1, no LLM)
POST   /events/{id}/confirm       → confirm event, link memo            (Pillar 1, no LLM)
POST   /schedule                  → create initial schedule             (Pillar 1, no LLM)
GET    /schedule                  → fetch current schedule              (Pillar 1, no LLM)
GET    /dashboard                 → pre-computed metrics JSON           (Pillar 2, no LLM)
GET    /insights/{period}         → cached narrative + recommendation   (Pillar 3, LLM cached)
POST   /insights/schedule/accept  → apply recommendation diff          (Pillar 3, no LLM)
GET    /sync/pull                 → pull server state to SQLite         (internal, no LLM)
```

**Async processing** via `asyncio` background tasks — no Celery for v1:

```python
from fastapi import FastAPI, BackgroundTasks, UploadFile
import asyncio

app = FastAPI()

@app.post("/memos/upload")
async def upload_memo(file: UploadFile, background_tasks: BackgroundTasks):
    obs_id = save_to_evidence_vault(file)
    background_tasks.add_task(process_memo_pipeline, obs_id)
    return {"job_id": obs_id, "status": "queued"}

async def process_memo_pipeline(obs_id: str):
    audio_path = get_audio_path(obs_id)
    transcript = await run_whisper(audio_path)        # faster-whisper
    features   = await run_ollama_extract(transcript) # Ollama structured output
    embedding  = await run_ollama_embed(transcript)   # Ollama /api/embed
    await write_to_postgres(obs_id, transcript, features, embedding)
    await write_to_obsidian(obs_id, transcript, features)
    await recompute_dashboard_metrics()
```

→ Ref: [[blog_manager/raw/docs/fastapi/index|FastAPI]]
→ Ref: [[blog_manager/raw/docs/async/index|Async Python]]
→ Ref: [[blog_manager/raw/docs/python~3.14/glossary|Python 3.14]]
→ Ref: [[blog_manager/raw/docs/requests/index|Python Requests]]

---

## 10. Obsidian Vault Integration

Every processed memo writes a `.md` file to `master_wiki/memos/`:

**Path:** `master_wiki/memos/YYYY-MM-DD-{obs_id[:8]}.md`

```markdown
---
date: 2026-07-04
obs_id: a3f9c12e
event: "Morning Run"
mood: 0.82
energy: 0.75
topics: [fitness, recovery, breathing]
sentiment: positive
---

## Transcript ^[extracted]

Full verbatim transcript text here...

## Key Takeaways ^[inferred]

- Noticed breathing improved vs last week
- Right knee discomfort flagged — monitor

## Entities ^[inferred]

| Name | Type |
|------|------|
| Morning Run | project |
| Right Knee | concept |
```

**Boundary enforcement:** Writer validates `target_path.startswith("master_wiki/memos/")` before writing.

Provenance tags per CLAUDE.md: `^[extracted]` on transcript, `^[inferred]` on features.

→ Ref: [[blog_manager/raw/docs/markdown/index|Markdown]]

---

## 11. Schedule System

### 11.1 Two-Block Model (inherited from v2)

```
W = 168h total weekly time
S = 56h  sleep (non-negotiable)
A = 112h available
T(F) = Σ fixed block durations
T(E) = A - T(F)             ← exploration budget
T(Dᵢ) = ωᵢ × T(E)          ← per-domain allocation
Σ ωᵢ = 1.0

Projects consume from parent domain:
Σ T(Pⱼ) ≤ T(Dᵢ)
```

### 11.2 First-Launch Wizard

Collected once: wake time, sleep time, fixed commitments, domain weights.
Written to `schedule_config` table. Rendered in mobile as step-by-step form.

### 11.3 LLM Recommendation Diff Format

```json
{
  "schedule_recommendation": {
    "reasoning": "Energy metrics show afternoon dip. Recommend moving deep work earlier.",
    "blocks": [
      {
        "action": "move",
        "block_id": "uuid-of-existing-block",
        "field": "scheduled_at",
        "old": "2026-07-07T15:00:00",
        "new": "2026-07-07T09:00:00"
      },
      {
        "action": "add",
        "title": "Recovery walk",
        "domain": "health",
        "scheduled_at": "2026-07-07T15:30:00",
        "duration_minutes": 30
      }
    ]
  }
}
```

User reviews diff on mobile → Accept (apply all) or Reject (discard).

---

## 12. Mobile Screen Map

```
Tab: Today
  ├── Event list with [Confirm / Skip] buttons
  └── [+ Free Memo] button → Record screen

Tab: Dashboard  (Pillar 2)
  ├── Mood trend chart (7d)
  ├── Energy trend chart (7d)
  ├── Topic cloud
  ├── Event completion rate
  └── Memo streak

Tab: Insights  (Pillar 3)
  ├── Daily summary
  ├── Weekly review + schedule diff
  └── Monthly identity report

Tab: Schedule
  ├── Week view (fixed + exploration blocks)
  └── Pending recommendation banner (if any)

Settings
  ├── Schedule wizard (first launch)
  └── Domain weight editor
```

---

## 13. AI Model Allocation

| Task | Model | Location | LLM? |
|------|-------|----------|------|
| Speech-to-text | faster-whisper `large-v3` | Local server | No |
| Feature extraction | Ollama `llama3.2` + JSON Schema | Local server | Yes (local) |
| Embeddings | Ollama `nomic-embed-text` 768d | Local server | Yes (local) |
| Insights / reviews | Claude (claude-sonnet-5) | Cloud API | Yes (cloud) |
| Schedule recommendations | Claude (claude-sonnet-5) | Cloud API | Yes (cloud) |

**Data boundary:** Raw audio never leaves local network. Cloud LLM receives only structured JSONB summaries.

---

## 14. Folder Structure

```
/home/pedrosouza/pessoal/master_manager/
├── CLAUDE.md                        # Orchestrator rules
├── pios_v2_architecture.md          # This document
├── databases/
│   ├── raw_observations.db          # SQLite: device sync mirror
│   └── pg_init.sql                  # PostgreSQL schema DDL
├── evidence_vault/
│   ├── audio/                       # Immutable .m4a files
│   └── transcripts/                 # Raw transcript .txt files
├── master_wiki/
│   ├── index.md
│   ├── log.md
│   ├── memos/                       # Auto-written by pipeline
│   ├── insights/                    # Weekly/monthly review .md
│   └── entities/
├── blog_manager/                    # Read-only reference
├── wiki_tcc/                        # Read-only reference
├── raw/
│   └── docs/                        # Read-only reference docs
└── tools/
    ├── process_memo.py              # STT + feature extraction worker
    ├── compute_metrics.py           # Dashboard pre-computation
    ├── write_obsidian.py            # Vault materialization
    └── n8n_mcp_server.py            # n8n REST MCP bridge
```

---

## 15. Reference Documentation

All external docs available locally as devdocs sets in `blog_manager/raw/docs/`.

| Technology | Role in PIOS v3 | Obsidian Link |
|-----------|----------------|---------------|
| React Native | Mobile app, screens, navigation | [[blog_manager/raw/docs/react_native/components-and-apis\|React Native]] |
| TypeScript | Mobile type safety | [[blog_manager/raw/docs/typescript/index\|TypeScript]] |
| JavaScript | Mobile runtime, async patterns | [[blog_manager/raw/docs/javascript/classes\|JavaScript]] |
| FastAPI | Backend API server | [[blog_manager/raw/docs/fastapi/index\|FastAPI]] |
| Python 3.14 | Backend language | [[blog_manager/raw/docs/python~3.14/glossary\|Python 3.14]] |
| PostgreSQL 18 | Server DB + pgvector | [[blog_manager/raw/docs/postgresql~18/ddl-partitioning\|PostgreSQL 18]] |
| SQLite | Device-local offline buffer | [[blog_manager/raw/docs/sqlite/lang_transaction\|SQLite]] |
| Requests | HTTP client in Python workers | [[blog_manager/raw/docs/requests/index\|Requests]] |
| Async | asyncio patterns for pipeline | [[blog_manager/raw/docs/async/index\|Async]] |
| Markdown | Obsidian vault note format | [[blog_manager/raw/docs/markdown/index\|Markdown]] |

**Raw docs used directly (in `raw/docs/`):**

| Doc | Usage |
|-----|-------|
| [[raw/docs/Audio (expo-audio)\|expo-audio]] | `useAudioRecorder` hooks, background recording setup |
| [[raw/docs/faster-whisper Guide Fast Local Speech-to-Text with Whisper, CUDA, and Batching\|faster-whisper]] | STT model config, `WhisperModel`, VAD filter |
| [[raw/docs/pgvector README\|pgvector README]] | HNSW index params, operator reference |
| [[raw/docs/pgvector-python examples\|pgvector-python]] | Bulk binary COPY load pattern |
| [[raw/docs/Ollama Structured Chat API\|Ollama Structured Chat API]] | `/api/chat` + JSON Schema, `/api/embed` |
