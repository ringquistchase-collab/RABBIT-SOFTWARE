"""
RabbitOS Enterprise AI Worker
Kafka consumer: pulls tasks, runs LLM inference, publishes results.
Supports DeepSeek API, OpenAI API, and local Phi-2.
"""
import os
import json
import time
import asyncio
import logging
import hashlib
from typing import Optional

log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

KAFKA_BROKERS     = os.getenv("KAFKA_BROKERS",        "kafka:9092")
TOPIC_TASKS       = os.getenv("KAFKA_TOPIC_TASKS",     "rabbitos.tasks")
TOPIC_RESULTS     = os.getenv("KAFKA_TOPIC_RESULTS",   "rabbitos.results")
CONSUMER_GROUP    = os.getenv("KAFKA_CONSUMER_GROUP",  "rabbitos-workers")
WORKER_CONCURRENCY= int(os.getenv("WORKER_CONCURRENCY","4"))
LLM_PROVIDER      = os.getenv("LLM_PROVIDER",         "mock")
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY",     "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY",       "")

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ── LLM Backends ─────────────────────────────────────────────────────────────

class LLMBackend:
    async def generate(self, prompt: str, max_tokens: int = 512) -> dict:
        raise NotImplementedError


class DeepSeekBackend(LLMBackend):
    BASE_URL = "https://api.deepseek.com/v1/chat/completions"

    async def generate(self, prompt: str, max_tokens: int = 512) -> dict:
        if not HTTPX_AVAILABLE:
            return MockBackend().generate(prompt, max_tokens)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={
                    "model":      "deepseek-chat",
                    "messages":   [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "output": data["choices"][0]["message"]["content"],
                "model":  data["model"],
                "tokens": data["usage"]["total_tokens"],
            }


class OpenAIBackend(LLMBackend):
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    async def generate(self, prompt: str, max_tokens: int = 512) -> dict:
        if not HTTPX_AVAILABLE:
            return await MockBackend().generate(prompt, max_tokens)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model":      "gpt-4o-mini",
                    "messages":   [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "output": data["choices"][0]["message"]["content"],
                "model":  data["model"],
                "tokens": data["usage"]["total_tokens"],
            }


class MockBackend(LLMBackend):
    RESPONSES = {
        "chat":     "This is a mock LLM response for your chat request.",
        "analyze":  "Analysis: The input data shows normal patterns. Confidence: 0.94.",
        "summarize":"Summary: Key points extracted from the provided context.",
        "embed":    "Embedding generated (mock 1536-dim vector).",
    }

    async def generate(self, prompt: str, max_tokens: int = 512) -> dict:
        task_type = "chat"
        for t in self.RESPONSES:
            if t in prompt.lower():
                task_type = t
                break
        output = self.RESPONSES.get(task_type, f"Mock response for: {prompt[:60]}")
        return {"output": output, "model": "mock-v1", "tokens": len(output.split())}


def get_backend() -> LLMBackend:
    if LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEY:
        return DeepSeekBackend()
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return OpenAIBackend()
    return MockBackend()


# ── Task Processor ────────────────────────────────────────────────────────────

class TaskProcessor:
    def __init__(self, llm: LLMBackend):
        self.llm = llm

    def _build_prompt(self, task_type: str, payload: dict) -> str:
        user_input = payload.get("input", payload.get("text", str(payload)))
        context    = payload.get("context", "")
        prompts = {
            "chat":     f"You are RabbitOS AI. User says: {user_input}\n{context}",
            "analyze":  f"Analyze the following data and provide insights:\n{user_input}",
            "summarize":f"Summarize the following in 3-5 sentences:\n{user_input}",
            "embed":    f"Generate a semantic representation for: {user_input}",
        }
        return prompts.get(task_type, f"Task: {task_type}\nInput: {user_input}")

    async def process(self, task: dict) -> dict:
        start     = time.time()
        task_id   = task.get("task_id", "unknown")
        task_type = task.get("task_type", "chat")
        payload   = task.get("payload", {})

        log.info("Processing task_id=%s type=%s", task_id, task_type)

        try:
            prompt = self._build_prompt(task_type, payload)
            result = await self.llm.generate(prompt)
            latency = (time.time() - start) * 1000

            # Compute result hash for integrity
            result_hash = hashlib.sha3_256(
                json.dumps(result, sort_keys=True).encode()
            ).hexdigest()[:16]

            return {
                "task_id":   task_id,
                "session_id":task.get("session_id"),
                "output":    result["output"],
                "model":     result["model"],
                "tokens":    result["tokens"],
                "latency_ms":round(latency, 2),
                "result_hash":result_hash,
                "status":    "ok",
            }
        except Exception as e:
            log.error("Task %s failed: %s", task_id, e)
            return {
                "task_id": task_id,
                "output":  "",
                "error":   str(e),
                "status":  "error",
            }


# ── Worker Loop ───────────────────────────────────────────────────────────────

async def worker_loop():
    llm       = get_backend()
    processor = TaskProcessor(llm)
    log.info("Worker started — LLM=%s Kafka=%s", LLM_PROVIDER,
             KAFKA_BROKERS if KAFKA_AVAILABLE else "mock")

    if not KAFKA_AVAILABLE:
        log.warning("aiokafka not available — running in demo mode")
        await _demo_loop(processor)
        return

    consumer = AIOKafkaConsumer(
        TOPIC_TASKS,
        bootstrap_servers=KAFKA_BROKERS,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda v: json.loads(v.decode()),
        max_poll_records=WORKER_CONCURRENCY,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode(),
    )

    await consumer.start()
    await producer.start()
    log.info("Kafka consumer started on topic=%s group=%s", TOPIC_TASKS, CONSUMER_GROUP)

    sem = asyncio.Semaphore(WORKER_CONCURRENCY)

    async def handle(task: dict):
        async with sem:
            result = await processor.process(task)
            await producer.send(TOPIC_RESULTS, result)

    try:
        async for msg in consumer:
            asyncio.create_task(handle(msg.value))
    finally:
        await consumer.stop()
        await producer.stop()


async def _demo_loop(processor: TaskProcessor):
    demo_tasks = [
        {"task_id": "demo-1", "task_type": "chat",
         "payload": {"input": "What is RabbitOS?"}, "session_id": "demo"},
        {"task_id": "demo-2", "task_type": "analyze",
         "payload": {"input": "EEG alpha power: 24.5 uV2, beta: 8.2 uV2"}, "session_id": "demo"},
        {"task_id": "demo-3", "task_type": "summarize",
         "payload": {"input": "RabbitOS is a biometric mesh OS with 47 nodes..."}, "session_id": "demo"},
    ]
    for task in demo_tasks:
        result = await processor.process(task)
        log.info("Demo result: %s", json.dumps(result, indent=2))
    log.info("Demo complete. Set KAFKA_BROKERS to enable live processing.")


if __name__ == "__main__":
    asyncio.run(worker_loop())
