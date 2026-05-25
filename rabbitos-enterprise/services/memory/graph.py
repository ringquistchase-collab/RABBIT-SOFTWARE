"""
Graph memory — Neo4j interface for knowledge graph and session relationships.
Stores: User → Session → Task → Entity relationships.
"""
import os
import logging
from typing import Optional

log = logging.getLogger("memory.graph")

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    log.warning("neo4j driver not installed — GraphMemory in mock mode")


class GraphMemory:
    """
    Knowledge graph for RabbitOS session context and entity relationships.
    """

    def __init__(self):
        if NEO4J_AVAILABLE:
            self._driver: AsyncDriver = AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        else:
            self._driver = None
            self._mock_graph: list[dict] = []

    async def close(self):
        if self._driver:
            await self._driver.close()

    async def link_task(self, user_id: str, session_id: str, task_id: str,
                        task_type: str, summary: str = ""):
        if not self._driver:
            self._mock_graph.append({
                "user_id": user_id, "session_id": session_id,
                "task_id": task_id, "task_type": task_type, "summary": summary,
            })
            return
        async with self._driver.session() as s:
            await s.run(
                """
                MERGE (u:User {id: $uid})
                MERGE (sess:Session {id: $sid})
                  ON CREATE SET sess.created_at = timestamp()
                MERGE (t:Task {id: $tid})
                  ON CREATE SET t.type = $ttype, t.summary = $summary, t.created_at = timestamp()
                MERGE (u)-[:HAS_SESSION]->(sess)
                MERGE (sess)-[:CONTAINS]->(t)
                """,
                uid=user_id, sid=session_id, tid=task_id,
                ttype=task_type, summary=summary,
            )

    async def get_session_history(self, session_id: str) -> list[dict]:
        if not self._driver:
            return [r for r in self._mock_graph if r.get("session_id") == session_id]
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (sess:Session {id: $sid})-[:CONTAINS]->(t:Task)
                RETURN t.id AS task_id, t.type AS task_type,
                       t.summary AS summary, t.created_at AS created_at
                ORDER BY t.created_at
                """,
                sid=session_id,
            )
            return [dict(record) async for record in result]

    async def get_user_entities(self, user_id: str) -> list[dict]:
        if not self._driver:
            return [r for r in self._mock_graph if r.get("user_id") == user_id]
        async with self._driver.session() as s:
            result = await s.run(
                """
                MATCH (u:User {id: $uid})-[:HAS_SESSION]->(sess)-[:CONTAINS]->(t)
                RETURN sess.id AS session_id, count(t) AS task_count,
                       collect(t.type) AS task_types
                ORDER BY sess.created_at DESC LIMIT 20
                """,
                uid=user_id,
            )
            return [dict(record) async for record in result]

    async def add_entity(self, session_id: str, entity_type: str,
                         entity_id: str, properties: Optional[dict] = None):
        if not self._driver:
            self._mock_graph.append({
                "session_id": session_id, "entity_type": entity_type,
                "entity_id": entity_id, **(properties or {}),
            })
            return
        props = properties or {}
        async with self._driver.session() as s:
            await s.run(
                f"""
                MERGE (e:{entity_type} {{id: $eid}})
                  ON CREATE SET e += $props
                MERGE (sess:Session {{id: $sid}})
                MERGE (sess)-[:REFERENCES]->(e)
                """,
                eid=entity_id, sid=session_id, props=props,
            )

    def stats(self) -> dict:
        if self._driver:
            return {"backend": "neo4j", "uri": NEO4J_URI}
        return {"backend": "mock", "nodes": len(self._mock_graph)}
