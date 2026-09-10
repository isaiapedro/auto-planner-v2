from __future__ import annotations

from abc import ABC, abstractmethod


class PlannerModel(ABC):
    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
    ) -> dict:
        ...
