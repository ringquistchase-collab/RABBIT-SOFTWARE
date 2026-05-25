import time
from typing import Any, Dict, List

AUDIT_LOG: List[Dict[str, Any]] = []


def log_event(event_id: str, event_type: str, actor: str, detail: Dict[str, Any] = {}) -> None:
    AUDIT_LOG.append({
        "event_id":   event_id,
        "event_type": event_type,
        "actor":      actor,
        "detail":     detail,
        "timestamp":  time.time(),
    })


def get_log() -> List[Dict[str, Any]]:
    return list(AUDIT_LOG)


def clear_log() -> None:
    AUDIT_LOG.clear()
