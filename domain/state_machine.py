"""Deterministic investigation state machine: explicit transitions, no skipping.

Safety property: there is NO path to DEPLOYED that bypasses STAGING ->
VALIDATION -> AWAITING_APPROVAL, and no path to a write state from a read
state except through the gated edges below. All transitions go through
`transition()`; direct `inc.state = ...` assignment is banned by convention
and flagged in review (see test_state_invariants).
"""
from __future__ import annotations

from domain.models import Incident
from domain.models import IncidentState as S

ALLOWED: dict[S, frozenset[S]] = {
    S.DETECTED: frozenset({S.TRIAGED, S.INSUFFICIENT_EVIDENCE}),
    S.TRIAGED: frozenset({S.INITIAL_HYPOTHESES, S.INSUFFICIENT_EVIDENCE}),
    S.INITIAL_HYPOTHESES: frozenset({S.COLLECT_EVIDENCE}),
    S.COLLECT_EVIDENCE: frozenset({S.UPDATE_HYPOTHESES, S.INSUFFICIENT_EVIDENCE}),
    S.UPDATE_HYPOTHESES: frozenset(
        {S.COLLECT_EVIDENCE, S.DIAGNOSIS, S.INSUFFICIENT_EVIDENCE}),
    S.DIAGNOSIS: frozenset({S.IMPACT_ESTIMATION}),
    S.IMPACT_ESTIMATION: frozenset({S.RECOMMENDATION}),
    S.RECOMMENDATION: frozenset({S.DRY_RUN}),
    S.DRY_RUN: frozenset({S.STAGING}),
    S.STAGING: frozenset({S.VALIDATION, S.TEST_FAILED}),
    S.VALIDATION: frozenset({S.AWAITING_APPROVAL, S.TEST_FAILED}),
    S.AWAITING_APPROVAL: frozenset({S.DEPLOYED, S.RECOMMENDATION}),
    S.DEPLOYED: frozenset({S.VERIFICATION, S.REGRESSION_PERSISTS}),
    S.VERIFICATION: frozenset({S.RESOLVED, S.ROLLBACK_REQUIRED}),
    # failure states may retry via STAGING; terminal otherwise
    S.TEST_FAILED: frozenset({S.STAGING}),
    S.REGRESSION_PERSISTS: frozenset({S.STAGING}),
    S.ROLLBACK_REQUIRED: frozenset({S.STAGING}),
    S.RESOLVED: frozenset(),
    S.INSUFFICIENT_EVIDENCE: frozenset(),
}


class IllegalTransitionError(ValueError):
    pass


def is_legal(frm: S, to: S) -> bool:
    return to in ALLOWED.get(frm, frozenset())


def transition(inc: Incident, to: S) -> Incident:
    if not is_legal(inc.state, to):
        raise IllegalTransitionError(f"illegal: {inc.state.value} -> {to.value}")
    inc.state = to
    return inc
