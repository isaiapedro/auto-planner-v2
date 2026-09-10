from __future__ import annotations

from pathlib import Path


def evidence_id_from_path(path: Path) -> str:
    stem = path.stem.lower().replace(" ", "-")
    return stem


def chunk_id_from_path(path: Path, section_index: int) -> str:
    return f"{evidence_id_from_path(path)}#s{section_index}"
