"""
Routes tasks to the appropriate LLM provider based on task_type.

  code       -> deepseek
  analysis   -> llama (via Ollama) or mock
  chat       -> mistral (via Ollama) or mock
  research   -> openai or mock
  *          -> mock
"""
from __future__ import annotations
import os
from typing import Any, Dict

from ai.llm_clients import DeepSeekClient, OpenAIClient, OllamaClient, MockClient
from core.config import cfg


class AIRouter:
    def __init__(self):
        self._deepseek = DeepSeekClient()
        self._openai   = OpenAIClient()
        self._ollama   = OllamaClient()
        self._mock     = MockClient()

    async def route(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task.get("task_type", "chat")
        content   = task.get("content", task.get("payload", {}).get("input", ""))

        if task_type == "code":
            return await self._call(self._deepseek, content, "deepseek", task)
        elif task_type == "analysis":
            return await self._call(self._ollama, content, "llama3", task, model="llama3")
        elif task_type == "chat":
            return await self._call(self._ollama, content, "mistral", task, model="mistral")
        elif task_type == "research":
            return await self._call(self._openai, content, "gpt-4o-mini", task)
        else:
            return await self._call(self._mock, content, "mock", task)

    async def _call(self, client, content: str, provider: str, task: dict, **kwargs) -> Dict[str, Any]:
        try:
            return await client.complete(content, **kwargs)
        except Exception:
            result = await self._mock.complete(content)
            result["provider"] = f"mock(fallback:{provider})"
            return result


ai_router = AIRouter()
