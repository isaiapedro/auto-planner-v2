from __future__ import annotations

import logging

from services.llm import planner_model
from services.llm.prompts import EVIDENCE_PLANNER_SYSTEM, REPAIR_PLANNER_SYSTEM
from services.planning.intention_parser import json_dumps
from services.planning.plan_narrative import enrich_recommendations
from services.planning.schemas import EvidenceRecommendations, InterpretedIntentions, PlanningRecommendation
from services.wiki.models import EvidencePackage

logger = logging.getLogger(__name__)

_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "intention_id": {"type": "string"},
                    "practice": {"type": "string"},
                    "frequency": {"type": "integer", "minimum": 1, "maximum": 14},
                    "duration_minutes": {"type": "integer", "minimum": 15, "maximum": 240},
                    "spacing": {"type": ["string", "null"]},
                    "preferred_time": {"type": ["string", "null"]},
                    "priority": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "title": {"type": ["string", "null"]},
                    "rationale": {"type": ["string", "null"]},
                    "routine_impact": {"type": ["string", "null"]},
                    "evidence_summary": {"type": ["string", "null"]},
                },
                "required": [
                    "intention_id",
                    "practice",
                    "frequency",
                    "duration_minutes",
                    "priority",
                    "evidence_ids",
                ],
            },
        }
    },
    "required": ["recommendations"],
}


async def build_recommendations(
    user_intention: str,
    interpreted: InterpretedIntentions,
    evidence: EvidencePackage,
) -> tuple[EvidenceRecommendations, str]:
    user_prompt = "\n\n".join(
        [
            "USER INTENTION",
            user_intention,
            "STRUCTURED INTENTIONS",
            json_dumps(interpreted.model_dump()),
            evidence.to_prompt_block(),
        ]
    )
    source = "llm"
    if not evidence.items:
        logger.info("Skipping evidence LLM call because wiki returned zero hits; using enriched fallback")
        source = "fallback"
        result = _fallback_recommendations(user_intention, interpreted, evidence)
    else:
        try:
            raw = await planner_model.generate_structured(
                EVIDENCE_PLANNER_SYSTEM,
                user_prompt,
                _RECOMMENDATION_SCHEMA,
            )
            result = EvidenceRecommendations.model_validate(raw)
            if not result.recommendations:
                logger.warning("Evidence planner returned zero recommendations; using enriched fallback")
                source = "fallback"
                result = _fallback_recommendations(user_intention, interpreted, evidence)
        except Exception as exc:
            logger.warning("Evidence planner failed (%s); using enriched fallback", exc)
            source = "fallback"
            result = _fallback_recommendations(user_intention, interpreted, evidence)

    known_ids = {item.evidence_id for item in evidence.items}
    cleaned: list[PlanningRecommendation] = []
    for recommendation in result.recommendations:
        recommendation.evidence_ids = [item for item in recommendation.evidence_ids if item in known_ids]
        cleaned.append(recommendation)
    enriched = enrich_recommendations(user_intention, interpreted, cleaned, evidence)
    return EvidenceRecommendations(recommendations=enriched), source


def _fallback_recommendations(
    user_intention: str,
    interpreted: InterpretedIntentions,
    evidence: EvidencePackage,
) -> EvidenceRecommendations:
    recommendations: list[PlanningRecommendation] = []
    for intention in interpreted.intentions:
        recommendations.append(
            PlanningRecommendation(
                intention_id=intention.id,
                practice=intention.id,
                frequency=min(intention.desired_frequency, 4),
                duration_minutes=intention.preferred_duration_minutes,
                spacing="separate_days",
                preferred_time="morning",
                priority=0.7 if intention.priority == "high" else 0.5,
                evidence_ids=[],
                title=intention.theme.strip().title(),
            )
        )
    enriched = enrich_recommendations(user_intention, interpreted, recommendations, evidence)
    return EvidenceRecommendations(recommendations=enriched)


async def revise_recommendations(
    user_intention: str,
    interpreted: InterpretedIntentions,
    evidence: EvidencePackage,
    recommendations: EvidenceRecommendations,
    violations: list[dict],
) -> EvidenceRecommendations:
    user_prompt = "\n\n".join(
        [
            "USER INTENTION",
            user_intention,
            "STRUCTURED INTENTIONS",
            json_dumps(interpreted.model_dump()),
            "CURRENT RECOMMENDATIONS",
            json_dumps(recommendations.model_dump()),
            "VALIDATION VIOLATIONS",
            json_dumps({"violations": violations}),
            evidence.to_prompt_block(),
        ]
    )
    raw = await planner_model.generate_structured(
        REPAIR_PLANNER_SYSTEM,
        user_prompt,
        _RECOMMENDATION_SCHEMA,
    )
    revised = EvidenceRecommendations.model_validate(raw)
    enriched = enrich_recommendations(user_intention, interpreted, revised.recommendations, evidence)
    return EvidenceRecommendations(recommendations=enriched)
