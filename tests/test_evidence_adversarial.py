"""C2: stale-data behavior, contradictory evidence, tool-failure matrix, LLM contract."""
from datetime import UTC, datetime, timedelta

import pytest

from agent.orchestrator.loop import investigate
from agent.tools import registry as regmod
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co
from domain.conflicts import detect_conflicts
from domain.evidence import assess, downgrade, is_stale
from domain.models import Evidence, IncidentState


def _ev(tool: str, claim: str, age_s: int = 5) -> Evidence:
    now = datetime.now(UTC)
    return Evidence(source_type="metric", source_id="s", tool_name=tool,
                    observed_at=now - timedelta(seconds=age_s), collected_at=now,
                    extracted_claim=claim)


def _inject_shipping():
    STATE.deploys.append(Deploy(deploy_id="d1", version="2.4.1", sha="s",
                                component="shipping-plugin",
                                t_offset_s=STATE.clock.offset_s))
    STATE.plugin_version = "2.4.1"
    STATE.faults.shipping_latency_ms_add = 1620.0
    _co()
    for hist, val in ((STATE.checkout_p95_hist, STATE.checkout_p95_now),
                      (STATE.conv_hist, STATE.conv_now),
                      (STATE.ship_p95_hist, STATE.ship_p95_now),
                      (STATE.pay_fail_hist, STATE.pay_fail_now)):
        hist.append(val)


def test_freshness_marks_stale():
    ev = _ev("get_checkout_metrics", "checkout_p95 baseline=450ms", age_s=5)
    assert not is_stale(ev)
    old = _ev("get_checkout_metrics", "checkout_p95 baseline=450ms", age_s=3600)
    assert is_stale(old)
    rep = assess([ev, old])
    assert rep["stale_ids"] == [old.evidence_id] and not rep["all_fresh"]
    assert downgrade("HIGH") == "MEDIUM" and downgrade("MEDIUM") == "LOW" \
        and downgrade("LOW") == "LOW"


def test_stale_key_evidence_downgrades_confidence(monkeypatch):
    """Aged checkout evidence must reduce confidence + name re-collection."""
    seed()
    _inject_shipping()
    real = regmod.ToolRegistry.get_checkout_metrics

    def aged(self, stage="TRIAGE"):
        payload, ev = real(self, stage)
        ev.observed_at = ev.collected_at - timedelta(seconds=3600)
        return payload, ev
    monkeypatch.setattr(regmod.ToolRegistry, "get_checkout_metrics", aged)
    inc = investigate()
    assert inc.diagnosis.confidence in (
        __import__("domain.models", fromlist=["Confidence"]).Confidence.MEDIUM,
        __import__("domain.models", fromlist=["Confidence"]).Confidence.LOW)
    assert any("stale" in m for m in inc.diagnosis.missing)


def test_conflict_metric_vs_journey():
    evs = [_ev("get_checkout_metrics", "checkout_p95 baseline=450ms current=460ms dev=+2%"),
           _ev("run_validation", "synthetic checkout passed=False duration=2411ms")]
    conflicts = detect_conflicts(evs)
    assert any(c.startswith("metric_vs_journey") for c in conflicts)


def test_conflict_deploy_presence():
    evs = [_ev("get_recent_deploys", "0 deploys; latest=None"),
           _ev("get_dependency_health", "shipping_p95=1820ms after deploy abc123")]
    assert any(c.startswith("deploy_presence") for c in detect_conflicts(evs))


def test_conflict_healthy_deps_spiked_checkout():
    evs = [_ev("get_dependency_health", "shipping_p95=190ms"),
           _ev("get_checkout_metrics", "checkout_p95 baseline=450ms current=1650ms dev=+267%")]
    assert any(c.startswith("dependency_vs_checkout") for c in detect_conflicts(evs))


@pytest.mark.parametrize("tool", [
    "get_checkout_metrics", "get_conversion_metrics", "get_recent_deploys",
    "get_dependency_health", "get_error_logs", "get_diagnostics",
    "estimate_revenue_impact"])
@pytest.mark.parametrize("failure", ["timeout", "malformed", "denied"])
def test_tool_failure_matrix_degrades_safely(monkeypatch, tool, failure):
    """Every typed tool x {timeout, malformed, denied}: no crash, no invented data."""
    seed()
    _inject_shipping()
    exc = {"timeout": ConnectionError("t"),
           "malformed": ValueError("bad payload"),
           "denied": PermissionError("denied")}[failure]

    def _boom(self, *a, **k):
        raise exc
    monkeypatch.setattr(regmod.ToolRegistry, tool, _boom)
    inc = investigate()
    # Must end in a known safe state, never with invented diagnosis evidence
    assert inc.state in (IncidentState.DRY_RUN, IncidentState.INSUFFICIENT_EVIDENCE)
    if inc.state == IncidentState.DRY_RUN:
        assert inc.diagnosis is not None and len(inc.diagnosis.supporting) > 0
    else:
        assert inc.diagnosis is None  # no confident guess without evidence
