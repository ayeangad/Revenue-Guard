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
    sessions: int, baseline_conv: float, observed_conv: float, aov: float | None
) -> RevenueImpact:
    """expected = sessions*baseline; lost = expected - observed; impact = lost*AOV.

    Validation (never silently coerce):
    - sessions < 0, conversion outside [0, 1], or negative AOV -> ValueError
    - sessions == 0 or AOV unknown (None) -> reliable=False, impact 0.0.
      Missing is NOT treated as zero revenue; it is reported as unknowable.
    """
    for name, v in (("baseline_conv", baseline_conv), ("observed_conv", observed_conv)):
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"{name}={v}: conversion must be in [0, 1]")
    if sessions < 0:
        raise ValueError(f"sessions={sessions}: must be >= 0")
    if aov is not None and aov < 0:
        raise ValueError(f"aov={aov}: must be >= 0")
    if sessions <= 0 or aov is None:
        reason = ("no traffic in window: impact cannot be estimated reliably"
                  if sessions <= 0 else
                  "AOV unknown: impact cannot be estimated reliably (missing != 0)")
        return RevenueImpact(
            sessions=sessions, baseline_conv=baseline_conv, observed_conv=observed_conv,
            aov=aov if aov is not None else 0.0,
            expected_orders=0, observed_orders=0, lost_orders=0,
            estimated_impact=0.0, reliable=False, assumptions=[reason],
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
