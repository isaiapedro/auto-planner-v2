# PIOS v3 — Implementation Task List

Reference architecture: [[pios_v2_architecture]]

---

## Infrastructure (Cross-Cutting)

| # | Task | Status | Output |
|---|------|--------|--------|
| 1 | PostgreSQL 18 + pgvector Docker setup | ✅ done | `docker-compose.yaml`, `databases/docker-entrypoint-initdb.d/01_init_pios.sh` |
| 2 | Ollama server setup + pull required models | ✅ done | `docker-compose.yaml` ollama service auto-pulls llama3.2 + nomic-embed-text |
| 3 | faster-whisper server setup | ⬜ pending | `tools/api/services/whisper.py` ready, `.env` WHISPER_DEVICE/MODEL config needed |
| 4 | FastAPI server scaffold | ✅ done | `tools/api/` — full router + service structure |
| 5 | Expo project scaffold with expo-audio plugin | ✅ done | `mobile/` — full scaffold with all 4 tab screens |

---

## Pillar 1 — Capture (User Input)

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 6 | SQLite device schema | ✅ done | `mobile/src/db/schema.ts` — events, memos, sync_queue + typed helpers |
| 7 | Event confirmation UI state machine | ✅ done | `mobile/src/components/ConfirmEventModal.tsx` wired in Today.tsx |
| 8 | Audio recording screen (React Native) | ✅ done | `mobile/src/screens/RecordMemo.tsx` — expo-audio + upload + poll |
| 9 | First-launch schedule wizard | ✅ done | `mobile/src/screens/ScheduleWizard.tsx` — 3-step form, Σω=1.0 |
| 10 | Schedule diff view (accept/reject LLM recommendations) | ✅ done | `mobile/src/components/ScheduleDiff.tsx` wired in Insights.tsx |

### Needed Infrastructure

| # | Task | Status | Output |
|---|------|--------|--------|
| 11 | Expo push notifications setup | ✅ done | `mobile/src/notifications/index.ts` — local schedule + tap deep-link |
| 12 | SQLite local DB initialization (expo-sqlite) | ✅ done | `App.tsx` runMigrations; Today.tsx syncs via upsertEvents |
| 13 | Evidence vault directory structure on server | ✅ done | `evidence_vault/audio/`, `evidence_vault/transcripts/` |
| 14 | FastAPI memo upload + job status endpoints | ✅ done | `tools/api/routers/memos.py` (stub pipeline) |

---

## Pillar 2 — Dashboard (Deterministic)

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 15 | Metric registry definitions | ✅ done | 6 metrics seeded in `databases/pg_init.sql` |
| 16 | SQL aggregation queries for dashboard metrics | ✅ done | SQL in `metric_registry`, executed by `pipeline._recompute_metrics()` |
| 17 | Dashboard screen layout + chart components | ✅ done | `mobile/src/screens/Dashboard.tsx` — trend/gauge/bar/donut wired |

### Needed Infrastructure

| # | Task | Status | Output |
|---|------|--------|--------|
| 18 | React Native charting library setup | ✅ done | `mobile/src/components/charts.tsx` — TrendLine, TopicBars, SentimentDonut, Gauge |
| 19 | Dashboard metric recompute trigger on memo ingestion | ✅ done | `_recompute_metrics()` called at end of `pipeline.py` |

---

## Pillar 3 — Intelligence (LLM)

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 20 | LLM context builder per review period | ✅ done | `tools/api/services/llm_context.py` — build_context(period) |
| 21 | Insight schema + /insights/{period} API with caching | ✅ done | `tools/api/routers/insights.py` (schema + endpoints) |
| 22 | Schedule recommendation diff format (JSONB) | ✅ done | `schemas.py` — `ScheduleRecommendation`, `BlockChange` models |

### Needed Infrastructure

| # | Task | Status | Output |
|---|------|--------|--------|
| 23 | Claude API client in FastAPI | ✅ done | `tools/api/services/llm_client.py` — generate_insight() with cache |
| 24 | Cron scheduler for daily/weekly/monthly review triggers | ✅ done | APScheduler CronTrigger in `main.py` lifespan |

---

## Processing Pipeline

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 25 | Memo processing pipeline design | ✅ done | `tools/api/services/pipeline.py` — full 6-step async pipeline |
| 26 | Ollama feature extraction prompt + JSON Schema | ✅ done | `tools/api/services/ollama.py` — `_EXTRACT_SCHEMA` + `_EXTRACT_SYSTEM` |

---

## Database

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 27 | Full PostgreSQL DDL (pg_init.sql) | ✅ done | `databases/pg_init.sql` — 9 tables, HNSW index, 6-metric registry seed |
| 28 | Device ↔ server sync protocol | ✅ done | `tools/api/routers/sync.py` — `GET /sync/pull` |

### Needed Infrastructure

| # | Task | Status | Output |
|---|------|--------|--------|
| 30 | HNSW index + pgvector performance config | ✅ done | HNSW index with m=16, ef_construction=64 in `pg_init.sql` |

---

## Obsidian Vault

### Structural Blueprints

| # | Task | Status | Output |
|---|------|--------|--------|
| 29 | Obsidian memo .md template + writer | ✅ done | `tools/api/services/vault.py` |

---

## File Map

```
master_manager/
├── pios_v2_architecture.md          ← canonical architecture reference
├── TASKS.md                         ← this file
├── docker-compose.yaml              ← postgres (pgvector/pg18) + ollama + n8n + pios_api
├── databases/
│   ├── docker-entrypoint-initdb.d/
│   │   └── 01_init_pios.sh          ← creates pios DB + vector extension
│   └── pg_init.sql                  ← [task #27] full DDL
├── evidence_vault/
│   ├── audio/                       ← .m4a files (append-only)
│   └── transcripts/                 ← .txt transcript cache
├── master_wiki/
│   ├── memos/                       ← auto-written by vault.py
│   └── insights/                    ← weekly/monthly review .md
└── tools/
    └── api/
        ├── main.py                  ← FastAPI app + lifespan
        ├── config.py                ← pydantic-settings env config
        ├── database.py              ← async SQLAlchemy engine
        ├── schemas.py               ← all Pydantic request/response models
        ├── routers/
        │   ├── memos.py             ← POST /memos/upload, GET /memos/{id}/status
        │   ├── events.py            ← POST /events/{id}/confirm
        │   ├── schedule.py          ← GET+POST /schedule
        │   ├── dashboard.py         ← GET /dashboard
        │   ├── insights.py          ← GET /insights/{period}, POST /insights/schedule/accept
        │   └── sync.py              ← GET /sync/pull
        ├── services/
        │   ├── whisper.py           ← faster-whisper singleton + transcribe()
        │   ├── ollama.py            ← extract_features() + embed()
        │   └── vault.py             ← write_memo() → master_wiki/memos/
        ├── requirements.txt
        ├── .env.example
        └── Dockerfile
```

---

## File Map (updated)

```
mobile/
├── App.tsx                              ← root: RootNavigator + SQLite init + notif perms
├── app.json                             ← expo-audio plugin, permissions
├── tsconfig.json                        ← strict TS
├── package.json                         ← expo-audio, expo-sqlite, gifted-charts, native-stack
└── src/
    ├── config.ts                        ← API_BASE_URL, poll settings
    ├── types/index.ts                   ← all shared TypeScript types
    ├── api/client.ts                    ← typed API client (all endpoints)
    ├── db/schema.ts                     ← SQLite schema + typed repo helpers
    ├── notifications/index.ts           ← local notif schedule + tap deep-link
    ├── navigation/
    │   ├── RootNavigator.tsx            ← stack: Tabs + RecordMemo + ScheduleWizard (modals)
    │   └── TabNavigator.tsx             ← 4-tab bottom nav
    ├── components/
    │   ├── charts.tsx                   ← TrendLine, TopicBars, SentimentDonut, Gauge
    │   ├── ConfirmEventModal.tsx        ← "did it happen?" → "save memo?" flow
    │   └── ScheduleDiff.tsx             ← current→proposed block diff, accept/reject
    └── screens/
        ├── Today.tsx                    ← event list + confirm modal + memo nav + notif sync
        ├── RecordMemo.tsx               ← expo-audio recorder + upload + poll
        ├── ScheduleWizard.tsx           ← 3-step onboarding form
        ├── Dashboard.tsx                ← charts from pre-computed metrics
        ├── Insights.tsx                 ← period tabs + narrative + ScheduleDiff
        └── Schedule.tsx                 ← config view + wizard launch

tools/api/
├── main.py                              ← app + APScheduler cron
├── services/
│   ├── pipeline.py                      ← full 6-step async pipeline
│   ├── llm_client.py                    ← generate_insight() via Claude
│   ├── llm_context.py                   ← build_context() for each period
│   ├── whisper.py                       ← STT singleton
│   ├── ollama.py                        ← extract + embed
│   └── vault.py                         ← Obsidian writer
databases/
├── pg_init.sql                          ← full DDL + HNSW + metric seed
└── docker-entrypoint-initdb.d/
    └── 01_init_pios.sh                  ← creates pios DB + vector ext
```

## Remaining Tasks

| # | Task | Priority |
|---|------|----------|
| 3 | faster-whisper: configure WHISPER_DEVICE in .env for target machine | high |

**All 29 other tasks complete.** UI, backend, DB, pipeline, LLM stack all built.

### Not-yet-runnable (needs setup, not code)
- `cd mobile && npm install` — install deps, then `npx tsc --noEmit` to typecheck
- `docker compose up -d postgres` then apply `databases/pg_init.sql` to `pios` DB
- `cp tools/api/.env.example tools/api/.env` + set `CLAUDE_API_KEY`
- Set `WHISPER_DEVICE=cuda` (or `cpu`) per target machine (#3)
