"""Contradictory-evidence detector: tools disagreeing must not be averaged away.

Rules operate on evidence claims (auditable strings), never on model output.
A conflict forces: recorded in contradicting[], confidence capped at MEDIUM,
and an explicit follow-up measurement named in missing[].
"""
from __future__ import annotations

import re

from domain.models import Evidence


def _num(claim: str, key: str) -> float | None:
    m = re.search(rf"{key}\s*=\s*([0-9.]+)", claim)
    return float(m.group(1)) if m else None


def detect_conflicts(evidence: list[Evidence]) -> list[str]:
    by_tool: dict[str, list[Evidence]] = {}
    for e in evidence:
        by_tool.setdefault(e.tool_name, []).append(e)
    conflicts: list[str] = []

    metrics = by_tool.get("get_checkout_metrics", [])
    validations = by_tool.get("run_validation", [])
    if metrics and validations:
        m = metrics[-1].extracted_claim
        dev_m = re.search(r"dev=([+-]?[0-9.]+)%", m)
        dev = float(dev_m.group(1)) if dev_m else 0.0
        v_failed = any("passed=False" in v.extracted_claim for v in validations)
        if abs(dev) < 10 and v_failed:
            conflicts.append("metric_vs_journey: checkout metric normal "
                             "but synthetic journey failed -> re-measure, trust journey")

    deploys = by_tool.get("get_recent_deploys", [])
    if deploys:
        last = deploys[-1].extracted_claim
        if "0 deploys" in last and any(
                "deploy" in e.extracted_claim and e.tool_name != "get_recent_deploys"
                for e in evidence):
            conflicts.append("deploy_presence: deploy history empty but other "
                             "evidence references a deploy -> check audit log")

    deps = by_tool.get("get_dependency_health", [])
    if deps and metrics:
        d = deps[-1].extracted_claim
        ship_m = re.search(r"shipping_p95=([0-9.]+)ms", d)
        if ship_m and float(ship_m.group(1)) < 300:
            dev_m = re.search(r"dev=([+-]?[0-9.]+)%", metrics[-1].extracted_claim)
            if dev_m and float(dev_m.group(1)) > 100:
                conflicts.append("dependency_vs_checkout: dependencies healthy but "
                                 "checkout spiked -> cause is not dependency; widen search")

    if any("unavailable" in e.extracted_claim for e in evidence):
        conflicts.append("telemetry_gap: some sources unavailable -> "
                         "diagnosis is provisional")
    return conflicts
