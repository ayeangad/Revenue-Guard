"""Failure taxonomy: WHY the agent got it wrong (not just THAT it did)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class FailureClass(str, Enum):
    MODEL_REASONING_FAILURE = "MODEL_REASONING_FAILURE"
    WRONG_HYPOTHESIS = "WRONG_HYPOTHESIS"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    BAD_TOOL_SELECTION = "BAD_TOOL_SELECTION"
    TOOL_FAILURE = "TOOL_FAILURE"
    OBSERVABILITY_GAP = "OBSERVABILITY_GAP"
    PROMPT_FAILURE = "PROMPT_FAILURE"
    GRADER_FAILURE = "GRADER_FAILURE"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    BASELINE_FAILURE = "BASELINE_FAILURE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    FALSE_NEGATIVE = "FALSE_NEGATIVE"
    INCORRECT_REMEDIATION = "INCORRECT_REMEDIATION"
    PARTIAL_REMEDIATION = "PARTIAL_REMEDIATION"
    ROLLBACK_FAILURE = "ROLLBACK_FAILURE"


def classify(m: dict) -> str:
    """Heuristic classifier for failed runs (deterministic, auditable)."""
    if m.get("state") == "INSUFFICIENT_EVIDENCE" and m.get("scenario") not in (
            "insufficient_evidence_001", "telemetry_gap_001", "false_alarm_001"):
        return FailureClass.FALSE_NEGATIVE.value
    if m.get("scenario") == "false_alarm_001" and m.get("state") != "INSUFFICIENT_EVIDENCE":
        return FailureClass.FALSE_POSITIVE.value
    if m.get("evidence_n", 0) < 4:
        return FailureClass.MISSING_EVIDENCE.value
    return FailureClass.WRONG_HYPOTHESIS.value


class FailureRecord(BaseModel):
    """Causal record rule: a category WITHOUT evidence is incomplete.

    Every entry must cite the exact observation that justifies the category
    (expected X, observed Y, therefore Z) — never a bare label.
    """

    scenario: str
    category: FailureClass
    evidence: str
    impact: str = ""
    fix: str = ""
    status: str = "open"  # open | fixed-verified | accepted-limitation
