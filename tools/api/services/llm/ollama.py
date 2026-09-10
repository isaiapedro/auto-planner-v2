from __future__ import annotations

import json
import logging

import httpx

from config import settings
from services.llm.provider import PlannerModel

logger = logging.getLogger(__name__)


class OllamaPlanner(PlannerModel):
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
    ) -> dict:
        async with httpx.AsyncClient(timeout=360) as client:
            try:
                resp = await client.post(
                    f"{settings.ollama_host}/api/chat",
                    json={
                        "model": settings.ollama_planning_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "format": schema,
                        "think": False,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Ollama request failed: %s", exc)
                raise RuntimeError(f"Ollama request failed: {exc}") from exc
            payload = resp.json()
            content = payload.get("message", {}).get("content")
            if not content:
                raise RuntimeError("Ollama returned empty message content")
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                logger.warning("Ollama returned non-JSON content: %s", content[:200])
                raise RuntimeError("Ollama returned non-JSON content") from exc
