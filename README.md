# PIOS Planner

A local-first mobile planner for capturing ideas, building routines, and organizing
the day. It works offline and syncs selected tasks through a small, authenticated API.

## What it demonstrates

- Offline mobile state with Expo, React Native, and SQLite.
- A focused FastAPI backend for planning, routines, goals, and memos.
- Clear separation between interface, domain logic, storage, and background work.

## Architecture

```text
Expo / React Native client
        │
        ├── local SQLite state and mobile notifications
        │
        └── authenticated sync
                 │
                 ▼
          FastAPI API
                 │
                 ├── planning and routines
                 ├── goals and memos
                 └── PostgreSQL
```

## Repository guide

| Path | Purpose |
| --- | --- |
| `mobile/` | Expo and React Native client, local state, and mobile UX |
| `tools/api/` | FastAPI service, routers, domain services, and API tests |
| `databases/` | Database-related development and deployment resources |

## Privacy and scope

Credentials, runtime records, and personal planning content are intentionally
excluded from the repository.
