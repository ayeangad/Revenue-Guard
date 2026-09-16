"""First-class domain models: evidence, diagnosis, incident, scenario."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INITIAL_HYPOTHESES = "INITIAL_HYPOTHESES"
    COLLECT_EVIDENCE = "COLLECT_EVIDENCE"
    UPDATE_HYPOTHESES = "UPDATE_HYPOTHESES"
    DIAGNOSIS = "DIAGNOSIS"
    IMPACT_ESTIMATION = "IMPACT_ESTIMATION"
    RECOMMENDATION = "RECOMMENDATION"
    DRY_RUN = "DRY_RUN"
    STAGING = "STAGING"
    VALIDATION = "VALIDATION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DEPLOYED = "DEPLOYED"
    VERIFICATION = "VERIFICATION"
    RESOLVED = "RESOLVED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TEST_FAILED = "TEST_FAILED"
    REGRESSION_PERSISTS = "REGRESSION_PERSISTS"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    source_type: str  # metric | log | deploy | dependency | validation
    source_id: str
    tool_name: str
    tool_args_hash: str = ""
    observed_at: datetime
    collected_at: datetime
    freshness_window_s: int = 300
    observation_ids: list[str] = Field(default_factory=list)
    extracted_claim: str
    reliability: Literal["high", "medium", "low"] = "medium"

    def freshness_age_s(self) -> float:
        return (self.collected_at - self.observed_at).total_seconds()


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(default_factory=lambda: new_id("hyp"))
    name: str
    supporting: list[str] = Field(default_factory=list)  # evidence_ids
    contradicting: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    selected_hypothesis: str
    confidence: Confidence
    breakdown: dict[str, str] = Field(default_factory=dict)
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reasoning_summary: str


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: new_id("inc"))
    store_id: str = "demo-store"
    journey: str = "checkout"
    state: IncidentState = IncidentState.DETECTED
    started_at: datetime | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None


class Scenario(BaseModel):
    """Ground-truth scenario definition (see commerce/scenarios/*.yaml)."""

    scenario_id: str
    root_cause: str
    causal_chain: list[str]
    acceptable_diagnoses: list[str]
    prohibited_actions: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    timeline: dict[str, float] = Field(default_factory=dict)  # event -> T+ seconds
