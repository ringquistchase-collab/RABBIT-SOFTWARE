from __future__ import annotations
import hashlib
from typing import Any, Dict

from core.config import cfg
from core.logger import get_logger

log = get_logger("llm_clients")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class _BaseClient:
    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class DeepSeekClient(_BaseClient):
    _URL = "https://api.deepseek.com/v1/chat/completions"
    _MODEL = "deepseek-chat"

    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        if not cfg.DEEPSEEK_API_KEY or not HTTPX_AVAILABLE:
            return await MockClient().complete(prompt)
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                self._URL,
                headers={"Authorization": f"Bearer {cfg.DEEPSEEK_API_KEY}"},
                json={"model": self._MODEL, "messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            data = r.json()
        return {
            "provider": "deepseek",
            "text":     data["choices"][0]["message"]["content"],
            "tokens":   data.get("usage", {}).get("total_tokens", 0),
        }


class OpenAIClient(_BaseClient):
    _URL = "https://api.openai.com/v1/chat/completions"

    async def complete(self, prompt: str, model: str = "gpt-4o-mini", **kwargs) -> Dict[str, Any]:
        if not cfg.OPENAI_API_KEY or not HTTPX_AVAILABLE:
            return await MockClient().complete(prompt)
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                self._URL,
                headers={"Authorization": f"Bearer {cfg.OPENAI_API_KEY}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            data = r.json()
        return {
            "provider": "openai",
            "text":     data["choices"][0]["message"]["content"],
            "tokens":   data.get("usage", {}).get("total_tokens", 0),
        }


class OllamaClient(_BaseClient):
    async def complete(self, prompt: str, model: str = "mistral", **kwargs) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return await MockClient().complete(prompt)
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(
                    f"{cfg.OLLAMA_URL}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                r.raise_for_status()
                data = r.json()
            return {
                "provider": f"ollama/{model}",
                "text":     data.get("response", ""),
                "tokens":   data.get("eval_count", 0),
            }
        except Exception as exc:
            log.warning("Ollama unavailable (%s), falling back to mock", exc)
            return await MockClient().complete(prompt)


class MockClient(_BaseClient):
    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        return {
            "provider": "mock",
            "text":     f"[mock response for prompt hash {digest}]",
            "tokens":   len(prompt.split()),
        }
