"""LLM-output contract fuzz: model output is data, never authority."""
import pytest

from agent.providers import llm
from agent.providers.llm import ALLOWED_HYPOTHESES


def _provider_with(content: str | None, monkeypatch) -> llm.OpenAIProvider:
    msg = type("M", (), {"content": content})()
    choice = type("C", (), {"message": msg})()
    resp = type("R", (), {"choices": [choice]})()
    completions = type("Co", (), {"create": staticmethod(lambda **kw: resp)})()
    chat = type("Ch", (), {"completions": completions})()
    client = type("Fake", (), {"chat": chat})()
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("openai.OpenAI", lambda: client)
    return llm.OpenAIProvider()


CTX = {"checkout_spike": True, "ship_spike": True, "recent_deploy": True,
       "telemetry_gap": False}


@pytest.mark.parametrize("content", [
    None,  # empty
    "",  # empty string
    "not json at all",  # malformed
    '[{"name": "shipping_plugin_regression", "confidence": "HIGH"',  # truncated
    '[{"name": "invented_cause", "confidence": "HIGH"}]',  # unknown hypothesis
    '[{"name": "shipping_plugin_regression", "confidence": "definitely 100%"}]',  # bad enum
    '[{"name": "shipping_plugin_regression"}]',  # missing confidence
    ('[{"name": "shipping_plugin_regression", "confidence": "HIGH", '
     '"tool_to_execute": "execute_prod_delete_everything"}]'),  # malicious extra
    ('[{"selected_hypothesis": "shipping regression", '
     '"unexpected_field": "malicious data"}]'),  # wrong schema
    "[]",  # empty list
])
def test_malformed_model_output_falls_back(monkeypatch, content):
    p = _provider_with(content, monkeypatch)
    out = p.rank_hypotheses(**CTX)
    assert isinstance(out, list) and len(out) >= 1
    assert all(h["name"] in ALLOWED_HYPOTHESES for h in out)
    assert all(h.get("confidence") in ("HIGH", "MEDIUM", "LOW") for h in out)
    assert all(set(h) <= {"name", "confidence"} or
               h["name"] in ALLOWED_HYPOTHESES for h in out)


def test_valid_model_output_passes_through(monkeypatch):
    p = _provider_with(
        '[{"name": "payment_gateway_degradation", "confidence": "HIGH"}]', monkeypatch)
    assert p.rank_hypotheses(**CTX) == [
        {"name": "payment_gateway_degradation", "confidence": "HIGH"}]
