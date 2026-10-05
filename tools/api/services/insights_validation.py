"""Semantic validation for root-published Personal Insights artifacts.

This module deliberately has no publication or filesystem-write API.  Root-owned
publication workflows may use it to validate a candidate before an atomic
replacement, while the Planner uses the same gate before serving a saved file.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from schemas import CurrentInsightsResponse


class InsightSemanticValidationError(ValueError):
    """A structurally valid artifact violates the Personal review contract."""


def _workspace_root(insights_root: Path) -> Path:
    """Return the parent of ``personal/`` for a configured Insights mount."""
    resolved = insights_root.resolve()
    if resolved.name != "insights" or resolved.parent.name != "planner" or resolved.parent.parent.name != "personal":
        raise InsightSemanticValidationError("Insights root must be personal/planner/insights")
    return resolved.parent.parent.parent


def _logical_file(workspace_root: Path, logical_path: str, *, allowed_prefix: str) -> Path:
    """Resolve a repository-relative artifact without accepting traversal or links out of scope."""
    candidate = PurePosixPath(logical_path)
    if candidate.is_absolute() or ".." in candidate.parts or not logical_path.startswith(allowed_prefix):
        raise InsightSemanticValidationError(f"path must stay within {allowed_prefix}: {logical_path}")
    root = workspace_root.resolve()
    path = (root / candidate).resolve()
    try:
        path.relative_to((root / allowed_prefix.rstrip("/")).resolve())
    except ValueError as exc:
        raise InsightSemanticValidationError(f"path escapes allowed scope: {logical_path}") from exc
    if not path.is_file():
        raise InsightSemanticValidationError(f"cited source does not exist: {logical_path}")
    return path


def _parse_pillar_taxonomy(path: Path) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_topics: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) == {"-"}:
            continue
        if not line.startswith((" ", "\t", "-")):
            if current_name is not None:
                groups.append((current_name, current_topics))
            # The manifest's stable machine group key is household_tasks,
            # while the human-maintained taxonomy labels it "household tasks".
            current_name, current_topics = ("household_tasks" if stripped == "household tasks" else stripped), []
        elif stripped.startswith("-"):
            topic = stripped[1:].split(":", 1)[0].strip()
            if not topic:
                raise InsightSemanticValidationError("pillar taxonomy contains an empty topic")
            current_topics.append(topic)
    if current_name is not None:
        groups.append((current_name, current_topics))
    if not groups:
        raise InsightSemanticValidationError("pillar taxonomy is empty")
    return groups


def _registry_targets(path: Path) -> tuple[set[str], set[str], set[str]]:
    text = path.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\|\s*([A-Z]+-\d+)\s*\|", text, flags=re.MULTILINE))
    priorities = set(re.findall(r"^\|\s*([^|]+?)\s*\|\s*(?:Non-negotiable|Continuing)", text, flags=re.MULTILINE))
    if not ids or not priorities:
        raise InsightSemanticValidationError("goal registry has no readable IDs or governing priorities")

    # The Personal registry predates machine-readable priority keys.  These
    # aliases are derived solely from its three named governing priorities and
    # retain the stable keys already used by the 1.2 artifact contract.
    aliases = {
        "Balanced lifestyle": "balanced_lifestyle",
        "Complete undergraduate graduation": "undergraduate_graduation",
        "Prepare for a strong junior role": "junior_role_readiness",
    }
    keys = {aliases.get(priority, _slug(priority)) for priority in priorities}
    dated_goal_ids: set[str] = set()
    for match in re.finditer(r"^\|\s*([A-Z]+-\d+)\s*\|[^|]*\|[^|]*\|\s*([^|]+?)\s*\|", text, flags=re.MULTILINE):
        goal_id, timing = match.groups()
        normalized_timing = timing.lower()
        # A phrase such as "before master's applications; date not yet set"
        # identifies a dependency, not a dated milestone to be reviewed.
        if "date not yet set" not in normalized_timing and any(
            marker in normalized_timing for marker in ("by ", "before ", "beginning of", "monthly", "end of")
        ):
            dated_goal_ids.add(goal_id)
    return ids, keys, dated_goal_ids


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _evidence_paths(review: CurrentInsightsResponse) -> Iterable[str]:
    bundle = review.inference_bundle
    for finding in [*bundle.routine_review.worked, *bundle.routine_review.did_not_work,
                    *bundle.future_plan_review.progress_updates, *bundle.future_plan_review.new_additions]:
        yield from finding.evidence_paths
    for relationship in [*bundle.future_plan_review.conflicts, *bundle.future_plan_review.facilitators]:
        yield from relationship.evidence_paths
    for assessment in bundle.goal_review.assessments:
        yield from assessment.evidence_paths
        for finding in assessment.findings:
            yield from finding.evidence_paths
    for group in bundle.life_pillar_review.groups:
        for topic in group.topics:
            yield from topic.evidence_paths
            for finding in topic.findings:
                yield from finding.evidence_paths


def _recommendation_paths(review: CurrentInsightsResponse) -> Iterable[str]:
    bundle = review.inference_bundle
    for assessment in bundle.goal_review.assessments:
        for recommendation in assessment.recommendations:
            yield recommendation.source_path
    for group in bundle.life_pillar_review.groups:
        for topic in group.topics:
            for recommendation in topic.recommendations:
                yield recommendation.source_path


def validate_insight_candidate(payload: Any, insights_root: Path | str) -> CurrentInsightsResponse:
    """Return a fully validated candidate or raise without changing any artifact.

    ``source_files`` defines the review's Personal-evidence scope. Every
    evidence citation must name one of those existing files. Recommendations
    are objective references and must resolve under a curated Knowledge wiki.
    """
    try:
        review = CurrentInsightsResponse.model_validate(payload)
    except ValidationError as exc:
        raise InsightSemanticValidationError(str(exc)) from exc

    root = _workspace_root(Path(insights_root))
    scoped_sources = set(review.source_files)
    for source in scoped_sources:
        _logical_file(root, source, allowed_prefix="personal/planner/memos/")
    for evidence_path in _evidence_paths(review):
        if evidence_path not in scoped_sources:
            raise InsightSemanticValidationError(
                f"evidence path is outside this review's source_files scope: {evidence_path}"
            )
        _logical_file(root, evidence_path, allowed_prefix="personal/planner/memos/")
    for source_path in _recommendation_paths(review):
        _logical_file(root, source_path, allowed_prefix="knowledge/")
        if "/wiki/" not in source_path:
            raise InsightSemanticValidationError(
                f"recommendation source must be a curated knowledge wiki path: {source_path}"
            )

    expected_taxonomy = _parse_pillar_taxonomy(Path(insights_root) / "archive" / "pillars.txt")
    actual_taxonomy = [(group.name, [topic.name for topic in group.topics]) for group in review.inference_bundle.life_pillar_review.groups]
    if actual_taxonomy != expected_taxonomy:
        raise InsightSemanticValidationError("life_pillar_review must exactly match archive/pillars.txt")

    registry_path = Path(insights_root) / "archive" / "long_term_goals.md"
    goal_ids, priority_keys, dated_goal_ids = _registry_targets(registry_path)
    reviewed_ids: set[str] = set()
    reviewed_priority_keys: set[str] = set()
    for assessment in review.inference_bundle.goal_review.assessments:
        if assessment.id and assessment.id not in goal_ids:
            raise InsightSemanticValidationError(f"unknown goal ID: {assessment.id}")
        if assessment.priority_key and assessment.priority_key not in priority_keys:
            raise InsightSemanticValidationError(f"unknown governing priority key: {assessment.priority_key}")
        if assessment.id:
            reviewed_ids.add(assessment.id)
        if assessment.priority_key:
            reviewed_priority_keys.add(assessment.priority_key)

    for relationship_kind, relationships in (
        ("conflict", review.inference_bundle.future_plan_review.conflicts),
        ("facilitator", review.inference_bundle.future_plan_review.facilitators),
    ):
        for relationship in relationships:
            for target in relationship.targets:
                if target.id and target.id not in goal_ids:
                    raise InsightSemanticValidationError(
                        f"unknown {relationship_kind} target goal ID: {target.id}"
                    )
                if target.priority_key and target.priority_key not in priority_keys:
                    raise InsightSemanticValidationError(
                        f"unknown {relationship_kind} target governing priority key: {target.priority_key}"
                    )
    missing_priorities = priority_keys - reviewed_priority_keys
    missing_dated_goals = dated_goal_ids - reviewed_ids
    if missing_priorities:
        raise InsightSemanticValidationError(
            f"goal_review is missing governing priority coverage: {', '.join(sorted(missing_priorities))}"
        )
    if missing_dated_goals:
        raise InsightSemanticValidationError(
            f"goal_review is missing dated-milestone coverage: {', '.join(sorted(missing_dated_goals))}"
        )
    return review
