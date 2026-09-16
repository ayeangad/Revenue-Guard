"""Deterministic simulation clock. Wall-clock never used inside evals."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class SimulationClock:
    t0: datetime = field(default_factory=lambda: datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    offset_s: float = 0.0

    def now(self) -> datetime:
        return self.t0 + timedelta(seconds=self.offset_s)

    def advance(self, seconds: float) -> datetime:
        self.offset_s += seconds
        return self.now()

    def at(self, seconds: float) -> datetime:
        return self.t0 + timedelta(seconds=seconds)
