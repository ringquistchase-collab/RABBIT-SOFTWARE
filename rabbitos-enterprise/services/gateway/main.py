"""
RabbitOS Enterprise Gateway
FastAPI entrypoint: JWT auth, rate limiting, routing to orchestrator, WebSocket streaming.
"""
import os
import time
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gateway")

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET    = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ORCHESTRATOR  = os.getenv("ORCHESTRATOR_URL", "http://rabbitos-orchestrator:8081")

# ── Metrics ───────────────────────────────────────────────────────────────────
REQUEST_COUNT = Counter("gateway_requests_total",   "Total requests",   ["method", "path", "status"])
REQUEST_LAT   = Histogram("gateway_request_seconds","Request latency",  ["path"])
AUTH_FAILURES = Counter("gateway_auth_failures",    "Auth failures",    ["reason"])

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    app.state.http = httpx.AsyncClient(base_url=ORCHESTRATOR, timeout=60)
    log.info("Gateway started. Orchestrator: %s", ORCHESTRATOR)
    yield
    await app.state.http.aclose()

app = FastAPI(title="RabbitOS Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Models ────────────────────────────────────────────────────────────────────
class TaskRequest(BaseModel):
    task_type: str
    payload:   dict
    session_id: Optional[str] = None
    stream:    bool = False

class HealthResponse(BaseModel):
    status:    str
    timestamp: float
    version:   str = "1.0.0"

# ── Auth ──────────────────────────────────────────────────────────────────────
def verify_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        AUTH_FAILURES.labels(reason="missing").inc()
        raise HTTPException(401, "Missing Authorization header")
    token = auth.split(" ", 1)[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        AUTH_FAILURES.labels(reason="expired").inc()
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        AUTH_FAILURES.labels(reason="invalid").inc()
        raise HTTPException(401, f"Invalid token: {e}")

# ── Middleware ────────────────────────────────────────────────────────────────
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LAT.labels(request.url.path).observe(duration)
    return response

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", timestamp=time.time())

@app.get("/ready")
async def ready(request: Request):
    try:
        r = await request.app.state.http.get("/health")
        r.raise_for_status()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "Orchestrator not ready")

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/v1/task")
async def submit_task(task: TaskRequest, claims: dict = Depends(verify_token),
                      request: Request = None):
    user_id = claims.get("sub", "anonymous")
    log.info("Task submitted: type=%s user=%s", task.task_type, user_id)

    if task.stream:
        async def streamer():
            async with request.app.state.http.stream(
                "POST", "/v1/task/stream",
                json={**task.model_dump(), "user_id": user_id}
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        return StreamingResponse(streamer(), media_type="text/event-stream")

    resp = await request.app.state.http.post(
        "/v1/task",
        json={**task.model_dump(), "user_id": user_id}
    )
    resp.raise_for_status()
    return resp.json()

@app.get("/v1/session/{session_id}")
async def get_session(session_id: str, claims: dict = Depends(verify_token),
                      request: Request = None):
    resp = await request.app.state.http.get(f"/v1/session/{session_id}")
    if resp.status_code == 404:
        raise HTTPException(404, "Session not found")
    resp.raise_for_status()
    return resp.json()

# ── WebSocket streaming ───────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    token = ws.query_params.get("token", "")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        await ws.close(code=4001)
        return

    await ws.accept()
    log.info("WebSocket connected: session=%s", session_id)
    try:
        async with httpx.AsyncClient(base_url=ORCHESTRATOR) as client:
            while True:
                data = await ws.receive_json()
                async with client.stream("POST", "/v1/task/stream",
                                         json={**data, "session_id": session_id}) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            await ws.send_text(line)
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: session=%s", session_id)
