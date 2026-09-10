from __future__ import annotations

import asyncio
import logging
import re

from services.llm import planner_model
from services.llm.prompts import INTENTION_INTERPRETER_SYSTEM
from services.planning.schemas import InterpretedIntention, InterpretedIntentions, PlanningPreference

logger = logging.getLogger(__name__)

_INTENTION_SCHEMA = {
    "type": "object",
    "properties": {
        "intentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "theme": {"type": "string"},
                    "desired_frequency": {"type": "integer", "minimum": 1, "maximum": 14},
                    "preferred_duration_minutes": {"type": "integer", "minimum": 15, "maximum": 240},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["id", "theme", "desired_frequency", "preferred_duration_minutes", "priority"],
            },
        },
        "preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
            },
        },
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
            },
        },
        "desired_routines": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intentions", "preferences", "constraints", "desired_routines"],
}


async def interpret_intention(
    user_intention: str,
    personal_context: dict | None = None,
) -> tuple[InterpretedIntentions, str]:
    payload = {
        "user_intention": user_intention,
        "personal_context": personal_context or {},
    }
    try:
        raw = await asyncio.wait_for(
            planner_model.generate_structured(
                INTENTION_INTERPRETER_SYSTEM,
                json_dumps(payload),
                _INTENTION_SCHEMA,
            ),
            timeout=60,
        )
        parsed = InterpretedIntentions.model_validate(raw)
        if not parsed.intentions:
            logger.warning("Intention interpreter returned zero intentions; using phrase-based fallback")
            return _fallback_intention(user_intention), "fallback"
        return parsed, "llm"
    except asyncio.TimeoutError:
        logger.warning("Intention interpreter timed out; using phrase-based fallback")
        return _fallback_intention(user_intention), "fallback"
    except Exception as exc:
        logger.warning("Intention interpreter failed (%s); using phrase-based fallback", exc)
        return _fallback_intention(user_intention), "fallback"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:48] or "focus_area"


def _fallback_intention(user_intention: str) -> InterpretedIntentions:
    parts = re.split(r"[.\n;]+|(?:\band\b|\bthen\b)", user_intention.lower())
    clauses: list[str] = []
    for part in parts:
        for clause in part.split(","):
            cleaned = clause.strip()
            if cleaned and len(cleaned) > 6:
                clauses.append(cleaned)
    intentions: list[InterpretedIntention] = []
    seen_ids: set[str] = set()
    for clause in clauses[:5]:
        intention_id = _slugify(clause)
        if intention_id in seen_ids:
            continue
        seen_ids.add(intention_id)
        priority = "high" if any(word in clause for word in ("focus", "interview", "project", "important")) else "medium"
        duration = 90 if any(word in clause for word in ("deep", "project", "interview", "code")) else 60
        frequency = 3
        if "daily" in clause or "every day" in clause:
            frequency = 5
        intentions.append(
            InterpretedIntention(
                id=intention_id,
                theme=clause.strip().capitalize(),
                desired_frequency=frequency,
                preferred_duration_minutes=duration,
                priority=priority,
            )
        )
    if not intentions:
        intentions.append(
            InterpretedIntention(
                id="weekly_priorities",
                theme="Weekly priorities from your description",
                desired_frequency=3,
                preferred_duration_minutes=60,
                priority="medium",
            )
        )
    preferences: list[PlanningPreference] = []
    lowered = user_intention.lower()
    if "morning" in lowered:
        preferences.append(PlanningPreference(key="focus_time", value="morning"))
    if "evening" in lowered or "evenings" in lowered:
        preferences.append(PlanningPreference(key="protect_evenings", value="true"))
    return InterpretedIntentions(
        intentions=intentions,
        preferences=preferences,
        constraints=[],
        desired_routines=[],
    )


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
