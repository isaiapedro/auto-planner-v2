"""Obsidian vault writer — produces append-only .md memos in master_wiki/memos/."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import aiofiles

from config import settings
from schemas import MemoFeatures

_ALLOWED_DIR = "memos"


async def write_memo(obs_id: str, event_title: str | None, transcript: str, features: MemoFeatures) -> str:
    vault = Path(settings.master_wiki_path)
    memos_dir = vault / _ALLOWED_DIR
    memos_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date.today().isoformat()}-{obs_id[:8]}.md"
    dest = memos_dir / filename

    # Boundary enforcement — never write outside master_wiki/memos/
    if not str(dest.resolve()).startswith(str(memos_dir.resolve())):
        raise ValueError(f"Security violation: {dest} outside allowed dir")

    if dest.exists():
        return str(dest)  # append-only: skip if already written

    topics_yaml = "[" + ", ".join(features.topics) + "]"
    entities_rows = "\n".join(f"| {e.name} | {e.type} |" for e in features.entities)

    content = f"""---
date: {date.today().isoformat()}
obs_id: {obs_id}
event: "{event_title or ''}"
mood: {features.mood:.2f}
energy: {features.energy:.2f}
topics: {topics_yaml}
sentiment: {features.sentiment.value}
---

## Transcript ^[extracted]

{transcript}

## Key Takeaways ^[inferred]

{chr(10).join(f"- {t}" for t in features.key_takeaways)}

## Entities ^[inferred]

| Name | Type |
|------|------|
{entities_rows}
"""

    async with aiofiles.open(dest, "w", encoding="utf-8") as f:
        await f.write(content)

    return str(dest)
