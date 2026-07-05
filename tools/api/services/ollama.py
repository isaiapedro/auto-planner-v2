"""Ollama client for structured feature extraction and embedding generation."""
from __future__ import annotations

import json

import httpx

from config import settings
from schemas import MemoFeatures

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "mood":            {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "energy":          {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "topics":          {"type": "array", "items": {"type": "string"}},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["person", "project", "concept", "location"]},
                },
                "required": ["name", "type"],
            },
        },
        "sentiment":       {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "key_takeaways":   {"type": "array", "items": {"type": "string"}},
        "event_confirmed": {"type": "boolean"},
    },
    "required": ["mood", "energy", "topics", "entities", "sentiment", "key_takeaways"],
}

_EXTRACT_SYSTEM = (
    "You are a personal intelligence analyst. Given a transcript of an audio memo, "
    "extract the following structured metadata:\n"
    "- mood: float 0.0 (very negative) to 1.0 (very positive)\n"
    "- energy: float 0.0 (exhausted) to 1.0 (highly energized)\n"
    "- topics: list of main topics discussed\n"
    "- entities: people, projects, concepts, or locations mentioned\n"
    "- sentiment: overall sentiment\n"
    "- key_takeaways: 2-5 concise takeaways from the memo\n"
    "- event_confirmed: true if the user explicitly states they completed an event\n"
    "Return only the JSON object, no prose."
)


async def extract_features(transcript: str) -> MemoFeatures:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_extract_model,
                "messages": [
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user", "content": transcript},
                ],
                "stream": False,
                "format": _EXTRACT_SCHEMA,
            },
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        return MemoFeatures.model_validate_json(raw)


_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
        "schedule_recommendation": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["add", "move", "remove"]},
                            "block_id": {"type": ["string", "null"]},
                            "field": {"type": ["string", "null"]},
                            "old": {},
                            "new": {},
                            "title": {"type": ["string", "null"]},
                            "domain": {"type": ["string", "null"]},
                            "scheduled_at": {"type": ["string", "null"]},
                            "duration_minutes": {"type": ["integer", "null"]},
                        },
                        "required": ["action"],
                    },
                },
            },
            "required": ["reasoning", "blocks"],
        },
    },
    "required": ["narrative", "schedule_recommendation"],
}

_INSIGHT_SYSTEM = """You are a personal intelligence analyst generating periodic life reviews.

You receive structured data about a user's audio memos, mood/energy trends, active goals,
busy_windows (compact per-day busy ranges), and current schedule. Return JSON with a "narrative"
(2-4 paragraph reflective summary — observations, patterns, growth edges) and a
"schedule_recommendation" (reasoning + a list of block changes to add/move/remove).

Allocation is goal-driven, not weight-driven:
- "long_term" goals have a target_date — allocate time with urgency proportional to how close the
  deadline is and how little progress the memos/events show so far.
- "routine" goals have a cadence (e.g. "daily", "3x/week") — allocate recurring blocks that fit
  that cadence into open slots.
- Use busy_windows to find genuinely free time — never propose a block that overlaps a busy
  window. If calendar_error is set, note that live calendar data was unavailable and rely on the
  stored schedule/fixed_blocks instead.

Tone: analytical, calm, high-competence. No platitudes. Focus on empirical patterns.
If no schedule changes are warranted, return schedule_recommendation with an empty blocks array."""


async def generate_insight(context: dict) -> dict:
    """Generate a period narrative + schedule recommendation locally via Ollama."""
    async with httpx.AsyncClient(timeout=360) as client:
        resp = await client.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_planning_model,
                "messages": [
                    {"role": "system", "content": _INSIGHT_SYSTEM},
                    {"role": "user", "content": json.dumps(context)},
                ],
                "stream": False,
                "format": _INSIGHT_SCHEMA,
                "think": False,
            },
        )
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"])


_ASSIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot_id": {"type": "integer"},
                    "goal_title": {"type": "string"},
                },
                "required": ["slot_id", "goal_title"],
            },
        },
    },
    "required": ["reasoning", "assignments"],
}

_ASSIGN_SYSTEM = """You are filling a fixed weekly grid of pre-approved 2-hour time slots with goals.

You receive `slots`: a list of {id, weekday, start, duration_minutes} — these are the ONLY valid
times; they are already guaranteed free (no overlap with work, fixed commitments, or existing
calendar events). You do not invent times — you only pick, for each slot you choose to use, which
single goal (by exact title) occupies it. Not every slot needs to be filled.

You receive `goals`, each with a domain/theme, kind ("long_term" has a target_date, "routine" has
a cadence like "daily" or "3x/week"), so you can group related goals together.

Allocation rules:
- "routine" goals: assign a number of slots per week roughly matching their cadence (e.g. "daily"
  → most/all days if slots allow, "3x/week" → 3 slots spread across the week, not 3 in one day).
- "long_term" goals: assign 1-3 slots/week; the closer target_date is, the more slots and the
  higher priority over other goals when slots are scarce.
- Spread a goal's slots across different weekdays where possible rather than stacking them.
- Each slot_id may appear at most once across all assignments. Leave a slot out if no goal should
  fill it (don't force every slot to be used).

Return JSON with "reasoning" (1 short paragraph explaining the allocation) and "assignments"
(list of {slot_id, goal_title}). If there are no active goals or no slots, return an empty list."""


async def assign_goals_to_slots(context: dict) -> dict:
    """Deterministic-slots allocator — LLM only picks which goal fills which pre-vetted slot."""
    async with httpx.AsyncClient(timeout=450) as client:
        resp = await client.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_planning_model,
                "messages": [
                    {"role": "system", "content": _ASSIGN_SYSTEM},
                    {"role": "user", "content": json.dumps(context)},
                ],
                "stream": False,
                "format": _ASSIGN_SCHEMA,
                "think": False,
            },
        )
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"])


async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.ollama_host}/api/embed",
            json={"model": settings.ollama_embed_model, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]
