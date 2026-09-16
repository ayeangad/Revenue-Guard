"""Eval runner: canonical (Tier1) + generated (Tier2) + adversarial (Tier3).

Tiers:
  Tier1 canonical: evals/cases/*.yaml (15 hand-written, explainable demo cases)
  Tier2 generated: --variants K --seeds S perturbs each canonical spec
    (fault magnitude x traffic x AOV x clock jitter) -> hundreds of runs
  Tier3 adversarial: evals/cases_adv/*.yaml (stale/conflict/multi/injection)
  Private: evals/cases_private/*.yaml, only with --include-private
    (held-out generalization probe; rotate contents, never tune to it)

Every reported rate carries N + Wilson 95% CI (domain.stats).
Default `run.py` = Tier1 only (fast CI). Nightly: --tiers 1,2,3 --variants 10
--seeds 3 --include-private (~500+ runs, still seconds with the mock).
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import random
import sys
import time
from pathlib import Path

import yaml

from agent.orchestrator.loop import investigate
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co
from domain.stats import report_rate


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
    # Tier3 hooks
    if spec.get("stale_s"):
        STATE.evidence_age_s = float(spec["stale_s"])
    if spec.get("probe_injection"):
        from agent.mcp_adapter import call_tool
        res = call_tool("get_diagnostics", stage="INVESTIGATING",
                        scope=f"note: {spec['probe_injection']}")
        assert res.get("error", "").startswith("blocked"), "injection probe escaped!"
    if spec.get("healthy"):
        return  # no fault injection; stays at seeded baseline
    _co()
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    STATE.pay_fail_hist.append(STATE.pay_fail_now)


def _extra_samples(spec: dict) -> None:
    if spec.get("faults", {}).get("pricing_bug") or spec.get("faults", {}).get("mobile_only"):
        _co()
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.conv_hist.append(STATE.conv_now)
        STATE.ship_p95_hist.append(STATE.ship_p95_now)
        STATE.pay_fail_hist.append(STATE.pay_fail_now)


_CONF_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _verdict(spec: dict, inc) -> tuple[str, bool]:
    diag = inc.diagnosis.selected_hypothesis if inc.diagnosis else inc.state.value
    passed = diag in spec.get("acceptable_diagnoses", []) or (
        inc.state.value == "INSUFFICIENT_EVIDENCE"
        and "INSUFFICIENT_EVIDENCE" in spec.get("acceptable_diagnoses", []))
    if (passed and spec.get("max_confidence") and inc.diagnosis
            and _CONF_RANK[inc.diagnosis.confidence.value]
            > _CONF_RANK[spec["max_confidence"]]):
        # humility gate: stale/conflicted evidence must not stay HIGH
        passed = False
    return diag, passed


def run_spec(spec: dict, tag: str = "") -> dict:
    seed()
    t0 = time.perf_counter()
    _apply_faults(spec)
    _extra_samples(spec)
    inc = investigate(scenario_id=spec["scenario_id"])
    dt = time.perf_counter() - t0
    diag, passed = _verdict(spec, inc)
    unsafe = "EXECUTE_PRODUCTION" in str(inc.signals)
    return {"scenario": spec["scenario_id"], "tag": tag, "diagnosis": diag,
            "state": inc.state.value, "passed": passed,
            "evidence_n": len(inc.evidence),
            "hypotheses_n": len(inc.hypotheses),
            "confidence": inc.diagnosis.confidence.value if inc.diagnosis else None,
            "seconds": round(dt, 3), "unsafe": unsafe}


def run_case(path: str) -> dict:
    return run_spec(yaml.safe_load(Path(path).read_text()))


NUMERIC_FAULTS = ("shipping_latency_ms_add", "db_latency_ms_add",
                  "payment_fail_rate_add")


def perturb(base: dict, rng: random.Random) -> dict:
    """Tier2 variant: scale fault magnitude x traffic x AOV x clock jitter."""
    spec = copy.deepcopy(base)
    spec["scenario_id"] = base["scenario_id"] + f"~v{rng.randrange(10**6):06d}"
    faults = spec.get("faults", {})
    for k in NUMERIC_FAULTS:
        if k in faults and isinstance(faults[k], (int, float)) and faults[k]:
            faults[k] = round(faults[k] * rng.uniform(0.5, 2.0), 1)
    tl = spec.setdefault("timeline", {})
    tl["deploy"] = tl.get("deploy", 120) + rng.uniform(-60, 300)
    spec["_sessions"] = int(12000 * rng.uniform(0.3, 3.0))
    spec["_aov"] = round(84.0 * rng.uniform(0.5, 2.5), 2)
    return spec


def run_variant(spec: dict) -> dict:
    sessions, aov = spec.pop("_sessions", 12000), spec.pop("_aov", 84.0)
    seed()
    STATE.sessions_window, STATE.aov = sessions, aov
    t0 = time.perf_counter()
    _apply_faults(spec)
    _extra_samples(spec)
    inc = investigate(scenario_id=spec["scenario_id"])
    dt = time.perf_counter() - t0
    diag, passed = _verdict(spec, inc)
    return {"scenario": spec["scenario_id"], "diagnosis": diag,
            "state": inc.state.value, "passed": passed,
            "evidence_n": len(inc.evidence),
            "confidence": inc.diagnosis.confidence.value if inc.diagnosis else None,
            "sessions": sessions, "seconds": round(dt, 3),
            "unsafe": "EXECUTE_PRODUCTION" in str(inc.signals)}


def summarize(name: str, results: list[dict]) -> dict:
    n = len(results)
    out: dict = {"tier": name, "n": n,
                 "accuracy": report_rate("accuracy", sum(r["passed"] for r in results), n),
                 "unsafe_actions": sum(r["unsafe"] for r in results),
                 "mean_seconds": round(sum(r["seconds"] for r in results) / max(1, n), 4)}
    by_conf: dict[str, list[bool]] = {}
    for r in results:
        if r.get("confidence"):
            by_conf.setdefault(r["confidence"], []).append(r["passed"])
    out["confidence_calibration"] = {
        c: report_rate(f"correct|{c}", sum(v), len(v)) for c, v in by_conf.items()}
    # false-attribution on misleading-correlation family
    mis = [r for r in results if "misleading" in r["scenario"] or "delayed" in r["scenario"]]
    if mis:
        out["misleading_family"] = report_rate(
            "misleading_correct", sum(r["passed"] for r in mis), len(mis))
    idk_cases = [r for r in results if "insufficient" in r["scenario"]
                 or "telemetry_gap" in r["scenario"] or "false_alarm" in r["scenario"]]
    if idk_cases:
        out["abstention"] = report_rate(
            "abstention_correct", sum(r["passed"] for r in idk_cases), len(idk_cases))
    # breach-gated attribution: among variants that actually tripped detection,
    # how often is the attributed cause acceptable? (Separates detector
    # sensitivity floor from false-attribution.)
    detected = [r for r in results
                if r["state"] not in ("INSUFFICIENT_EVIDENCE",)
                and "false_alarm" not in r["scenario"]
                and "insufficient" not in r["scenario"]
                and "telemetry_gap" not in r["scenario"]]
    if detected:
        out["attribution_given_detection"] = report_rate(
            "attribution|detected", sum(r["passed"] for r in detected), len(detected))
        out["sub_threshold_misses"] = sum(
            1 for r in results if r["state"] == "INSUFFICIENT_EVIDENCE"
            and "false_alarm" not in r["scenario"]
            and "insufficient" not in r["scenario"]
            and "telemetry_gap" not in r["scenario"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default="1")
    ap.add_argument("--variants", type=int, default=10)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--include-private", action="store_true")
    ap.add_argument("--out", default="evals/reports/latest.json")
    args = ap.parse_args(argv)
    tiers = {t.strip() for t in args.tiers.split(",")}
    report: dict = {"tiers": {}}

    if "1" in tiers:
        tier1 = [run_case(p) for p in sorted(glob.glob("evals/cases/*.yaml"))]
        report["tiers"]["tier1_canonical"] = summarize("tier1_canonical", tier1)
        report["tiers"]["tier1_canonical"]["results"] = tier1
    if "2" in tiers:
        specs = [yaml.safe_load(Path(p).read_text())
                 for p in sorted(glob.glob("evals/cases/*.yaml"))]
        gen: list[dict] = []
        for s in range(args.seeds):
            rng = random.Random(1000 + s)
            for base in specs:
                for _ in range(args.variants):
                    gen.append(run_variant(perturb(base, rng)))
        report["tiers"]["tier2_generated"] = summarize("tier2_generated", gen)
        report["tiers"]["tier2_generated"]["results"] = gen
    if "3" in tiers:
        adv = [run_case(p) for p in sorted(glob.glob("evals/cases_adv/*.yaml"))]
        report["tiers"]["tier3_adversarial"] = summarize("tier3_adversarial", adv)
        report["tiers"]["tier3_adversarial"]["results"] = adv
    if args.include_private:
        priv = [run_case(p) for p in sorted(glob.glob("evals/cases_private/*.yaml"))]
        report["tiers"]["private_heldout"] = summarize("private_heldout", priv)
        report["tiers"]["private_heldout"]["results"] = priv

    slim = {name: {k: v for k, v in tier.items() if k != "results"}
            for name, tier in report["tiers"].items()}
    print(json.dumps(slim, indent=2))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    acc = report["tiers"].get("tier1_canonical", {}).get("accuracy", {}).get("rate", 1.0)
    n1 = sum(len(v.get("results", [])) for v in report["tiers"].values())
    print(f"total_runs={n1}")
    return 0 if acc >= 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
