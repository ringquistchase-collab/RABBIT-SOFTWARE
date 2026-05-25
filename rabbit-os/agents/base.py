from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    async def run(self, command: str, params: Dict[str, Any]) -> Any:
        ...

    def __repr__(self) -> str:
        return f"<Agent:{self.name}>"
