"""Role-based tool authorization. The model is persuasive; the policy is not.

Matrix:
  anonymous: nothing (not even reads — no authenticated principal)
  analyst:   read-only (triage/investigate/impact stages)
  operator:  everything except prod execution
  approved:  operator + APPROVED approval row -> prod execution allowed

Prod execution ALSO requires the approval-row check in domain/remediation
(defense in depth: registry gate + persistence gate).
"""
from __future__ import annotations

READ_STAGES = frozenset({"TRIAGE", "INVESTIGATING", "IMPACT_ESTIMATION"})
WRITE_STAGES = frozenset({"STAGING", "VALIDATION", "APPROVAL"})
ROLES = ("anonymous", "analyst", "operator", "approved")


class AuthorizationError(PermissionError):
    pass


def authorize(actor: str, stage: str) -> None:
    if actor not in ROLES:
        raise AuthorizationError(f"unknown actor {actor!r}")
    if actor == "anonymous":
        raise AuthorizationError("anonymous: no tool access")
    if actor == "analyst" and stage not in READ_STAGES:
        raise AuthorizationError(f"analyst: stage {stage} is not read-only")
    if stage not in READ_STAGES | WRITE_STAGES and stage not in (
            "DIAGNOSIS", "RECOMMENDATION", "DRY_RUN"):
        raise AuthorizationError(f"unknown stage {stage!r}")
    # operator/approved may use any gated stage; prod execution is separately
    # gated on an APPROVED approval row (domain/remediation).
