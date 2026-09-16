"""Counterfactual revenue impact. Deterministic; LLM never computes this."""
from __future__ import annotations

from pydantic import BaseModel


class RevenueImpact(BaseModel):
    sessions: int
    baseline_conv: float
    observed_conv: float
    aov: float
    expected_orders: float
    observed_orders: float
    lost_orders: float
    estimated_impact: float
    reliable: bool
    assumptions: list[str]


def estimate_counterfactual(
    sessions: int, baseline_conv: float, observed_conv: float, aov: float
) -> RevenueImpact:
    """expected = sessions*baseline; lost = expected - observed; impact = lost*AOV."""
    if sessions <= 0:
        return RevenueImpact(
            sessions=sessions, baseline_conv=baseline_conv, observed_conv=observed_conv,
            aov=aov, expected_orders=0, observed_orders=0, lost_orders=0,
            estimated_impact=0.0, reliable=False,
            assumptions=["no traffic in window: impact cannot be estimated reliably"],
        )
    expected = sessions * baseline_conv
    observed = sessions * observed_conv
    lost = max(0.0, expected - observed)
    reliable = sessions >= 500 and baseline_conv > 0
    assumptions = [
        f"baseline_conv={baseline_conv:.4f} from pre-window baseline",
        f"observed_conv={observed_conv:.4f} in affected window",
        f"aov=${aov:.2f} assumed stable",
        "counterfactual assumes traffic mix unchanged",
    ]
    if not reliable:
        assumptions.append("low sample: impact cannot be estimated reliably")
    return RevenueImpact(
        sessions=sessions, baseline_conv=baseline_conv, observed_conv=observed_conv,
        aov=aov, expected_orders=round(expected, 1), observed_orders=round(observed, 1),
        lost_orders=round(lost, 1), estimated_impact=round(lost * aov, 2),
        reliable=reliable, assumptions=assumptions,
    )
