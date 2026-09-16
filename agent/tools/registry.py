"""Stage-gated ToolRegistry. Single source of truth; MCP adapts this later."""
from __future__ import annotations

import hashlib
from datetime import datetime

from commerce.sim.state import STATE
from domain.detection import detect_checkout_regression
from domain.models import Evidence, new_id
from domain.revenue import estimate_counterfactual

STAGE_TOOLS: dict[str, set[str]] = {
    "TRIAGE": {"get_checkout_metrics", "get_conversion_metrics", "get_recent_deploys"},
    "INVESTIGATING": {
        "get_checkout_metrics", "get_conversion_metrics", "get_recent_deploys",
        "get_error_logs", "get_dependency_health", "get_diagnostics",
    },
    "IMPACT_ESTIMATION": {"estimate_revenue_impact"},
    "STAGING": {"create_staging_change"},
    "VALIDATION": {"run_validation"},
    "APPROVAL": {"request_approval"},
}


def _ev(tool: str, args: dict, claim: str, source_type: str, source_id: str,
         observed_at: datetime, reliability: str = "medium",
         obs_ids: list[str] | None = None) -> Evidence:
    from datetime import timedelta
    h = hashlib.sha256(str(sorted(args.items())).encode()).hexdigest()[:10]
    # Single-clock rule (hostile finding C4): observed and collected MUST share
    # the sim clock. Mixing sim-time observations with wall-clock collection
    # made EVERYTHING look stale. collected = observed + collector lag
    # (evidence_age_s hook simulates a laggy collector for Tier3).
    collected_at = observed_at + timedelta(seconds=STATE.evidence_age_s)
    return Evidence(
        tool_name=tool, tool_args_hash=h, extracted_claim=claim,
        source_type=source_type, source_id=source_id,
        observed_at=observed_at, collected_at=collected_at,
        freshness_window_s=300, observation_ids=obs_ids or [new_id("obs")],
        reliability=reliability,  # type: ignore[arg-type]
    )


class ToolRegistry:
    """Deterministic tools. Methods return (payload, Evidence)."""

    def __init__(self, actor: str = "operator"):
        self.actor = actor

    def allowed(self, stage: str, tool: str) -> bool:
        if stage in ("DIAGNOSIS", "RECOMMENDATION", "DRY_RUN"):
            return True  # read-only synthesis stages may cite any collected evidence
        return tool in STAGE_TOOLS.get(stage, set())

    def _guard(self, stage: str, tool: str) -> None:
        from agent.authz import authorize
        authorize(self.actor, stage)  # role gate first: anonymous/analyst contained
        if not self.allowed(stage, tool):
            raise PermissionError(f"tool {tool} not available in stage {stage}")

    def get_checkout_metrics(self, stage: str = "TRIAGE"):
        self._guard(stage, "get_checkout_metrics")
        det = detect_checkout_regression(
            list(STATE.checkout_p95_hist), STATE.checkout_p95_now,
            list(STATE.conv_hist), STATE.conv_now,
            list(STATE.ship_p95_hist), STATE.ship_p95_now)
        ev = _ev("get_checkout_metrics", {}, det.summary, "metric", "checkout_p95",
                 STATE.now(), "high")
        return {"detection": det, "p95_ms": STATE.checkout_p95_now}, ev

    def get_conversion_metrics(self, stage: str = "TRIAGE"):
        self._guard(stage, "get_conversion_metrics")
        payload = {"rate": STATE.conv_now, "sessions": STATE.sessions_window, "aov": STATE.aov}
        ev = _ev("get_conversion_metrics", {}, f"conversion={STATE.conv_now:.4f}", "metric",
                 "conversion", STATE.now(), "high")
        return payload, ev

    def get_recent_deploys(self, stage: str = "TRIAGE"):
        self._guard(stage, "get_recent_deploys")
        ds = [{"version": d.version, "component": d.component, "t": d.t_offset_s}
              for d in STATE.deploys]
        claim = f"{len(ds)} deploys; latest={ds[-1] if ds else None}"
        return {"deploys": ds}, _ev("get_recent_deploys", {}, claim, "deploy", "history",
                                    STATE.now(), "high")

    def get_error_logs(self, stage: str = "INVESTIGATING"):
        self._guard(stage, "get_error_logs")
        errs = [] if STATE.faults.payment_fail_rate_add < 0.5 else ["payment timeout x12"]
        return {"errors": errs}, _ev("get_error_logs", {}, f"errors={errs}", "log",
                                     "app_errors", STATE.now())

    def get_dependency_health(self, stage: str = "INVESTIGATING"):
        self._guard(stage, "get_dependency_health")
        if STATE.faults.telemetry_gap:
            return {"unavailable": True}, _ev(
                "get_dependency_health", {}, "dependency telemetry unavailable",
                "dependency", "shipping", STATE.now(), "low")
        payload = {"shipping_p95_ms": STATE.ship_p95_now}
        return payload, _ev("get_dependency_health", {},
                            f"shipping_p95={STATE.ship_p95_now:.0f}ms", "dependency",
                            "shipping", STATE.now(), "high")

    def get_diagnostics(self, scope: str = "slow_queries", stage: str = "INVESTIGATING"):
        self._guard(stage, "get_diagnostics")
        payload = {"scope": scope, "db_extra_ms": STATE.faults.db_latency_ms_add,
                   "note": "simulated slow-query/trace summary"}
        return payload, _ev("get_diagnostics", {"scope": scope}, str(payload), "metric",
                            f"diag_{scope}", STATE.now())

    def estimate_revenue_impact(self, stage: str = "IMPACT_ESTIMATION"):
        self._guard(stage, "estimate_revenue_impact")
        base = sum(STATE.conv_hist) / max(1, len(STATE.conv_hist)) if STATE.conv_hist else 0.038
        impact = estimate_counterfactual(STATE.sessions_window, base, STATE.conv_now, STATE.aov)
        claim = (f"expected={impact.expected_orders} observed={impact.observed_orders} "
                 f"lost={impact.lost_orders} impact=${impact.estimated_impact}")
        return {"impact": impact}, _ev("estimate_revenue_impact", {}, claim, "metric",
                                       "revenue", STATE.now(), "medium")

    def create_staging_change(self, action: str, stage: str = "STAGING"):
        self._guard(stage, "create_staging_change")
        # staging rollback in sim: deterministic
        STATE.plugin_version = "2.4.0"
        STATE.faults.shipping_latency_ms_add = 0.0
        from commerce.sim.store import checkout as _co
        _co()
        return {"dry_run": False, "staged": action, "version": STATE.plugin_version}, _ev(
            "create_staging_change", {"action": action}, f"staged {action} on STAGING",
            "deploy", "staging", STATE.now(), "high")

    def run_validation(self, stage: str = "VALIDATION"):
        self._guard(stage, "run_validation")
        from commerce.sim.store import checkout as _co
        r = _co()
        passed = r["status"] == "ok" and r["duration_ms"] < 1000
        return {"passed": passed, "journey": r}, _ev(
            "run_validation", {}, f"synthetic checkout passed={passed} "
            f"duration={r['duration_ms']}ms", "validation", "syn_checkout",
            STATE.now(), "high")

    def request_approval(self, summary: str, stage: str = "APPROVAL"):
        self._guard(stage, "request_approval")
        return {"approval_id": new_id("appr"), "state": "PENDING",
                "summary": summary}, _ev(
            "request_approval", {}, f"approval requested: {summary}", "deploy",
            "approval", STATE.now(), "high")
