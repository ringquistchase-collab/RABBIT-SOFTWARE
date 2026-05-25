"""
Vector memory — Qdrant interface for semantic search and episodic recall.
"""
import os
import hashlib
import logging
from typing import Optional

log = logging.getLogger("memory.vector")

QDRANT_URL        = os.getenv("QDRANT_URL",        "http://qdrant:6333")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY",    "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "rabbitos_memory")
VECTOR_DIM        = 1536   # OpenAI / DeepSeek embedding dimension

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        Filter, FieldCondition, MatchValue,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    log.warning("qdrant-client not installed — VectorMemory in mock mode")


class VectorMemory:
    """
    Manages semantic memory for RabbitOS sessions.
    Each memory point stores: user_id, session_id, content, metadata.
    """

    def __init__(self):
        if QDRANT_AVAILABLE:
            self._client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY or None,
            )
            self._ensure_collection()
        else:
            self._client = None
            self._mock_store: list[dict] = []

    def _ensure_collection(self):
        try:
            self._client.get_collection(QDRANT_COLLECTION)
        except Exception:
            self._client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            log.info("Created Qdrant collection: %s", QDRANT_COLLECTION)

    def _mock_id(self, content: str) -> str:
        return hashlib.sha3_256(content.encode()).hexdigest()[:8]

    def upsert(self, user_id: str, session_id: str,
               content: str, vector: list[float],
               metadata: Optional[dict] = None) -> str:
        point_id = self._mock_id(f"{session_id}:{content}")
        payload  = {
            "user_id":    user_id,
            "session_id": session_id,
            "content":    content,
            **(metadata or {}),
        }
        if self._client:
            self._client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
        else:
            self._mock_store.append({"id": point_id, "vector": vector, "payload": payload})
        log.debug("Upserted memory point %s for session %s", point_id, session_id)
        return point_id

    def search(self, query_vector: list[float], user_id: str,
               limit: int = 5) -> list[dict]:
        if self._client:
            results = self._client.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                ),
                limit=limit,
                with_payload=True,
            )
            return [{"id": str(r.id), "score": r.score, "content": r.payload.get("content"),
                     "session_id": r.payload.get("session_id")} for r in results]
        # Mock: return top-N by simple dot product
        import numpy as np
        q = np.array(query_vector)
        scored = []
        for p in self._mock_store:
            if p["payload"].get("user_id") != user_id:
                continue
            v     = np.array(p["vector"])
            score = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-9))
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": p["id"], "score": s, "content": p["payload"].get("content")}
                for s, p in scored[:limit]]

    def delete_session(self, session_id: str):
        if self._client:
            self._client.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
                ),
            )
        else:
            self._mock_store = [p for p in self._mock_store
                                if p["payload"].get("session_id") != session_id]

    def stats(self) -> dict:
        if self._client:
            info = self._client.get_collection(QDRANT_COLLECTION)
            return {"points": info.points_count, "backend": "qdrant", "url": QDRANT_URL}
        return {"points": len(self._mock_store), "backend": "mock"}
