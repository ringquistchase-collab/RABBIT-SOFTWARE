"""
Telemetry collector — gathers runtime metrics and publishes to the event bus.
"""
import time
import asyncio
from typing import Any, Dict, List

from core.event_bus import bus
from core.logger import get_logger

log = get_logger("telemetry.collector")

_METRICS: List[Dict[str, Any]] = []


class MetricCollector:
    def __init__(self, interval_sec: float = 30.0):
        self.interval = interval_sec
        self._running = False

    def record(self, name: str, value: float, tags: Dict[str, str] = {}) -> None:
        entry = {"name": name, "value": value, "tags": tags, "ts": time.time()}
        _METRICS.append(entry)
        bus.publish("metric", entry)

    def get_metrics(self, name: str | None = None) -> List[Dict[str, Any]]:
        if name:
            return [m for m in _METRICS if m["name"] == name]
        return list(_METRICS)

    async def run_loop(self) -> None:
        self._running = True
        while self._running:
            self.record("collector.heartbeat", 1.0)
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        self._running = False


collector = MetricCollector()
