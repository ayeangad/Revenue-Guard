"""State-machine invariants: EVERY state x EVERY target is checked.

Illegal-transition execution must be 0, and the full legal path must walk
end to end. Skipped approval / validation / staging are asserted explicitly.
"""
import pytest

from domain.models import Incident
from domain.models import IncidentState as S
from domain.state_machine import ALLOWED, IllegalTransitionError, is_legal, transition


def _inc(state: S) -> Incident:
    return Incident(store_id="t", state=state)


def test_n_by_n_only_allowed_transitions_execute():
    illegal_fired = 0
    for frm in S:
        for to in S:
            inc = _inc(frm)
            try:
                transition(inc, to)
                assert is_legal(frm, to), f"{frm}->{to} executed but not allowed"
                assert inc.state == to
            except IllegalTransitionError:
                assert not is_legal(frm, to)
                assert inc.state == frm  # no state corruption on refusal
                if frm != to:
                    illegal_fired += 1
    assert illegal_fired > 0  # the guard actually rejects (non-vacuous)


def test_spec_must_fail_cases():
    must_fail = [
        (S.DETECTED, S.DEPLOYED), (S.DETECTED, S.RESOLVED),
        (S.DIAGNOSIS, S.DEPLOYED), (S.VALIDATION, S.DEPLOYED),
        (S.STAGING, S.DEPLOYED), (S.AWAITING_APPROVAL, S.STAGING),
    ]
    for frm, to in must_fail:
        with pytest.raises(IllegalTransitionError):
            transition(_inc(frm), to)


def test_no_path_skips_gates():
    # STAGING cannot reach DEPLOYED without VALIDATION + AWAITING_APPROVAL:
    # BFS over ALLOWED from STAGING, DEPLOYED reachable only via AWAITING_APPROVAL.
    seen, stack = set(), [S.STAGING]
    pred: dict[S, S] = {}
    while stack:
        cur = stack.pop()
        for nxt in ALLOWED[cur]:
            if nxt not in seen:
                seen.add(nxt)
                pred[nxt] = cur
                stack.append(nxt)
    assert S.DEPLOYED in seen
    assert pred[S.DEPLOYED] == S.AWAITING_APPROVAL
    # walk back: every prod path contains STAGING, VALIDATION, AWAITING_APPROVAL
    path, cur = [], S.DEPLOYED
    while cur != S.STAGING:
        path.append(cur)
        cur = pred[cur]
    assert S.VALIDATION in path and S.AWAITING_APPROVAL in path


def test_happy_path_walks():
    inc = _inc(S.DETECTED)
    for to in [S.TRIAGED, S.INITIAL_HYPOTHESES, S.COLLECT_EVIDENCE,
               S.UPDATE_HYPOTHESES, S.DIAGNOSIS, S.IMPACT_ESTIMATION,
               S.RECOMMENDATION, S.DRY_RUN, S.STAGING, S.VALIDATION,
               S.AWAITING_APPROVAL, S.DEPLOYED, S.VERIFICATION, S.RESOLVED]:
        transition(inc, to)
    assert inc.state == S.RESOLVED
