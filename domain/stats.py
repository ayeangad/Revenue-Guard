"""Small-sample-honest statistics: Wilson CIs, never bare proportions."""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k/n. Returns (lo, hi)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(max(0.0, (center - margin) / denom), 4),
            round(min(1.0, (center + margin) / denom), 4))


def diff_ci(k1: int, n1: int, k2: int, n2: int, z: float = 1.96) -> tuple[float, float]:
    """Normal-approx CI for p1 - p2 (documented approximation, fine for n>=30)."""
    if n1 == 0 or n2 == 0:
        return (0.0, 0.0)
    p1, p2 = k1 / n1, k2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return (round(p1 - p2 - z * se, 4), round(p1 - p2 + z * se, 4))


def report_rate(name: str, k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"metric": name, "k": k, "n": n, "rate": round(k / n, 4) if n else 0.0,
            "ci95": [lo, hi]}
