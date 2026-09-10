from __future__ import annotations

import logging
import re

from services.llm import planner_model
from services.llm.prompts import PLAN_SUMMARY_SYSTEM
from services.planning.intention_parser import json_dumps
from services.planning.schemas import (
    GeneratedSchedule,
    InterpretedIntentions,
    PlanningRecommendation,
    PipelineMeta,
)
from services.wiki.models import EvidencePackage

logger = logging.getLogger(__name__)

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_summary": {"type": "string"},
        "recommendation_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intention_id": {"type": "string"},
                    "rationale": {"type": "string"},
                    "routine_impact": {"type": "string"},
                    "evidence_summary": {"type": "string"},
                },
                "required": ["intention_id", "rationale", "routine_impact", "evidence_summary"],
            },
        },
    },
    "required": ["plan_summary", "recommendation_notes"],
}

_PRACTICE_LIBRARY: list[tuple[tuple[str, ...], str, str, str]] = [
    (
        ("interview", "software", "coding", "project", "engineer", "code"),
        "Deep work on software projects",
        "Protected focus blocks for implementation and problem-solving, when cognitive load is highest.",
        "Consistent deep-work sessions reduce context switching and support measurable project progress across the week.",
    ),
    (
        ("exercise", "workout", "run", "gym", "health"),
        "Exercise and recovery",
        "Short, repeatable movement sessions spaced across the week to support energy and sleep quality.",
        "Regular exercise tends to improve sustained attention and recovery between demanding cognitive blocks.",
    ),
    (
        ("read", "study", "research", "learn", "paper"),
        "Reading and study",
        "Dedicated reading blocks for material that compounds over time rather than urgent tasks.",
        "Spaced study sessions usually outperform cramming for retention and long-term skill growth.",
    ),
    (
        ("chess", "music", "sing", "creative", "write", "art"),
        "Creative practice",
        "Low-pressure practice time for skills you want to maintain without turning them into obligations.",
        "Maintaining creative hobbies in fixed windows helps protect them from being displaced by reactive work.",
    ),
    (
        ("evening", "rest", "free", "wind down", "recover"),
        "Protected evening recovery",
        "Lighter or empty evening windows to avoid over-scheduling the end of the day.",
        "Recovery buffers reduce next-day fatigue and make morning focus blocks easier to protect.",
    ),
]


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _match_practice(intention_id: str, theme: str) -> tuple[str, str, str]:
    haystack = f"{intention_id} {theme}".lower()
    best_score = 0
    best: tuple[str, str, str] | None = None
    for keywords, title, rationale, routine_impact in _PRACTICE_LIBRARY:
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > best_score:
            best_score = score
            best = (title, rationale, routine_impact)
    if best and best_score > 0:
        return best
    readable = theme.strip() or intention_id.replace("_", " ")
    return (
        readable.title(),
        f"Time blocked for {readable}, based on what you described wanting in your week.",
        f"Repeating this across separate days keeps progress visible without filling every open hour.",
    )


def _attach_evidence(
    recommendation: PlanningRecommendation,
    evidence: EvidencePackage,
    intention_tokens: set[str],
) -> None:
    matched = []
    for item in evidence.items:
        item_tokens = _tokenize(f"{item.title} {item.text} {item.evidence_id}")
        if intention_tokens & item_tokens:
            matched.append(item)
    if not matched and evidence.items:
        matched = evidence.items[:2]
    if not matched:
        recommendation.evidence_summary = (
            "No strong match in the local wiki for this practice; this recommendation is based on your stated intention and scheduling constraints."
        )
        return
    recommendation.evidence_ids = [item.evidence_id for item in matched[:3]]
    snippets = []
    for item in matched[:2]:
        snippet = item.text.strip().replace("\n", " ")[:220]
        snippets.append(f"{item.title}: {snippet}")
    recommendation.evidence_summary = " ".join(snippets)


def enrich_recommendations(
    user_intention: str,
    interpreted: InterpretedIntentions,
    recommendations: list[PlanningRecommendation],
    evidence: EvidencePackage,
) -> list[PlanningRecommendation]:
    intention_lookup = {item.id: item for item in interpreted.intentions}
    enriched: list[PlanningRecommendation] = []
    used_titles: set[str] = set()
    for recommendation in recommendations:
        intention = intention_lookup.get(recommendation.intention_id)
        theme = intention.theme if intention else recommendation.intention_id
        library_title, rationale, routine_impact = _match_practice(recommendation.intention_id, theme)
        if recommendation.title and recommendation.title.endswith("_practice"):
            display_title = library_title
        elif theme.strip():
            display_title = theme.strip().title()
        else:
            display_title = recommendation.title or library_title
        if display_title in used_titles and theme.strip():
            display_title = f"{theme.strip().title()} ({recommendation.intention_id.replace('_', ' ')})"
        used_titles.add(display_title)
        recommendation.title = display_title
        recommendation.rationale = recommendation.rationale or rationale
        recommendation.routine_impact = recommendation.routine_impact or routine_impact
        intention_tokens = _tokenize(f"{recommendation.intention_id} {theme} {user_intention}")
        if not recommendation.evidence_summary:
            _attach_evidence(recommendation, evidence, intention_tokens)
        enriched.append(recommendation)
    return enriched


def _template_plan_summary(
    user_intention: str,
    recommendations: list[PlanningRecommendation],
    generated: GeneratedSchedule,
    meta: PipelineMeta,
) -> str:
    exploration_count = len(generated.exploration_blocks)
    parts = [
        f"This draft translates your description into {exploration_count} exploration blocks across the week.",
        f"Intentions were interpreted via {meta.intention_source}; practices were chosen via {meta.recommendation_source}.",
    ]
    if meta.evidence_hits == 0:
        parts.append(
            "The local wiki did not return matching evidence for this query, so specialist citations are limited in this draft."
        )
    else:
        parts.append(f"The planner retrieved {meta.evidence_hits} wiki passages to inform practice choices.")
    if recommendations:
        focus = ", ".join(item.title or item.practice for item in recommendations[:4])
        parts.append(f"The main focus areas are: {focus}.")
    parts.append("Exact times were chosen from your sleep window, fixed commitments, and calendar availability — not by the language model.")
    return " ".join(parts)


async def build_plan_summary(
    user_intention: str,
    interpreted: InterpretedIntentions,
    recommendations: list[PlanningRecommendation],
    generated: GeneratedSchedule,
    evidence: EvidencePackage,
    meta: PipelineMeta,
) -> tuple[str, list[PlanningRecommendation]]:
    if not recommendations:
        return _template_plan_summary(user_intention, recommendations, generated, meta), recommendations

    if meta.recommendation_source != "llm" or meta.intention_source != "llm":
        return _template_plan_summary(user_intention, recommendations, generated, meta), recommendations

    prompt = "\n\n".join(
        [
            "USER INTENTION",
            user_intention,
            "STRUCTURED INTENTIONS",
            json_dumps(interpreted.model_dump()),
            "RECOMMENDATIONS",
            json_dumps({"recommendations": [item.model_dump() for item in recommendations]}),
            "SCHEDULE OVERVIEW",
            json_dumps(
                {
                    "exploration_blocks": len(generated.exploration_blocks),
                    "fixed_blocks": len(generated.fixed_blocks),
                }
            ),
            evidence.to_prompt_block(),
        ]
    )
    try:
        raw = await planner_model.generate_structured(PLAN_SUMMARY_SYSTEM, prompt, _SUMMARY_SCHEMA)
        plan_summary = str(raw.get("plan_summary", "")).strip()
        notes = raw.get("recommendation_notes") or []
        notes_by_id = {str(item.get("intention_id")): item for item in notes if item.get("intention_id")}
        for recommendation in recommendations:
            note = notes_by_id.get(recommendation.intention_id)
            if not note:
                continue
            recommendation.rationale = str(note.get("rationale") or recommendation.rationale or "").strip() or recommendation.rationale
            recommendation.routine_impact = str(note.get("routine_impact") or recommendation.routine_impact or "").strip() or recommendation.routine_impact
            recommendation.evidence_summary = str(note.get("evidence_summary") or recommendation.evidence_summary or "").strip() or recommendation.evidence_summary
        if plan_summary:
            return plan_summary, recommendations
    except Exception as exc:
        logger.warning("Plan summary generation failed (%s); using template summary", exc)
    return _template_plan_summary(user_intention, recommendations, generated, meta), recommendations
