import uuid
from fastapi import APIRouter, HTTPException
from core.models import AnalyzeRequest, AnalyzeResponse
from ai.router import ai_router
from security.audit_log import log_event

router = APIRouter()


@router.post("/", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    task_id = req.event_id or str(uuid.uuid4())

    task = {
        "task_id":   task_id,
        "task_type": req.task_type,
        "content":   req.content,
        "context":   req.context,
    }

    try:
        result = await ai_router.route(task)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    log_event(task_id, "analyze", "system", {"task_type": req.task_type, "provider": result.get("provider")})

    return AnalyzeResponse(
        task_id  = task_id,
        provider = result.get("provider", "unknown"),
        result   = result.get("text", ""),
        tokens   = result.get("tokens", 0),
    )
