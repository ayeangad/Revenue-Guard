"""Benchmark contamination audit + eval-validity invariant.

The investigator must decide from telemetry signals alone. Spec text
(scenario ids, acceptable diagnoses, yaml) must not reach the decision path:
same signals + different scenario_id -> same verdict, and no spec vocabulary
is imported anywhere under agent/.
"""
import pathlib

from agent.orchestrator.loop import investigate
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co


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


def test_scenario_id_does_not_change_verdict():
    """'adversarial' wording / ids must not leak into decisions."""
    seed()
    _inject_shipping()
    a = investigate(scenario_id="bad_shipping_deploy_001")
    seed()
    _inject_shipping()
    b = investigate(scenario_id="adversarial_trick_999_totaly_different")
    assert a.diagnosis.selected_hypothesis == b.diagnosis.selected_hypothesis
    assert a.diagnosis.confidence == b.diagnosis.confidence
    assert [h.name for h in a.hypotheses] == [h.name for h in b.hypotheses]


def test_agent_imports_no_spec_vocabulary():
    """Static audit: agent/ must not read yaml specs or grading keys."""
    banned = ("acceptable_diagnoses", "yaml.safe_load", "cases_adv",
              "cases_private", "human_labels")
    hits = [str(p) for p in pathlib.Path("agent").rglob("*.py")
            if any(b in p.read_text() for b in banned)]
    assert hits == [], f"spec leakage into agent/: {hits}"


def test_validity_status_complete(tmp_path):
    """Runner emits expected/observed/status; mismatch is INVALID, never green."""
    import json

    from evals.runner.run import main
    out = tmp_path / "r.json"
    assert main(["--tiers", "1", "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert rep["status"] == "COMPLETE"
    t1 = rep["tiers"]["tier1_canonical"]
    assert t1["status"] == "COMPLETE" and t1["expected"] == t1["observed"] == 15
