import time
import uuid
from fastapi import APIRouter
from core.models import IngestPayload, IngestResponse
from core.event_bus import bus
from security.hasher import hash_event
from security.audit_log import log_event
from db.sqlite import insert_event

router = APIRouter()


@router.post("/", response_model=IngestResponse)
async def ingest(payload: IngestPayload):
    event_id = str(uuid.uuid4())
    event_hash = hash_event(payload.dict())

    record = {
        "event_id":   event_id,
        "source":     payload.source,
        "user_id":    payload.user_id or "anonymous",
        "session_id": payload.session_id or "",
        "hash":       event_hash,
        "data":       payload.data,
        "tags":       payload.tags,
        "timestamp":  time.time(),
    }

    insert_event(record)
    bus.publish("ingest", record)
    log_event(event_id, "ingest", payload.user_id or "anonymous", {"source": payload.source})

    return IngestResponse(event_id=event_id, hash=event_hash, queued=True)
