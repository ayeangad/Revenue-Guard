"""Hostile-review regression tests: untrusted model output + tool failure."""
from agent.orchestrator.loop import investigate
from agent.providers.llm import ALLOWED_HYPOTHESES
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co
from domain.models import IncidentState


def _inject_shipping():
    STATE.deploys.append(Deploy(deploy_id="d1", version="2.4.1", sha="s",
                                component="shipping-plugin",
                                t_offset_s=STATE.clock.offset_s))
    STATE.plugin_version = "2.4.1"
    STATE.faults.shipping_latency_ms_add = 1620.0
    _co()
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    STATE.pay_fail_hist.append(STATE.pay_fail_now)


def test_mock_names_within_allowlist():
    seed()
    _inject_shipping()
    inc = investigate()
    assert inc.diagnosis.selected_hypothesis in ALLOWED_HYPOTHESES


def test_tool_failure_degrades_to_idk_not_crash(monkeypatch):
    seed()
    _inject_shipping()
    from agent.tools import registry as regmod

    def _boom(self, stage="INVESTIGATING"):
        raise ConnectionError("dependency metrics down")
    monkeypatch.setattr(regmod.ToolRegistry, "get_dependency_health", _boom)
    inc = investigate()
    assert inc.state == IncidentState.INSUFFICIENT_EVIDENCE
    assert "tool_failure" in inc.signals


def _fake_openai_client():
    content = '[{"name": "invented_cause", "confidence": "HIGH"}]'
    msg = type("M", (), {"content": content})()
    choice = type("C", (), {"message": msg})()
    resp = type("FakeResp", (), {"choices": [choice]})()
    completions = type("Co", (), {"create": staticmethod(lambda **kw: resp)})()
    chat = type("Ch", (), {"completions": completions})()
    return type("FakeClient", (), {"chat": chat})()


def test_openai_fallback_validates_names(monkeypatch):
    from agent.providers import llm

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("openai.OpenAI", lambda: _fake_openai_client())
    p = llm.OpenAIProvider()
    out = p.rank_hypotheses(checkout_spike=True, ship_spike=True,
                            recent_deploy=True, telemetry_gap=False)
    assert all(h["name"] in ALLOWED_HYPOTHESES for h in out)
    # mock knows nothing unavailable -> still returns competing hyps
    assert len(out) >= 2
