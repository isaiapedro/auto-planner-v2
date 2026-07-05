from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine
from routers import dashboard, events, goals, insights, memos, schedule, sync
from services import whisper as whisper_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load Whisper model — avoids cold-start on first upload
    whisper_service.get_model()

    # Review generation is automatic: POST /insights/{period}/generate, triggered
    # by an n8n cron (Friday noon weekly, 1st-of-month monthly).
    yield

    await engine.dispose()


app = FastAPI(
    title="PIOS API",
    description="Personal Intelligence Operating System — backend API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memos.router)
app.include_router(events.router)
app.include_router(schedule.router)
app.include_router(goals.router)
app.include_router(dashboard.router)
app.include_router(insights.router)
app.include_router(sync.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
