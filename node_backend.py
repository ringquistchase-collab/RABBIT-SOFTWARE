import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Federated LLM Corpus Node")

NODE_API_KEY = os.getenv("NODE_API_KEY", "node-secret")
NODE_ID = os.getenv("NODE_ID", "node-1")
NODE_NAME = os.getenv("NODE_NAME", "Example Node")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    policy: Dict[str, Any] = Field(default_factory=dict)


DOCUMENTS = [
    {
        "doc_id": "doc-001",
        "title": "Network diagnostics policy",
        "content": "Only approved endpoints may be measured and queried.",
        "tags": ["network", "policy", "security"],
    },
    {
        "doc_id": "doc-002",
        "title": "Tower metadata handling",
        "content": "Use OS-exposed identifiers and lawful lookup providers for enrichment.",
        "tags": ["tower", "metadata", "telemetry"],
    },
    {
        "doc_id": "doc-003",
        "title": "Federated corpus routing",
        "content": "Approved nodes may exchange summaries and corpus hits with provenance.",
        "tags": ["federation", "llm", "provenance"],
    },
]


def require_node_api_key(authorization: Optional[str]) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    expected = f"Bearer {NODE_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "node_id": NODE_ID, "time": utcnow()}


@app.get("/capabilities")
def capabilities() -> Dict[str, Any]:
    return {
        "node_id": NODE_ID,
        "node_name": NODE_NAME,
        "capabilities": [
            {
                "name": "corpus.search",
                "description": "Search local approved document corpus",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "policy": {"type": "object"},
                    },
                    "required": ["query"],
                },
            }
        ],
    }


@app.post("/corpus/search")
def corpus_search(
    request: SearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_node_api_key(authorization)

    q = request.query.lower().strip()
    matches: List[Dict[str, Any]] = []

    for doc in DOCUMENTS:
        haystack = " ".join(
            [
                doc["title"],
                doc["content"],
                " ".join(doc["tags"]),
            ]
        ).lower()

        if q in haystack:
            matches.append(
                {
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "summary": doc["content"][:180],
                    "tags": doc["tags"],
                    "score": 0.9,
                }
            )

    return {
        "node_id": NODE_ID,
        "node_name": NODE_NAME,
        "query": request.query,
        "policy_echo": request.policy,
        "matches": matches,
        "retrieved_at": utcnow(),
    }