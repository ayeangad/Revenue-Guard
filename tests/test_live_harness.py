"""Live-harness tests: key gate, cost math, contract validation, fake-transport E2E."""
import json

import pytest

from agent.providers.llm import ALLOWED_HYPOTHESES
from evals.live_eval import (
    JUDGE_FREEFORM,
    JUDGE_RUBRIC,
    PROMPT_V,
    RUBRIC_FREEFORM_V,
    RUBRIC_STRUCTURED_V,
    estimate_cost,
    live_judge,
    live_rank_hypotheses,
    main,
    require_key,
)


def _fake_openai(text: str, inp: int = 100, out: int = 20, monkeypatch=None):
    msg = type("M", (), {"content": text})()
    choice = type("C", (), {"message": msg})()
    usage = type("U", (), {"prompt_tokens": inp, "completion_tokens": out})()
    resp = type("R", (), {"choices": [choice], "usage": usage})()
    completions = type("Co", (), {"create": staticmethod(lambda **kw: resp)})()
    chat = type("Ch", (), {"completions": completions})()
    client = type("Fake", (), {"chat": chat})()
    if monkeypatch is not None:
        monkeypatch.setattr("openai.OpenAI", lambda: client)
    return client


CTX = {"checkout_spike": True, "ship_spike": True, "recent_deploy": True,
       "telemetry_gap": False, "payment_spike": False, "pricing_anomaly": False,
       "mobile_only": False, "db_spike": False, "cache_drop": False}


def test_missing_key_is_invalid_not_skip(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        require_key()
    assert main(["--condition", "B", "--limit", "1"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "INVALID"


def test_invalid_key_preflight_is_invalid(monkeypatch, capsys, tmp_path):
    """Well-formed but rejected key: preflight fails BEFORE any spend."""
    import evals.live_eval as le
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-INVALID")
    monkeypatch.setattr(le, "preflight_key",
                        lambda: (_ for _ in ()).throw(RuntimeError("401")))
    assert main(["--condition", "B", "--limit", "1",
                 "--out", str(tmp_path / "live.json")]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "INVALID"


def test_gpt5_omits_temperature(monkeypatch):
    """gpt-5 family rejects temperature != 1: chat() must omit it."""
    seen = {}

    def fake_create(**kw):
        seen.update(kw)
        msg = type("M", (), {"content": "hi"})()
        choice = type("C", (), {"message": msg})()
        usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 5})()
        return type("R", (), {"choices": [choice], "usage": usage})()
    completions = type("Co", (), {"create": staticmethod(fake_create)})()
    chat_ns = type("Ch", (), {"completions": completions})()
    monkeypatch.setattr("openai.OpenAI", lambda: type("F", (), {"chat": chat_ns})())
    from evals.live_eval import chat
    _, prov = chat("gpt-5-mini", [{"role": "user", "content": "x"}], 0.0, 50)
    assert "temperature" not in seen
    assert seen["max_completion_tokens"] == 50
    assert prov["temperature"] == 1.0
    _, prov = chat("gpt-4o-mini", [{"role": "user", "content": "x"}], 0.0, 50)
    assert seen["temperature"] == 0.0


def test_default_model_is_gpt5_mini():
    from evals.live_eval import DEFAULT_MODEL
    assert DEFAULT_MODEL == "gpt-5-mini"


def test_cost_math():
    assert estimate_cost("gpt-4o-mini", 1000, 1000) == pytest.approx(0.00075)
    assert estimate_cost("gpt-4o-mini", 0, 0) == 0.0


def test_live_rank_contract_validated(monkeypatch):
    _fake_openai('[{"name": "shipping_plugin_regression", "confidence": "HIGH"}]',
                 monkeypatch=monkeypatch)
    out, prov = live_rank_hypotheses(CTX, "gpt-4o-mini")
    assert out == [{"name": "shipping_plugin_regression", "confidence": "HIGH"}]
    assert prov["prompt_v"] == PROMPT_V and prov["input_tokens"] == 100
    assert prov["cost_usd"] == pytest.approx(100 / 1000 * 0.00015 + 20 / 1000 * 0.0006)


def test_live_rank_malicious_output_falls_back(monkeypatch):
    _fake_openai('[{"name": "pwned", "confidence": "HIGH", '
                 '"tool_to_execute": "rm -rf /"}]', monkeypatch=monkeypatch)
    out, prov = live_rank_hypotheses(CTX, "gpt-4o-mini")
    assert all(h["name"] in ALLOWED_HYPOTHESES for h in out)
    assert prov.get("fallback") == "contract-validation"


def test_live_judge_versions_and_schema(monkeypatch):
    _fake_openai('{"pass": true, "criterion": "correctness", "quote": "ship spike"}',
                 monkeypatch=monkeypatch)
    spec = {"acceptable_diagnoses": ["shipping_plugin_regression"]}
    res = {"diagnosis": "shipping_plugin_regression", "confidence": "HIGH",
           "evidence_n": 7, "hypotheses_n": 3}
    v, prov = live_judge(spec, res, "gpt-4o-mini", "rubric")
    assert v["pass"] is True and prov["rubric_v"] == RUBRIC_STRUCTURED_V
    _fake_openai('{"pass": false, "reason": "wrong cause"}', monkeypatch=monkeypatch)
    v, prov = live_judge(spec, res, "gpt-4o-mini", "freeform")
    assert v["pass"] is False and prov["rubric_v"] == RUBRIC_FREEFORM_V
    _fake_openai("I think it is fine, probably", monkeypatch=monkeypatch)
    v, prov = live_judge(spec, res, "gpt-4o-mini", "rubric")
    assert v["pass"] is False and prov.get("fallback") == "unparseable"


def test_prompts_frozen_and_versioned():
    assert PROMPT_V and RUBRIC_FREEFORM_V and RUBRIC_STRUCTURED_V
    assert "EXACTLY one JSON object" in JUDGE_RUBRIC
    assert "EXACTLY one JSON object" in JUDGE_FREEFORM
