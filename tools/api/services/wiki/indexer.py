from __future__ import annotations

import re
from pathlib import Path

from config import settings
from services.wiki.citations import chunk_id_from_path, evidence_id_from_path
from services.wiki.models import WikiChunk

SKIP_NAMES = {
    "AGENTS.md",
    "BEHAVIOR.md",
    "SYSTEM.md",
    "SKILLS.md",
    "manifest.yaml",
    "REVIEW.md",
    "TASKS.md",
    "ONTOLOGY.md",
    "KNOWLEDGE.md",
    "PRIVACY.md",
    "INDEX.md",
    "DECISIONS.md",
    "CHANGELOG.md",
    "DEPENDENCIES.md",
    "ARCHITECTURE.md",
    "API.md",
}


def _resolve_root() -> Path:
    return Path(settings.knowledge_root_path).resolve()


def _is_allowed(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    if path.name in SKIP_NAMES:
        return False
    if path.suffix.lower() != ".md":
        return False
    return True


def _infer_domain(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = rel.parts
    return parts[0] if parts else "general"


def _infer_category(path: Path) -> str:
    lowered = {part.lower() for part in path.parts}
    for candidate in ("wiki", "papers", "concepts", "standards", "datasets", "organizations", "raw"):
        if candidate in lowered:
            return candidate
    return "general"


def _title_from_content(path: Path, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.stem.replace("-", " ").replace("_", " ")


def _split_sections(content: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.startswith("#") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    if not sections:
        return [content.strip()] if content.strip() else []
    return [section for section in sections if section]


def load_chunks(root: Path | None = None) -> list[WikiChunk]:
    base = root or _resolve_root()
    if not base.exists():
        return []

    chunks: list[WikiChunk] = []
    for path in base.rglob("*.md"):
        if not _is_allowed(path, base):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not content.strip():
            continue

        domain = _infer_domain(path, base)
        category = _infer_category(path)
        title = _title_from_content(path, content)
        rel_source = str(path.relative_to(base))
        evidence_id = evidence_id_from_path(path)

        for index, section in enumerate(_split_sections(content)):
            chunks.append(
                WikiChunk(
                    chunk_id=chunk_id_from_path(path, index),
                    source=rel_source,
                    domain=domain,
                    category=category,
                    title=title,
                    text=section,
                )
            )
            if index == 0:
                chunks[-1].chunk_id = evidence_id
    return chunks


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}
