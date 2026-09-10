import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import calendar_auth

router = APIRouter(prefix="/calendar/auth", tags=["calendar-auth"])
logger = logging.getLogger(__name__)


class AuthStartResponse(BaseModel):
    auth_url: str
    state: str
    instructions: str = (
        "Open auth_url in a browser on this machine/network, approve access, "
        "then POST /calendar/auth/wait/{state} to finish and store the token."
    )


class AuthWaitResponse(BaseModel):
    connected: bool
    expiry: str
    scopes: list[str]


@router.post("/start", response_model=AuthStartResponse)
async def start_auth() -> AuthStartResponse:
    try:
        auth_url, state = await asyncio.to_thread(calendar_auth.build_auth_url)
    except Exception as exc:
        logger.exception("Could not start Google Calendar authorization")
        raise HTTPException(status_code=503, detail="Calendar authorization is temporarily unavailable") from exc
    return AuthStartResponse(auth_url=auth_url, state=state)


@router.post("/wait/{state}", response_model=AuthWaitResponse)
async def wait_auth(state: str) -> AuthWaitResponse:
    try:
        result = await calendar_auth.wait_for_token(state)
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Calendar authorization timed out. Please try again.") from exc
    except (ValueError, RuntimeError) as exc:
        logger.exception("Google Calendar authorization failed")
        raise HTTPException(status_code=400, detail="Calendar authorization could not be completed") from exc
    return AuthWaitResponse(connected=True, **result)
