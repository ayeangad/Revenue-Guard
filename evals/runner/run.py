"""Minimal eval runner: runs scenarios, checks acceptable diagnoses, writes report."""
from __future__ import annotations

import json
import sys

import yaml

from agent.orchestrator.loop import investigate
from commerce.sim import store as _store  # noqa: F401 (register routes/state fns)
from commerce.sim.seed import seed
from commerce.sim.state import STATE


def run_case(path: str) -> dict:
    with open(path) as f:
        spec = yaml.safe_load(f)
    seed()
    # Reproduce timeline deterministically via SimulationClock offsets
    tl = spec.get("timeline", {})
    STATE.clock.advance(tl.get("deploy", 300))
    # Inject fault per scenario root cause
    if "shipping" in spec["root_cause"]:
        STATE.deploys.append(__import__("commerce.sim.state", fromlist=["Deploy"]).Deploy(
            deploy_id="dep_1", version="2.4.1", sha="abc123",
            component="shipping-plugin", t_offset_s=STATE.clock.offset_s))
        STATE.plugin_version = "2.4.1"
        STATE.faults.shipping_latency_ms_add = 1620.0
        from commerce.sim.store import checkout as _co
        _co()
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.conv_hist.append(STATE.conv_now)
        STATE.ship_p95_hist.append(STATE.ship_p95_now)
    if spec["scenario_id"] == "telemetry_gap_001":
        STATE.faults.telemetry_gap = True
    if spec["scenario_id"] == "misleading_corr_001":
        # traffic-like DB saturation WITHOUT ship spike, but with recent deploy
        STATE.faults.shipping_latency_ms_add = 0.0
        STATE.faults.db_latency_ms_add = 400.0
        from commerce.sim.store import checkout as _co2
        _co2()
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.conv_hist.append(STATE.conv_now)
        STATE.ship_p95_hist.append(200.0)
        STATE.ship_p95_now = 200.0
    inc = investigate(scenario_id=spec["scenario_id"])
    diag = inc.diagnosis.selected_hypothesis if inc.diagnosis else inc.state.value
    passed = diag in spec.get("acceptable_diagnoses", []) or (
        inc.state.value == "INSUFFICIENT_EVIDENCE"
        and "INSUFFICIENT_EVIDENCE" in spec.get("acceptable_diagnoses", []))
    return {"scenario": spec["scenario_id"], "diagnosis": diag,
            "state": inc.state.value, "passed": passed,
            "evidence_n": len(inc.evidence)}


if __name__ == "__main__":
    import glob
    results = [run_case(p) for p in sorted(glob.glob("evals/cases/*.yaml"))]
    print(json.dumps(results, indent=2))
    with open("evals/reports/latest.json", "w") as f:
        f.write(json.dumps(results, indent=2))
    acc = sum(r["passed"] for r in results) / max(1, len(results))
    print(f"accuracy={acc:.2f}")
    sys.exit(0 if acc >= 0.5 else 1)
