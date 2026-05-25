"""
In-process event bus backed by a bounded deque.
"""
import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional


class EventBus:
    def __init__(self, maxlen: int = 10_000):
        self._queue: deque = deque(maxlen=maxlen)
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        event = {
            "type":      event_type,
            "payload":   payload,
            "timestamp": time.time(),
        }
        self._queue.append(event)
        for q in self._subscribers.get(event_type, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, event_type: str, maxsize: int = 256) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.setdefault(event_type, []).append(q)
        return q

    def consume(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        items = list(self._queue)
        return items[-limit:] if limit else items

    def drain(self) -> List[Dict[str, Any]]:
        items = list(self._queue)
        self._queue.clear()
        return items


bus = EventBus()
