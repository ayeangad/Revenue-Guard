"""Iterative investigation orchestrator.

Deterministic state transitions; LLM/mock only ranks hypotheses and picks
next evidence action. Produces provenance-linked Diagnosis.
"""
from __future__ import annotations

from agent.providers.llm import get_provider
from agent.tools.registry import ToolRegistry
from domain.models import Confidence, Diagnosis, Hypothesis, Incident, IncidentState


def investigate(store_id: str = "demo-store", scenario_id: str = "bad_shipping_deploy_001") -> Incident:
    reg = ToolRegistry()
    inc = Incident(store_id=store_id, state=IncidentState.DETECTED)

    # TRIAGE (stage-gated reads)
    m, ev1 = reg.get_checkout_metrics("TRIAGE")
    _conv, ev2 = reg.get_conversion_metrics("TRIAGE")
    _dep, ev3 = reg.get_recent_deploys("TRIAGE")
    inc.evidence += [ev1, ev2, ev3]
    det = m["detection"]
    if not det.breached:
        inc.state = IncidentState.INSUFFICIENT_EVIDENCE
        return inc
    inc.state = IncidentState.TRIAGED
    inc.signals = {"summary": det.summary}

    # INITIAL_HYPOTHESES ⇄ COLLECT_EVIDENCE ⇄ UPDATE_HYPOTHESES (2 rounds max MVP)
    provider = get_provider()
    flags = _signal_flags(det, tele_gap=False)
    recent_deploy = flags["recent_deploy"]
    ranked = provider.rank_hypotheses(**flags)
    inc.state = IncidentState.INITIAL_HYPOTHESES
    inc.hypotheses = [Hypothesis(name=h["name"]) for h in ranked]

    # Round 1 evidence
    inc.state = IncidentState.COLLECT_EVIDENCE
    dep_payload, ev_dep = reg.get_dependency_health("INVESTIGATING")
    _, ev_log = reg.get_error_logs("INVESTIGATING")
    _, ev_diag = reg.get_diagnostics(stage="INVESTIGATING")
    inc.evidence += [ev_dep, ev_log, ev_diag]
    tele_gap = bool(dep_payload.get("unavailable"))

    # Round 2: update hypotheses with fresh evidence
    inc.state = IncidentState.UPDATE_HYPOTHESES
    flags2 = _signal_flags(det, tele_gap=tele_gap)
    flags2["ship_spike"] = flags2["ship_spike"] and not tele_gap
    flags2["checkout_spike"] = True
    ranked2 = provider.rank_hypotheses(**flags2)
    # link evidence ids to hypotheses (provenance)
    ev_ids = [e.evidence_id for e in inc.evidence]
    inc.hypotheses = [Hypothesis(name=h["name"], supporting=ev_ids[:3],
                                 missing=[] if not tele_gap else ["dependency telemetry"])
                      for h in ranked2]

    if tele_gap and not recent_deploy:
        inc.state = IncidentState.INSUFFICIENT_EVIDENCE
        return inc

    # DIAGNOSIS (deterministic record from ranked list)
    top = ranked2[0]["name"]
    conf = Confidence(ranked2[0].get("confidence", "MEDIUM"))
    ship_spike = flags2.get("ship_spike", False)
    breakdown = {
        "deploy_corr": "strong" if recent_deploy else "weak",
        "dependency_corr": "strong" if ship_spike and not tele_gap else "weak",
        "cohort_match": "strong" if flags2.get("mobile_only") else "medium",
        "causal_direct": "weak",  # honest: correlation, not proven causation
    }
    contradict = [e.evidence_id for e in inc.evidence if "unavailable" in e.extracted_claim]
    inc.diagnosis = Diagnosis(
        selected_hypothesis=top, confidence=conf, breakdown=breakdown,
        supporting=ev_ids, contradicting=contradict,
        missing=["exact query plan"] if "deploy" in top else [],
        reasoning_summary=f"Top hypothesis {top} from competing set "
                          f"{[h['name'] for h in ranked2]}; see linked evidence.")
    inc.state = IncidentState.DIAGNOSIS

    # IMPACT (deterministic counterfactual)
    impact_payload, ev_imp = reg.estimate_revenue_impact("IMPACT_ESTIMATION")
    inc.evidence.append(ev_imp)
    inc.signals["impact"] = impact_payload["impact"].model_dump()
    inc.state = IncidentState.IMPACT_ESTIMATION

    # RECOMMENDATION + DRY_RUN (no writes yet)
    inc.state = IncidentState.RECOMMENDATION
    inc.signals["recommendation"] = (
        "rollback shipping-plugin v2.4.1 -> v2.4.0" if "shipping" in top or "deploy" in top
        else "investigate further; no safe rollback identified")
    inc.state = IncidentState.DRY_RUN
    inc.signals["dry_run"] = f"WOULD execute: {inc.signals['recommendation']}. No action taken."
    return inc


def _signal_flags(det, tele_gap: bool = False) -> dict:
    from commerce.sim.state import STATE
    ship_hist = list(STATE.ship_p95_hist)
    ship_base = sum(ship_hist) / len(ship_hist) if ship_hist else 200.0
    pay_hist = list(STATE.pay_fail_hist) if hasattr(STATE, "pay_fail_hist") else [0.02]
    pay_base = sum(pay_hist) / len(pay_hist) if pay_hist else 0.02
    return {
        "ship_spike": STATE.ship_p95_now > ship_base * 1.5,
        "recent_deploy": bool(STATE.deploys),
        "telemetry_gap": tele_gap or STATE.faults.telemetry_gap,
        "payment_spike": STATE.pay_fail_now > pay_base + 0.08,
        "pricing_anomaly": STATE.pricing_error_now > 0.01 or STATE.faults.pricing_bug,
        "mobile_only": STATE.faults.mobile_only
        or (STATE.desktop_conv_now - STATE.mobile_conv_now) > 0.015,
        "db_spike": STATE.faults.db_latency_ms_add > 150,
        "cache_drop": STATE.faults.cache_bust or STATE.cache_hit_now < 0.7,
        "checkout_spike": det.signals[0].deviation_pct > 50,
    }


def STATE_ship_spike() -> bool:
    return _ship_spike_simple()


def _ship_spike_simple() -> bool:
    from commerce.sim.state import STATE
    hist = list(STATE.ship_p95_hist)
    if not hist:
        return False
    base = sum(hist) / len(hist)
    return STATE.ship_p95_now > base * 1.5
