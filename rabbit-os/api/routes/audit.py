from typing import List, Optional
from fastapi import APIRouter, Query
from security.audit_log import get_log

router = APIRouter()


@router.get("/", response_model=List[dict])
async def audit_log(
    limit: int = Query(100, ge=1, le=1000),
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
):
    entries = get_log()
    if event_type:
        entries = [e for e in entries if e.get("event_type") == event_type]
    if actor:
        entries = [e for e in entries if e.get("actor") == actor]
    return entries[-limit:]
