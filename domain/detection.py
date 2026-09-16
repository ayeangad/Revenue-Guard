"""Boring deterministic detector: rolling baseline + prev-period + percentiles.

Outputs baseline/current/deviation%. No ML, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class Signal:
    name: str
    baseline: float
    current: float

    @property
    def deviation_pct(self) -> float:
        if self.baseline == 0:
            return 0.0 if self.current == 0 else float("inf")
        return (self.current - self.baseline) / abs(self.baseline) * 100


@dataclass
class Detection:
    breached: bool
    signals: list[Signal]
    summary: str


def rolling_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def zscore(current: float, history: list[float]) -> float:
    if len(history) < 5:
        return 0.0
    mu, sd = mean(history), pstdev(history)
    if sd == 0:
        return 0.0 if current == mu else 99.0
    return (current - mu) / sd


def detect_checkout_regression(
    checkout_p95_hist: list[float],
    checkout_p95_now: float,
    conv_hist: list[float],
    conv_now: float,
    ship_p95_hist: list[float] | None = None,
    ship_p95_now: float | None = None,
    z_thresh: float = 3.0,
    conv_drop_pct: float = -10.0,
) -> Detection:
    signals = [
        Signal("checkout_p95_ms", rolling_mean(checkout_p95_hist), checkout_p95_now),
        Signal("conversion_rate", rolling_mean(conv_hist), conv_now),
    ]
    if ship_p95_hist is not None and ship_p95_now is not None:
        signals.append(Signal("shipping_p95_ms", rolling_mean(ship_p95_hist), ship_p95_now))
    z = zscore(checkout_p95_now, checkout_p95_hist)
    conv_dev = signals[1].deviation_pct
    breached = (z >= z_thresh) or (conv_dev <= conv_drop_pct)
    summary = (
        f"checkout_p95 baseline={signals[0].baseline:.0f}ms current={signals[0].current:.0f}ms "
        f"dev={signals[0].deviation_pct:+.0f}% z={z:.1f}; "
        f"conversion baseline={signals[1].baseline:.3f} current={signals[1].current:.3f} "
        f"dev={conv_dev:+.1f}%"
    )
    return Detection(breached=breached, signals=signals, summary=summary)
