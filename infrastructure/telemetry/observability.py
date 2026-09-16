"""Structured logging + Prometheus metrics (agent observability)."""
from __future__ import annotations

import structlog
from prometheus_client import Counter, Histogram

INVESTIGATIONS = Counter("rg_investigations_total", "investigations run", ["outcome"])
TOOL_CALLS = Counter("rg_tool_calls_total", "tool calls", ["tool"])
INVESTIGATION_SECONDS = Histogram("rg_investigation_seconds", "investigation latency")


def get_logger(name: str = "rg"):
    structlog.configure(
        processors=[structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory())
    return structlog.get_logger(name)
