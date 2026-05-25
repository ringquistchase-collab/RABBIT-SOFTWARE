"""
Telemetry processor — aggregates raw metrics into windowed statistics.
"""
from collections import defaultdict
from typing import Any, Dict, List

from telemetry.collector import collector


class MetricAggregator:
    def summary(self, window_sec: float = 300.0) -> Dict[str, Any]:
        import time
        cutoff = time.time() - window_sec
        recent = [m for m in collector.get_metrics() if m["ts"] >= cutoff]

        by_name: Dict[str, List[float]] = defaultdict(list)
        for m in recent:
            by_name[m["name"]].append(m["value"])

        result = {}
        for name, values in by_name.items():
            result[name] = {
                "count": len(values),
                "sum":   round(sum(values), 4),
                "min":   round(min(values), 4),
                "max":   round(max(values), 4),
                "avg":   round(sum(values) / len(values), 4),
            }
        return result


aggregator = MetricAggregator()
