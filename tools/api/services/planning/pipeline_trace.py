from __future__ import annotations

import time
from typing import Any

from services.planning.schemas import PipelineStageTrace


class PipelineTracer:
    def __init__(self, planning_model: str) -> None:
        self._planning_model = planning_model
        self._stages: list[PipelineStageTrace] = []

    def start(self) -> float:
        return time.perf_counter()

    def record(
        self,
        stage: str,
        source: str,
        started_at: float,
        *,
        model: str | None = None,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        notes: list[str] | None = None,
    ) -> None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        self._stages.append(
            PipelineStageTrace(
                stage=stage,
                source=source,
                model=model or self._planning_model,
                duration_ms=duration_ms,
                input_summary=input_summary or {},
                output_summary=output_summary or {},
                notes=notes or [],
            )
        )

    def to_list(self) -> list[PipelineStageTrace]:
        return list(self._stages)
