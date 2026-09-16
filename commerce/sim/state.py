"""Shared in-memory sim-store state. Single-process MVP; Postgres later."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from domain.clock import SimulationClock


@dataclass
class Faults:
    shipping_latency_ms_add: float = 0.0
    db_latency_ms_add: float = 0.0
    payment_fail_rate_add: float = 0.0
    pricing_bug: bool = False
    telemetry_gap: bool = False  # when True, dependency metrics unavailable


@dataclass
class Deploy:
    deploy_id: str
    version: str
    sha: str
    component: str
    t_offset_s: float


@dataclass
class SimState:
    clock: SimulationClock = field(default_factory=SimulationClock)
    faults: Faults = field(default_factory=Faults)
    deploys: list[Deploy] = field(default_factory=list)
    checkout_p95_hist: deque = field(default_factory=lambda: deque(maxlen=60))
    conv_hist: deque = field(default_factory=lambda: deque(maxlen=60))
    ship_p95_hist: deque = field(default_factory=lambda: deque(maxlen=60))
    checkout_p95_now: float = 450.0
    conv_now: float = 0.038
    ship_p95_now: float = 200.0
    sessions_window: int = 12000
    aov: float = 84.0
    plugin_version: str = "2.4.0"
    checkout_latency_ms: float = 450.0

    def now(self) -> datetime:
        return self.clock.now()

    def reset(self) -> None:
        self.__dict__.update(SimState().__dict__)


STATE = SimState()


def utcnow() -> datetime:
    return datetime.now(UTC)
