from typing import Any, Dict

from agents.base import BaseAgent
from ai.router import ai_router
from ai.prompts import format_prompt, SECURITY_TEMPLATE
from security.hasher import hash_event
from security.audit_log import log_event


class SecurityAgent(BaseAgent):
    name = "security"
    description = "Event risk assessment, anomaly detection, and security auditing."

    async def run(self, command: str, params: Dict[str, Any]) -> Any:
        if command == "assess":
            event  = params.get("event", {})
            prompt = format_prompt(SECURITY_TEMPLATE, content=str(event))
            result = await ai_router.route({"task_type": "analysis", "content": prompt})
            log_event(hash_event(event)[:16], "security_assess", "security_agent", {"event_keys": list(event.keys())})
            return {"risk_assessment": result["text"], "event_hash": hash_event(event)[:16]}

        if command == "scan":
            events = params.get("events", [])
            results = []
            for ev in events:
                prompt = format_prompt(SECURITY_TEMPLATE, content=str(ev))
                r = await ai_router.route({"task_type": "analysis", "content": prompt})
                results.append({"hash": hash_event(ev)[:16], "assessment": r["text"]})
            return results

        if command == "hash":
            return {"hash": hash_event(params)}

        return {"error": f"Unknown command: {command}", "available": ["assess", "scan", "hash"]}
