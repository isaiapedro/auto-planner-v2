# PIOS Planner

> A local-first planning system that combines fast mobile capture, intentional routines, and a privacy-aware API layer.

**Portfolio focus:** Expo · React Native · FastAPI · SQLite · PostgreSQL · mobile-first product architecture

## Why it matters

PIOS Planner is designed around a simple constraint: planning tools are most useful
when capture is quick, day-to-day state works offline, and sensitive personal
context is handled deliberately. The project explores that constraint across a
native-feeling mobile client and a focused backend API.

## Engineering highlights

- **Offline-friendly mobile workflow:** the Expo client uses local SQLite storage
  for durable device state and sync-oriented workflows.
- **Focused API boundary:** the FastAPI service exposes planning, routine, memo,
  goal, dashboard, insight, and synchronization capabilities behind token-based
  access control.
- **Background work with observability:** asynchronous services handle durable
  work while request logging stays metadata-oriented.
- **Product-oriented architecture:** the implementation separates mobile UI,
  API routes, persistence, and domain services instead of collapsing concerns
  into a single application layer.

## Architecture

```text
Expo / React Native client
        │
        ├── local SQLite state and mobile notifications
        │
        └── authenticated sync
                 │
                 ▼
          FastAPI service
                 │
                 ├── planning, routines, goals, and insights
                 ├── memo and background-work workflows
                 └── PostgreSQL-backed services
```

## Repository guide

| Path | Purpose |
| --- | --- |
| `mobile/` | Expo and React Native client, local state, and mobile UX |
| `tools/api/` | FastAPI service, routers, domain services, and API tests |
| `databases/` | Database-related development and deployment resources |

## Technology stack

- **Mobile:** Expo, React Native, TypeScript, SQLite, local notifications
- **API:** Python, FastAPI, SQLAlchemy, async PostgreSQL access
- **Integration:** authenticated synchronization, background processing, and metadata-oriented request observability

## Privacy and scope

This repository demonstrates the application architecture and its engineering
contracts. It intentionally excludes credentials, runtime records, and personal
planning content.
