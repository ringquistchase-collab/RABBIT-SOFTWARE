"""
RabbitOS Enterprise AI Orchestrator
Receives tasks from gateway, manages sessions, routes to workers via Kafka.
"""
import os
import uuid
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from router import TaskRouter, Task, TaskResult

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("orchestrator")

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    app.state.router = TaskRouter()
    await app.state.router.start()
    log.info("Orchestrator started")
    yield
    await app.state.router.stop()

app = FastAPI(title="RabbitOS Orchestrator", version="1.0.0", lifespan=lifespan)

# ── Models ────────────────────────────────────────────────────────────────────
class TaskRequest(BaseModel):
    task_type:  str
    payload:    dict
    user_id:    str
    session_id: Optional[str] = None
    stream:     bool = False

class SessionResponse(BaseModel):
    session_id: str
    user_id:    str
    created_at: float
    tasks:      list

# ── In-memory session store (replace with Redis in prod) ─────────────────────
SESSIONS: dict[str, dict] = {}

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}

@app.post("/v1/task")
async def submit_task(req: TaskRequest):
    session_id = req.session_id or str(uuid.uuid4())
    task = Task(
        task_id    = str(uuid.uuid4()),
        task_type  = req.task_type,
        payload    = req.payload,
        user_id    = req.user_id,
        session_id = session_id,
    )

    # Record in session
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"user_id": req.user_id, "created_at": time.time(), "tasks": []}
    SESSIONS[session_id]["tasks"].append(task.task_id)

    # Route task
    result: TaskResult = await app.state.router.route(task)
    return {
        "task_id":    task.task_id,
        "session_id": session_id,
        "result":     result.output,
        "model":      result.model,
        "tokens":     result.tokens_used,
        "latency_ms": result.latency_ms,
    }

@app.post("/v1/task/stream")
async def stream_task(req: TaskRequest):
    session_id = req.session_id or str(uuid.uuid4())
    task = Task(
        task_id    = str(uuid.uuid4()),
        task_type  = req.task_type,
        payload    = req.payload,
        user_id    = req.user_id,
        session_id = session_id,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for chunk in app.state.router.stream(task):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/v1/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return SessionResponse(session_id=session_id, **session)

@app.delete("/v1/session/{session_id}")
async def delete_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"deleted": session_id}
