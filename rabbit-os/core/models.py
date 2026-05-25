from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IngestPayload(BaseModel):
    source:    str
    data:      Dict[str, Any]
    user_id:   Optional[str] = None
    session_id: Optional[str] = None
    tags:      List[str]     = Field(default_factory=list)


class IngestResponse(BaseModel):
    event_id:  str
    hash:      str
    queued:    bool
    timestamp: float = Field(default_factory=time.time)


class AnalyzeRequest(BaseModel):
    event_id:  Optional[str] = None
    task_type: str            = "analysis"
    content:   str
    context:   Dict[str, Any] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    task_id:  str
    provider: str
    result:   str
    tokens:   int = 0


class AuditEntry(BaseModel):
    event_id:   str
    event_type: str
    actor:      str
    detail:     Dict[str, Any] = Field(default_factory=dict)
    timestamp:  float          = Field(default_factory=time.time)


class AgentRequest(BaseModel):
    agent:   str
    command: str
    params:  Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent:  str
    output: Any
    ok:     bool  = True
    error:  str   = ""
