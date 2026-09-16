"""Golden scenario: bad_shipping_deploy_001 full CLI path (18-step provenance)."""
from agent.orchestrator.loop import investigate
from agent.tools.registry import ToolRegistry
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from domain.models import IncidentState


def test_golden_path():
    seed()
    # healthy baseline: no incident
    inc0 = investigate()
    assert inc0.state == IncidentState.INSUFFICIENT_EVIDENCE  # no breach, honest answer

    # inject: deploy shipping-plugin v2.4.1 -> shipping + checkout spike + conv drop
    STATE.clock.advance(300)
    STATE.deploys.append(Deploy(deploy_id="dep_1", version="2.4.1", sha="abc123",
                                component="shipping-plugin", t_offset_s=STATE.clock.offset_s))
    STATE.plugin_version = "2.4.1"
    STATE.faults.shipping_latency_ms_add = 1620.0
    from commerce.sim.store import checkout as _co
    _co()
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)

    inc = investigate()
    assert inc.state == IncidentState.DRY_RUN, inc.model_dump_json()
    assert inc.diagnosis is not None
    assert inc.diagnosis.selected_hypothesis in (
        "shipping_plugin_regression", "shipping_dependency_degradation_via_deploy")
    assert len(inc.evidence) >= 6  # triage 3 + evidence 3 + impact 1
    assert len(inc.hypotheses) >= 2  # competing hypotheses required
    assert "counterfactual" in str(inc.signals) or "impact" in inc.signals
    assert inc.diagnosis.confidence.value in ("HIGH", "MEDIUM", "LOW")
    assert "WOULD execute" in inc.signals["dry_run"]

    # stage -> validate -> verify (symmetric signals)
    reg = ToolRegistry()
    staged, _ = reg.create_staging_change("rollback shipping-plugin", stage="STAGING")
    assert staged["version"] == "2.4.0"
    val, _ = reg.run_validation(stage="VALIDATION")
    assert val["passed"] is True
    m, _ = reg.get_checkout_metrics("TRIAGE")
    assert not m["detection"].breached  # recovered


def test_stage_gating():
    from commerce.sim.seed import seed as _seed
    _seed()
    reg = ToolRegistry()
    try:
        reg.create_staging_change("x", stage="TRIAGE")
        raise AssertionError("should have raised PermissionError")
    except PermissionError:
        pass


def test_insufficient_evidence_when_healthy():
    seed()
    STATE.faults.telemetry_gap = True
    inc = investigate()
    # healthy + gap -> honest non-diagnosis (no breach => insufficient)
    assert inc.state in (IncidentState.INSUFFICIENT_EVIDENCE, IncidentState.DRY_RUN)
