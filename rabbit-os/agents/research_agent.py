from typing import Any, Dict

from agents.base import BaseAgent
from ai.router import ai_router
from ai.prompts import format_prompt, RESEARCH_TEMPLATE
from ai.embeddings import embed, cosine_similarity

_KNOWLEDGE_BASE: list = []


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Knowledge retrieval, similarity search, and research synthesis."

    async def run(self, command: str, params: Dict[str, Any]) -> Any:
        if command == "query":
            question = params.get("question", "")
            context  = params.get("context", {})
            relevant = self._retrieve(question, top_k=3)
            context_str = "\n".join(r["text"] for r in relevant) if relevant else "No stored context."
            prompt = format_prompt(
                RESEARCH_TEMPLATE,
                content=question,
                context=f"{context_str}\n{context}",
            )
            result = await ai_router.route({"task_type": "research", "content": prompt})
            return {"answer": result["text"], "sources": len(relevant)}

        if command == "store":
            text = params.get("text", "")
            if text:
                _KNOWLEDGE_BASE.append({"text": text, "embedding": embed(text)})
                return {"stored": True, "total": len(_KNOWLEDGE_BASE)}
            return {"stored": False}

        if command == "search":
            query  = params.get("query", "")
            top_k  = params.get("top_k", 5)
            return self._retrieve(query, top_k=top_k)

        return {"error": f"Unknown command: {command}", "available": ["query", "store", "search"]}

    def _retrieve(self, query: str, top_k: int = 5) -> list:
        if not _KNOWLEDGE_BASE:
            return []
        q_emb = embed(query)
        scored = [
            (cosine_similarity(q_emb, item["embedding"]), item)
            for item in _KNOWLEDGE_BASE
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"text": item["text"], "score": round(score, 4)} for score, item in scored[:top_k]]
