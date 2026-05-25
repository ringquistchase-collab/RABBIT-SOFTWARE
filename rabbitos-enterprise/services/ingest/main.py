"""
RabbitOS Enterprise Ingest Service
Bridges existing Supabase sensor/spectrum data into the enterprise Kafka pipeline.
"""
import os
import json
import time
import asyncio
import logging
import hashlib
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("ingest")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TOPIC_TASKS   = os.getenv("KAFKA_TOPIC_TASKS", "rabbitos.tasks")

try:
    from aiokafka import AIOKafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

app = FastAPI(title="RabbitOS Ingest Bridge", version="1.0.0")


class SensorEvent(BaseModel):
    sensor_id:   str
    user_id:     str
    value:       float
    unit:        str
    signal_type: Optional[str] = None
    metadata:    dict = {}

class SpectrumEvent(BaseModel):
    session_id:    Optional[str] = None
    user_id:       str
    frequency_mhz: float
    power_dbm:     float
    node_id:       Optional[int] = None
    peaks:         list = []

_producer: Optional[object] = None

@app.on_event("startup")
async def startup():
    global _producer
    if KAFKA_AVAILABLE:
        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await _producer.start()

@app.on_event("shutdown")
async def shutdown():
    if _producer:
        await _producer.stop()

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}

@app.post("/ingest/sensor")
async def ingest_sensor(event: SensorEvent):
    task = {
        "task_id":   hashlib.sha3_256(f"{event.sensor_id}:{time.time()}".encode()).hexdigest()[:16],
        "task_type": "analyze",
        "payload":   {
            "input":      f"Sensor {event.sensor_id}: {event.value} {event.unit}",
            "signal_type":event.signal_type,
            "metadata":   event.metadata,
        },
        "user_id":   event.user_id,
        "session_id":f"sensor-{event.sensor_id}",
        "source":    "supabase-sensor",
    }
    if _producer:
        await _producer.send(TOPIC_TASKS, task)
    return {"task_id": task["task_id"], "queued": True}

@app.post("/ingest/spectrum")
async def ingest_spectrum(event: SpectrumEvent):
    task = {
        "task_id":   hashlib.sha3_256(f"spec:{event.frequency_mhz}:{time.time()}".encode()).hexdigest()[:16],
        "task_type": "analyze",
        "payload":   {
            "input":       f"Spectrum @ {event.frequency_mhz} MHz, power {event.power_dbm} dBm",
            "peaks":       event.peaks,
            "node_id":     event.node_id,
        },
        "user_id":   event.user_id,
        "session_id":event.session_id or f"spectrum-{event.node_id}",
        "source":    "supabase-spectrum",
    }
    if _producer:
        await _producer.send(TOPIC_TASKS, task)
    return {"task_id": task["task_id"], "queued": True}
