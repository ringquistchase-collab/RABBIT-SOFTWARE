import os
import json
import uuid
import hmac
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field, HttpUrl

app = FastAPI(title="Federated LLM Corpus Coordinator")

DB_PATH = os.getenv("FEDERATION_DB", "federation.db")
COORDINATOR_API_KEY = os.getenv("COORDINATOR_API_KEY", "change-me")
SIGNING_SECRET = os.getenv("SIGNING_SECRET", "change-me-too").encode()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            auth_type TEXT NOT NULL DEFAULT 'bearer',
            auth_token TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS routed_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT NOT NULL,
            origin_node_id TEXT,
            query_text TEXT NOT NULL,
            policy_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS query_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            result_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


class NodeRegistration(BaseModel):
    node_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    base_url: HttpUrl
    auth_type: str = Field(default="bearer")
    auth_token: Optional[str] = None


class FederatedQuery(BaseModel):
    query_text: str = Field(..., min_length=1)
    origin_node_id: Optional[str] = None
    target_node_ids: Optional[List[str]] = None
    policy: Dict[str, Any] = Field(default_factory=dict)


def require_api_key(x_api_key: Optional[str]) -> None:
    if x_api_key != COORDINATOR_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def sign_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    sig = hmac.new(SIGNING_SECRET, digest.encode(), hashlib.sha256).hexdigest()
    return {"payload_hash": digest, "signature": sig}


def register_node_db(node: NodeRegistration) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO nodes (node_id, name, base_url, auth_type, auth_token, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            name=excluded.name,
            base_url=excluded.base_url,
            auth_type=excluded.auth_type,
            auth_token=excluded.auth_token,
            enabled=1
        """,
        (
            node.node_id,
            node.name,
            str(node.base_url).rstrip("/"),
            node.auth_type,
            node.auth_token,
            utcnow(),
        ),
    )
    conn.commit()
    conn.close()


def get_nodes(target_ids: Optional[List[str]] = None) -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()

    if target_ids:
        placeholders = ",".join(["?"] * len(target_ids))
        cur.execute(
            f"""
            SELECT node_id, name, base_url, auth_type, auth_token
            FROM nodes
            WHERE enabled = 1 AND node_id IN ({placeholders})
            """,
            target_ids,
        )
    else:
        cur.execute(
            """
            SELECT node_id, name, base_url, auth_type, auth_token
            FROM nodes
            WHERE enabled = 1
            """
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def save_query(query_id: str, query: FederatedQuery) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO routed_queries (query_id, origin_node_id, query_text, policy_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            query_id,
            query.origin_node_id,
            query.query_text,
            json.dumps(query.policy),
            utcnow(),
        ),
    )
    conn.commit()
    conn.close()


def save_result(query_id: str, node_id: str, result: Dict[str, Any], provenance: Dict[str, Any]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO query_results (query_id, node_id, result_json, provenance_json, received_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            query_id,
            node_id,
            json.dumps(result),
            json.dumps(provenance),
            utcnow(),
        ),
    )
    conn.commit()
    conn.close()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": utcnow()}


@app.post("/api/nodes/register")
def register_node(
    node: NodeRegistration,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, str]:
    require_api_key(x_api_key)
    register_node_db(node)
    return {"status": "registered", "node_id": node.node_id}


@app.get("/api/nodes")
def list_nodes(
    x_api_key: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    require_api_key(x_api_key)
    rows = get_nodes()
    return [
        {
            "node_id": row["node_id"],
            "name": row["name"],
            "base_url": row["base_url"],
            "auth_type": row["auth_type"],
        }
        for row in rows
    ]


@app.post("/api/query")
async def federated_query(
    query: FederatedQuery,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)

    query_id = str(uuid.uuid4())
    save_query(query_id, query)

    nodes = get_nodes(query.target_node_ids)
    if not nodes:
        raise HTTPException(status_code=404, detail="No enabled target nodes found.")

    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for node in nodes:
            headers = {}
            if node["auth_type"] == "bearer" and node["auth_token"]:
                headers["Authorization"] = f"Bearer {node['auth_token']}"

            endpoint = node["base_url"].rstrip("/") + "/corpus/search"

            try:
                response = await client.post(
                    endpoint,
                    json={"query": query.query_text, "policy": query.policy},
                    headers=headers,
                )
                response.raise_for_status()
                body = response.json()

                provenance = {
                    "query_id": query_id,
                    "node_id": node["node_id"],
                    "node_name": node["name"],
                    "endpoint": endpoint,
                    "policy_applied": query.policy,
                    "retrieved_at": utcnow(),
                }
                save_result(query_id, node["node_id"], body, provenance)

                signed = sign_payload(body)

                results.append(
                    {
                        "node_id": node["node_id"],
                        "status": "ok",
                        "result": body,
                        "provenance": provenance,
                        "signature": signed,
                    }
                )
            except Exception as exc:
                provenance = {
                    "query_id": query_id,
                    "node_id": node["node_id"],
                    "node_name": node["name"],
                    "endpoint": endpoint,
                    "error": str(exc),
                    "retrieved_at": utcnow(),
                }
                error_body = {"error": str(exc)}
                save_result(query_id, node["node_id"], error_body, provenance)

                results.append(
                    {
                        "node_id": node["node_id"],
                        "status": "error",
                        "error": str(exc),
                        "provenance": provenance,
                    }
                )

    aggregate = {"query_id": query_id, "results": results}
    aggregate_signature = sign_payload(aggregate)

    return {
        **aggregate,
        "aggregate_signature": aggregate_signature,
    }


@app.get("/api/query/{query_id}")
def get_query_results(
    query_id: str,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT node_id, result_json, provenance_json, received_at
        FROM query_results
        WHERE query_id = ?
        ORDER BY id ASC
        """,
        (query_id,),
    )
    rows = cur.fetchall()
    conn.close()

    results = [
        {
            "node_id": row["node_id"],
            "result": json.loads(row["result_json"]),
            "provenance": json.loads(row["provenance_json"]),
            "received_at": row["received_at"],
        }
        for row in rows
    ]

    signed = sign_payload({"query_id": query_id, "results": results})

    return {
        "query_id": query_id,
        "results": results,
        "signature": signed,
    }