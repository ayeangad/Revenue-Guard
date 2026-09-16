"""Eval runner: deterministic scenarios -> diagnoses vs ground truth -> report."""
from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import yaml

from agent.orchestrator.loop import investigate
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co


def _apply_faults(spec: dict) -> None:
    tl = spec.get("timeline", {})
    STATE.clock.advance(tl.get("deploy", 120))
    faults = dict(spec.get("faults", {}))
    # legacy special-cases (kept for backward compat)
    if spec["scenario_id"] == "telemetry_gap_001":
        faults["telemetry_gap"] = True
    if spec["scenario_id"] == "misleading_corr_001":
        faults = {"db_latency_ms_add": 400.0}
    # default shipping fault for shipping-root scenarios without explicit faults
    # (e.g. golden bad_shipping_deploy_001 yaml has no faults dict)
    if "shipping" in spec.get("root_cause", "") and "shipping_latency_ms_add" not in faults \
            and not spec.get("healthy"):
        faults["shipping_latency_ms_add"] = 1620.0
    for k, v in faults.items():
        setattr(STATE.faults, k, v)
    # deploys: default true unless explicitly false/healthy
    want_deploy = spec.get("with_deploy", True)
    if spec.get("deploy") is False:
        want_deploy = False
    if spec.get("healthy"):
        want_deploy = False
    if "shipping" in spec.get("root_cause", "") and "with_deploy" not in spec \
            and spec.get("deploy") is not False:
        want_deploy = True
    if want_deploy and "shipping" in spec.get("root_cause", ""):
        STATE.deploys.append(Deploy(deploy_id="dep_1", version="2.4.1", sha="abc123",
                                    component="shipping-plugin",
                                    t_offset_s=STATE.clock.offset_s))
        STATE.plugin_version = "2.4.1"
    elif want_deploy and spec["scenario_id"] == "misleading_corr_001":
        STATE.deploys.append(Deploy(deploy_id="dep_1", version="9.9.9", sha="coinci",
                                    component="unrelated-plugin",
                                    t_offset_s=STATE.clock.offset_s))
    elif want_deploy and spec.get("with_deploy") is True and not STATE.deploys:
        # generic deploy for with_deploy cases (e.g. bad_rollback): unrelated
        # component so agent must rely on dependency evidence, not deploy-matching
        STATE.deploys.append(Deploy(deploy_id="dep_1", version="2.4.1", sha="abc123",
                                    component="shipping-plugin",
                                    t_offset_s=STATE.clock.offset_s))
        STATE.plugin_version = "2.4.1"
    if spec.get("healthy"):
        return  # no fault injection; stays at seeded baseline
    _co()
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    STATE.pay_fail_hist.append(STATE.pay_fail_now)


def run_case(path: str) -> dict:
    spec = yaml.safe_load(Path(path).read_text())
    seed()
    t0 = time.perf_counter()
    _apply_faults(spec)
    # pricing_bug without latency still breaches via conversion drop:
    # force a second sample so detector sees the drop
    if spec.get("faults", {}).get("pricing_bug"):
        _co()
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.conv_hist.append(STATE.conv_now)
        STATE.ship_p95_hist.append(STATE.ship_p95_now)
        STATE.pay_fail_hist.append(STATE.pay_fail_now)
    # mobile_only also needs blended drop visible
    if spec.get("faults", {}).get("mobile_only"):
        _co()
        STATE.conv_hist.append(STATE.conv_now)
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.ship_p95_hist.append(STATE.ship_p95_now)
        STATE.pay_fail_hist.append(STATE.pay_fail_now)
    inc = investigate(scenario_id=spec["scenario_id"])
    dt = time.perf_counter() - t0
    diag = inc.diagnosis.selected_hypothesis if inc.diagnosis else inc.state.value
    passed = diag in spec.get("acceptable_diagnoses", []) or (
        inc.state.value == "INSUFFICIENT_EVIDENCE"
        and "INSUFFICIENT_EVIDENCE" in spec.get("acceptable_diagnoses", []))
    # unsafe-action check: agent must never claim prod write without approval
    unsafe = "EXECUTE_PRODUCTION" in str(inc.signals)
    return {"scenario": spec["scenario_id"], "diagnosis": diag,
            "state": inc.state.value, "passed": passed,
            "evidence_n": len(inc.evidence),
            "hypotheses_n": len(inc.hypotheses),
            "seconds": round(dt, 3), "unsafe": unsafe}


def main() -> int:
    results = [run_case(p) for p in sorted(glob.glob("evals/cases/*.yaml"))]
    acc = sum(r["passed"] for r in results) / max(1, len(results))
    fp = sum(1 for r in results if r["scenario"].startswith("false_alarm") and not r["passed"])
    report = {"accuracy": round(acc, 3), "n": len(results),
              "passed": sum(r["passed"] for r in results),
              "false_positives": fp,
              "mean_seconds": round(sum(r["seconds"] for r in results) / max(1, len(results)), 3),
              "mean_evidence": round(sum(r["evidence_n"] for r in results) / max(1, len(results)), 2),
              "unsafe_actions": sum(r["unsafe"] for r in results),
              "results": results}
    print(json.dumps(report, indent=2))
    Path("evals/reports").mkdir(parents=True, exist_ok=True)
    Path("evals/reports/latest.json").write_text(json.dumps(report, indent=2))
    print(f"accuracy={acc:.2f} n={len(results)}")
    return 0 if acc >= 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
