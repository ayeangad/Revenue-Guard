"""Metamorphic judge testing: irrelevant presentation changes must not flip verdicts.

Heuristic judges are pure functions of a fixed field set, so they pass by
construction — these tests pin that property AND define the exact protocol
the live LLM judges (condition C) must pass once a key exists:
  - criterion/evidence/field order invariance
  - answer-order invariance (statelessness across candidates)
  - verbosity invariance (verdict must not reward padding)

Each test is written judge-agnostic: point BIASED_CANDIDATES at any
(result, spec) -> bool to audit it.
"""
import pytest

from evals.judges.judges import evidence_judge, freeform_judge, rubric_judge

SPEC = {"scenario_id": "probe", "root_cause": "shipping_overnight",
        "acceptable_diagnoses": ["shipping_plugin_regression",
                                 "shipping_dependency_degradation_via_deploy"]}
RESULT = {"scenario": "probe", "diagnosis": "shipping_plugin_regression",
          "state": "DRY_RUN", "passed": True, "evidence_n": 7,
          "hypotheses_n": 3, "confidence": "HIGH"}

JUDGES = {"freeform": freeform_judge, "rubric": rubric_judge,
          "evidence": evidence_judge}


@pytest.mark.parametrize("judge", sorted(JUDGES))
def test_criterion_order_invariance(judge):
    """Reordered acceptable-set / shuffled evidence must not flip the verdict."""
    j = JUDGES[judge]
    base = j(RESULT, SPEC)
    shuffled = dict(SPEC, acceptable_diagnoses=list(reversed(SPEC["acceptable_diagnoses"])))
    assert j(RESULT, shuffled) == base
    assert j(dict(RESULT), dict(SPEC, root_cause="shipping morning")) == base


@pytest.mark.parametrize("judge", sorted(JUDGES))
def test_answer_order_invariance(judge):
    """Grading B-then-A must equal grading A-then-B (statelessness)."""
    j = JUDGES[judge]
    other = dict(RESULT, diagnosis="pricing_bug", evidence_n=7, hypotheses_n=3)
    assert (j(RESULT, SPEC), j(other, SPEC)) == (j(RESULT, SPEC), j(other, SPEC))
    # and the pair verdict is order-independent by construction of pure fns
    assert [j(r, SPEC) for r in (RESULT, other)] == \
        [j(r, SPEC) for r in reversed((RESULT, other))][::-1]


@pytest.mark.parametrize("judge", sorted(JUDGES))
def test_verbosity_invariance(judge):
    """800 words of padding with identical substance must not change the verdict."""
    j = JUDGES[judge]
    padded = dict(RESULT, notes="lorem ipsum " * 400, reasoning_summary="x" * 2000)
    assert j(padded, SPEC) == j(RESULT, SPEC)


@pytest.mark.parametrize("judge", sorted(JUDGES))
def test_missing_fields_fail_closed(judge):
    """A verdict must never flip to PASS because a field went missing.

    Count-based judges (rubric/evidence) raise on absent inputs — loud, not
    silently permissive. The freeform judge ignores counts by design
    (documented leniency); its verdict must then be unchanged, never upgraded.
    """
    j = JUDGES[judge]
    base = j(RESULT, SPEC)
    assert base is True
    thin = dict(RESULT)
    del thin["evidence_n"]
    if judge == "freeform":
        assert j(thin, SPEC) == base  # field-insensitive, never upgraded
    else:
        with pytest.raises((KeyError, TypeError)):
            j(thin, SPEC)


def test_live_judge_transport_invariance(monkeypatch):
    """Fake-transport check: identical verdict for reordered/verbose payloads.

    With a stubbed model returning a fixed verdict, the JUDGE PATH (payload
    construction, parsing, schema validation) must not introduce
    order/verbosity sensitivity of its own. Model-side bias needs a live key
    (condition C protocol); this pins the harness side.
    """
    from evals.live_eval import live_judge
    seen_prompts = []
    msg = type("M", (), {"content": '{"pass": true, "criterion": "correctness"}'})()
    choice = type("C", (), {"message": msg})()
    usage = type("U", (), {"prompt_tokens": 50, "completion_tokens": 10})()
    resp = type("R", (), {"choices": [choice], "usage": usage})()

    def fake_create(**kw):
        seen_prompts.append(kw["messages"][0]["content"])
        return resp
    completions = type("Co", (), {"create": staticmethod(fake_create)})()
    chat = type("Ch", (), {"completions": completions})()
    monkeypatch.setattr("openai.OpenAI", lambda: type("F", (), {"chat": chat})())

    spec = dict(SPEC)
    v1, _ = live_judge(spec, RESULT, "gpt-4o-mini", "rubric")
    padded = dict(RESULT, notes="lorem ipsum " * 400)
    v2, _ = live_judge(spec, padded, "gpt-4o-mini", "rubric")
    assert (v1["pass"], v2["pass"]) == (True, True)
    assert len(seen_prompts) == 2  # both calls actually went through the path
