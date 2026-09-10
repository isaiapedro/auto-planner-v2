from __future__ import annotations

from services.wiki.models import EvidencePackage
from services.wiki.retriever import retrieve


class WikiService:
    def search(
        self,
        query: str,
        domains: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 8,
    ) -> EvidencePackage:
        items = retrieve(query=query, domains=domains, categories=categories, limit=limit)
        return EvidencePackage(query=query, items=items)
