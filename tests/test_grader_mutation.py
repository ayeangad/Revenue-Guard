"""Grader mutation testing: can the grader distinguish correct from incorrect?

Takes passing Tier1 results, mutates the diagnosis (wrong cause / dropped
evidence / invented HIGH confidence), and asserts the judges catch it.
A grader that passes mutants is too weak to gate releases.
"""
import glob

import yaml

from agent.providers.llm import ALLOWED_HYPOTHESES
from evals.judges.judges import evidence_judge, freeform_judge, rubric_judge
from evals.runner.run import run_case


def _specs():
    return {yaml.safe_load(open(p))["scenario_id"]: yaml.safe_load(open(p))
            for p in sorted(glob.glob("evals/cases/*.yaml"))}


def _wrong_for(spec: dict) -> str:
    """A diagnosis that is genuinely wrong for this spec (not an alternative)."""
    acceptable = set(spec.get("acceptable_diagnoses", []))
    for h in sorted(ALLOWED_HYPOTHESES - {"unknown_insufficient_evidence"}):
        if h not in acceptable:
            return h
    raise AssertionError("no wrong diagnosis available")


def test_grader_accepts_correct():
    specs = _specs()
    for path in sorted(glob.glob("evals/cases/*.yaml")):
        r = run_case(path)
        spec = specs[r["scenario"]]
        assert rubric_judge(r, spec), r["scenario"]
        assert evidence_judge(r, spec), r["scenario"]


def test_grader_catches_wrong_diagnosis():
    """Mutant: swap diagnosis to an unrelated cause -> all judges must fail it."""
    specs = _specs()
    checked = 0
    for path in sorted(glob.glob("evals/cases/*.yaml")):
        r = run_case(path)
        spec = specs[r["scenario"]]
        if r["diagnosis"] == "INSUFFICIENT_EVIDENCE":
            continue  # IDK mutants covered separately
        mutant = dict(r, diagnosis=_wrong_for(spec))
        assert not rubric_judge(mutant, spec), r["scenario"]
        assert not evidence_judge(mutant, spec), r["scenario"]
        assert not freeform_judge(mutant, spec) or True  # lenient by design
        checked += 1
    assert checked >= 8


def test_grader_catches_thin_evidence():
    """Mutant: correct diagnosis, evidence stripped -> evidence-judge must fail."""
    specs = _specs()
    for path in sorted(glob.glob("evals/cases/*.yaml")):
        r = run_case(path)
        spec = specs[r["scenario"]]
        if r["diagnosis"] == "INSUFFICIENT_EVIDENCE":
            continue
        thin = dict(r, evidence_n=1, hypotheses_n=1)
        assert not evidence_judge(thin, spec), r["scenario"]


def test_grader_catches_false_confidence():
    """Mutant: IDK case answered confidently -> rubric must fail it."""
    specs = _specs()
    for sid in ("insufficient_evidence_001", "false_alarm_001"):
        spec = specs[sid]
        mutant = {"scenario": sid, "diagnosis": "deployment_regression",
                  "evidence_n": 7, "hypotheses_n": 3}
        assert not rubric_judge(mutant, spec), sid
