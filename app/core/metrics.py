from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class MetricPoint:
    count: int = 0
    total_ms: float = 0.0

    def add(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_ms += float(elapsed_ms)

    @property
    def avg_ms(self) -> float:
        if self.count <= 0:
            return 0.0
        return self.total_ms / self.count


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[tuple[str, str, int], MetricPoint] = defaultdict(MetricPoint)
        self._started_at = time.time()

    def observe(self, *, method: str, path: str, status: int, elapsed_ms: float) -> None:
        key = (method.upper(), path, int(status))
        with self._lock:
            self._by_key[key].add(elapsed_ms)

    def snapshot(self, *, top_n: int = 200) -> dict:
        with self._lock:
            items = [
                {
                    "method": method,
                    "path": path,
                    "status": status,
                    "count": point.count,
                    "avg_ms": round(point.avg_ms, 2),
                    "total_ms": round(point.total_ms, 2),
                }
                for (method, path, status), point in self._by_key.items()
            ]

        items.sort(key=lambda v: (v["count"], v["total_ms"]), reverse=True)
        return {
            "started_at": self._started_at,
            "top": items[: max(1, min(int(top_n), 1000))],
            "total_keys": len(items),
        }

    def reset(self) -> None:
        with self._lock:
            self._by_key.clear()
            self._started_at = time.time()


request_metrics = RequestMetrics()
