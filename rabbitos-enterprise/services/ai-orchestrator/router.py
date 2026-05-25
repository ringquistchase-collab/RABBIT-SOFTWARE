"""
RabbitOS Task Router
Routes tasks to Kafka workers and retrieves results.
Integrates with Qdrant (vector memory) and Neo4j (graph memory).
"""
import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

log = logging.getLogger("router")

KAFKA_BROKERS     = os.getenv("KAFKA_BROKERS",      "kafka:9092")
TOPIC_TASKS       = os.getenv("KAFKA_TOPIC_TASKS",   "rabbitos.tasks")
TOPIC_RESULTS     = os.getenv("KAFKA_TOPIC_RESULTS", "rabbitos.results")
QDRANT_URL        = os.getenv("QDRANT_URL",          "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION",   "rabbitos_memory")
NEO4J_URI         = os.getenv("NEO4J_URI",           "bolt://neo4j:7687")
RESULT_TIMEOUT    = int(os.getenv("RESULT_TIMEOUT",  "30"))

# Optional heavy imports
try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    log.warning("aiokafka not available — using mock routing")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

try:
    from neo4j import AsyncGraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


@dataclass
class Task:
    task_id:    str
    task_type:  str
    payload:    dict
    user_id:    str
    session_id: str
    created_at: float = field(default_factory=time.time)


@dataclass
class TaskResult:
    task_id:    str
    output:     str
    model:      str = "mock"
    tokens_used:int = 0
    latency_ms: float = 0.0
    error:      Optional[str] = None


class VectorMemory:
    def __init__(self):
        self._client = QdrantClient(url=QDRANT_URL) if QDRANT_AVAILABLE else None

    async def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        if not self._client:
            return []
        results = self._client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=limit,
        )
        return [{"id": str(r.id), "score": r.score, "payload": r.payload} for r in results]

    async def upsert(self, task_id: str, vector: list[float], payload: dict):
        if not self._client:
            return
        self._client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(id=task_id, vector=vector, payload=payload)],
        )


class GraphMemory:
    def __init__(self):
        self._driver = (
            AsyncGraphDatabase.driver(NEO4J_URI,
                auth=(os.getenv("NEO4J_USER", "neo4j"),
                      os.getenv("NEO4J_PASSWORD", "")))
            if NEO4J_AVAILABLE else None
        )

    async def link_session(self, user_id: str, session_id: str, task_id: str):
        if not self._driver:
            return
        async with self._driver.session() as s:
            await s.run(
                "MERGE (u:User {id: $uid}) "
                "MERGE (sess:Session {id: $sid}) "
                "MERGE (t:Task {id: $tid}) "
                "MERGE (u)-[:HAS_SESSION]->(sess) "
                "MERGE (sess)-[:CONTAINS]->(t)",
                uid=user_id, sid=session_id, tid=task_id,
            )

    async def close(self):
        if self._driver:
            await self._driver.close()


class TaskRouter:
    """Routes tasks to workers via Kafka; falls back to in-process mock."""

    def __init__(self):
        self._producer: Optional[object] = None
        self._results:  dict[str, asyncio.Future] = {}
        self._consumer_task: Optional[asyncio.Task] = None
        self.vector_mem = VectorMemory()
        self.graph_mem  = GraphMemory()

    async def start(self):
        if not KAFKA_AVAILABLE:
            log.info("Mock routing active (aiokafka not installed)")
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._producer.start()
        self._consumer_task = asyncio.create_task(self._consume_results())
        log.info("Kafka producer started: %s", KAFKA_BROKERS)

    async def stop(self):
        if self._producer:
            await self._producer.stop()
        if self._consumer_task:
            self._consumer_task.cancel()
        await self.graph_mem.close()

    async def route(self, task: Task) -> TaskResult:
        start = time.time()
        await self.graph_mem.link_session(task.user_id, task.session_id, task.task_id)

        if not KAFKA_AVAILABLE or not self._producer:
            return self._mock_result(task, time.time() - start)

        loop   = asyncio.get_event_loop()
        future = loop.create_future()
        self._results[task.task_id] = future

        await self._producer.send(TOPIC_TASKS, {
            "task_id":   task.task_id,
            "task_type": task.task_type,
            "payload":   task.payload,
            "user_id":   task.user_id,
            "session_id":task.session_id,
        })

        try:
            result = await asyncio.wait_for(future, timeout=RESULT_TIMEOUT)
        except asyncio.TimeoutError:
            result = TaskResult(task_id=task.task_id, output="Timeout", error="timeout")
        finally:
            self._results.pop(task.task_id, None)

        result.latency_ms = (time.time() - start) * 1000
        return result

    async def stream(self, task: Task) -> AsyncGenerator[str, None]:
        result = await self.route(task)
        # Simulate streaming by yielding tokens
        for word in (result.output or "").split():
            yield word + " "
            await asyncio.sleep(0.02)

    async def _consume_results(self):
        consumer = AIOKafkaConsumer(
            TOPIC_RESULTS,
            bootstrap_servers=KAFKA_BROKERS,
            value_deserializer=lambda v: json.loads(v.decode()),
            group_id="orchestrator",
        )
        await consumer.start()
        try:
            async for msg in consumer:
                data    = msg.value
                task_id = data.get("task_id")
                future  = self._results.get(task_id)
                if future and not future.done():
                    future.set_result(TaskResult(
                        task_id    = task_id,
                        output     = data.get("output", ""),
                        model      = data.get("model", "unknown"),
                        tokens_used= data.get("tokens", 0),
                    ))
        finally:
            await consumer.stop()

    def _mock_result(self, task: Task, elapsed: float) -> TaskResult:
        responses = {
            "chat":     f"[mock] Response to: {str(task.payload)[:60]}",
            "analyze":  "[mock] Analysis complete. Confidence: 0.94.",
            "summarize":"[mock] Summary generated from input context.",
            "embed":    "[mock] Embedding vector generated.",
        }
        output = responses.get(task.task_type, f"[mock] Task '{task.task_type}' processed.")
        return TaskResult(
            task_id    = task.task_id,
            output     = output,
            model      = "mock-router",
            tokens_used= len(output.split()),
            latency_ms = elapsed * 1000,
        )
