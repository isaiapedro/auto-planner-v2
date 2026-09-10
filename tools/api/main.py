import logging
import asyncio
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import engine, ensure_insight_audit_schema, ensure_memo_jobs_schema, ensure_routine_occurrence_schema
from routers import account, account_catalog, calendar_auth, dashboard, events, goals, insights, memos, planning, routine, sync
from services.pipeline import run_memo_worker
from services.observability import configure_logging, log_event, request_id

configure_logging()
logger = logging.getLogger(__name__)


def _route_category(path: str) -> str:
    """Return an allow-listed route family; never log user-controlled path text."""
    if path == "/health":
        return "/health"
    family = path.lstrip("/").split("/", 1)[0]
    return f"/{family}" if family in {"account", "memos", "events", "routine", "planning", "goals", "dashboard", "insights", "sync", "calendar-auth"} else "/unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail startup loudly if the durable Personal memo queue cannot be created.
    await ensure_memo_jobs_schema()
    await ensure_insight_audit_schema()
    await ensure_routine_occurrence_schema()
    worker = asyncio.create_task(run_memo_worker(), name="memo-transcription-worker")
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        await engine.dispose()


app = FastAPI(
    title="PIOS API",
    description="Personal Intelligence Operating System — backend API",
    version="0.1.0",
    lifespan=lifespan,
)

_allowed_origins = [origin.strip() for origin in settings.api_allowed_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Protect LAN access and emit metadata-only request completion events."""
    incoming_id = request.headers.get("x-request-id", "")
    try:
        correlation_id = str(uuid.UUID(incoming_id))
    except ValueError:
        correlation_id = str(uuid.uuid4())
    token = request_id.set(correlation_id)
    started = time.perf_counter()
    response = None
    try:
        if request.method != "OPTIONS" and request.url.path != "/health":
            authorization = request.headers.get("authorization", "")
            scheme, _, access_token = authorization.partition(" ")
            expected = settings.pios_api_token.get_secret_value()
            if scheme.lower() != "bearer" or not secrets.compare_digest(access_token, expected):
                response = JSONResponse(status_code=401, content={"detail": "Unauthorized"})
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id
        return response
    finally:
        log_event(
            logger,
            "api_request_completed",
            method=request.method,
            route=_route_category(request.url.path),
            status_code=response.status_code if response else 500,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        request_id.reset(token)

app.include_router(memos.router)
app.include_router(account.router)
app.include_router(account_catalog.router)
app.include_router(events.router)
app.include_router(routine.router)
app.include_router(planning.router)
app.include_router(goals.router)
app.include_router(dashboard.router)
app.include_router(insights.router)
app.include_router(sync.router)
app.include_router(calendar_auth.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
