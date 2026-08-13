# Copyright (c) 2026 Lumine. All rights reserved.
"""In-process metrics registry (B-02).

Prometheus text-format export so the stack can be scraped without adding
a dependency. Counters/gauges are process-local; a multi-instance fleet
would aggregate at scrape time (documented in COMPLETION-WORKFLOW W4).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import DefaultDict


class MetricsRegistry:
    """Thread-safe counters + gauges with Prometheus text exposition."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: DefaultDict[str, float] = defaultdict(float)
        self._gauges: DefaultDict[str, float] = defaultdict(float)

    def inc(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {**self._counters, **self._gauges}

    def render_prometheus(self) -> str:
        """Render counters (type counter) and gauges in text format 0.0.4."""
        lines: list[str] = []
        with self._lock:
            for name, value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value:g}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value:g}")
        return "\n".join(lines) + "\n"


# Process-wide default registry.
default_registry = MetricsRegistry()
