from typing import Any, Dict

from agents.base import BaseAgent
from ai.router import ai_router
from ai.prompts import format_prompt, CODE_REVIEW_TEMPLATE


class DevAgent(BaseAgent):
    name = "dev"
    description = "Code review, refactoring suggestions, and development assistance."

    async def run(self, command: str, params: Dict[str, Any]) -> Any:
        if command == "review":
            code = params.get("code", "")
            prompt = format_prompt(CODE_REVIEW_TEMPLATE, content=code)
            result = await ai_router.route({"task_type": "code", "content": prompt})
            return result["text"]

        if command == "explain":
            code    = params.get("code", "")
            context = params.get("context", {})
            result  = await ai_router.route({
                "task_type": "code",
                "content":   f"Explain this code:\n\n{code}",
                "context":   context,
            })
            return result["text"]

        if command == "generate":
            spec   = params.get("spec", "")
            result = await ai_router.route({
                "task_type": "code",
                "content":   f"Write code for: {spec}",
            })
            return result["text"]

        return {"error": f"Unknown command: {command}", "available": ["review", "explain", "generate"]}
