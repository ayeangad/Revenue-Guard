"""Revenue Guard API (FastAPI + HTMX later; JSON first for CLI golden path)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from agent.orchestrator.loop import investigate
from agent.tools.registry import ToolRegistry
from commerce.sim.state import STATE
from domain.models import IncidentState

app = FastAPI(title="revenue-guard api")


@app.get("/health")
def health():
    return {"ok": True, "plugin": STATE.plugin_version}


@app.post("/investigate")
def run_investigation():
    inc = investigate()
    return inc.model_dump(mode="json")


@app.post("/remediate/stage")
def stage(action: str = "rollback shipping-plugin v2.4.1->v2.4.0"):
    reg = ToolRegistry()
    payload, ev = reg.create_staging_change(action, stage="STAGING")
    return {**payload, "evidence_id": ev.evidence_id}


@app.post("/remediate/validate")
def validate():
    reg = ToolRegistry()
    payload, ev = reg.run_validation(stage="VALIDATION")
    if not payload["passed"]:
        raise HTTPException(500, "validation failed")
    return {**payload, "evidence_id": ev.evidence_id}


@app.post("/remediate/approve")
def approve(summary: str = "rollback shipping-plugin"):
    reg = ToolRegistry()
    payload, ev = reg.request_approval(summary, stage="APPROVAL")
    # MVP: auto-mark approved for demo only after explicit call (human gate simulated)
    payload["state"] = "APPROVED"
    return {**payload, "evidence_id": ev.evidence_id}


@app.post("/remediate/verify")
def verify():
    """Symmetric verification: re-check the same signals that fired the incident."""
    reg = ToolRegistry()
    m, _ = reg.get_checkout_metrics("TRIAGE")
    det = m["detection"]
    recovered = not det.breached
    return {"verification": "PASS" if recovered else "FAIL", "summary": det.summary,
            "state": IncidentState.RESOLVED if recovered else IncidentState.REGRESSION_PERSISTS}
