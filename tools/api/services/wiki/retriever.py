from __future__ import annotations

from services.wiki.indexer import load_chunks, tokenize
from services.wiki.models import Evidence, WikiChunk


def _score_chunk(chunk: WikiChunk, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    haystack = f"{chunk.title} {chunk.text} {chunk.source}".lower()
    chunk_tokens = tokenize(haystack)
    overlap = query_tokens & chunk_tokens
    if not overlap:
        return 0.0
    title_bonus = sum(2.0 for token in overlap if token in chunk.title.lower())
    return float(len(overlap)) + title_bonus


def retrieve(
    query: str,
    domains: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int = 8,
) -> list[Evidence]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    allowed_domains = {domain.lower() for domain in domains} if domains else None
    allowed_categories = {category.lower() for category in categories} if categories else None

    ranked: list[tuple[float, WikiChunk]] = []
    for chunk in load_chunks():
        if allowed_domains and chunk.domain.lower() not in allowed_domains:
            continue
        if allowed_categories and chunk.category.lower() not in allowed_categories:
            continue
        score = _score_chunk(chunk, query_tokens)
        if score <= 0:
            continue
        ranked.append((score, chunk))

    ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].chunk_id))
    results: list[Evidence] = []
    seen_ids: set[str] = set()
    for score, chunk in ranked:
        evidence_id = chunk.chunk_id.split("#", 1)[0]
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        results.append(
            Evidence(
                evidence_id=evidence_id,
                source=chunk.source,
                domain=chunk.domain,
                category=chunk.category,
                title=chunk.title,
                text=chunk.text,
                score=score,
            )
        )
        if len(results) >= limit:
            break
    return results
