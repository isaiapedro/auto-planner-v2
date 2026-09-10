from __future__ import annotations

from pydantic import BaseModel, Field


class WikiChunk(BaseModel):
    chunk_id: str
    source: str
    domain: str
    category: str
    title: str
    text: str
    score: float = 0.0


class WikiDocument(BaseModel):
    source: str
    domain: str
    category: str
    title: str
    chunks: list[WikiChunk] = Field(default_factory=list)


class Evidence(BaseModel):
    evidence_id: str
    source: str
    domain: str
    category: str
    title: str
    text: str
    score: float = 0.0


class EvidencePackage(BaseModel):
    query: str
    items: list[Evidence] = Field(default_factory=list)

    def to_prompt_block(self) -> str:
        if not self.items:
            return "RELEVANT EVIDENCE\n\nNo matching evidence found in the local wiki."
        lines = ["RELEVANT EVIDENCE", ""]
        for idx, item in enumerate(self.items, start=1):
            lines.extend(
                [
                    f"[E{idx}]",
                    f"Evidence ID: {item.evidence_id}",
                    f"Source: {item.source}",
                    f"Domain: {item.domain}",
                    f"Category: {item.category}",
                    f"Title: {item.title}",
                    "Summary:",
                    item.text[:1200],
                    "",
                ]
            )
        return "\n".join(lines)
