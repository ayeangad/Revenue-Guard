"""Revenue Guard API: JSON for CLI/evals + HTMX dashboard at /ui (no build step)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from agent.orchestrator.loop import investigate
from agent.tools.registry import ToolRegistry
from commerce.sim.state import STATE, Deploy
from domain.models import IncidentState

app = FastAPI(title="revenue-guard api")
LAST: dict = {}  # last investigation (in-memory demo; Postgres in P2 stores history)

CSS = ("body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}"
       ".crit{background:#fee;border-left:4px solid #c00;padding:1rem}"
       ".ok{background:#efe;border-left:4px solid #0a0;padding:1rem}"
       "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem;text-align:left}"
       ".muted{color:#666}")


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{title}</title>"
            f"<style>{CSS}</style>"
            '<script src="https://unpkg.com/htmx.org@1.9.12"></script></head>'
            f"<body><h1>{title}</h1><p class=muted>Working on: <b>STAGING</b> "
            "(prod writes require approval)</p>" + body + "</body></html>")


def _health_block() -> str:
    return (f"<p>checkout p95 <b>{STATE.checkout_p95_now:.0f}ms</b> · "
            f"conversion <b>{STATE.conv_now:.2%}</b> · "
            f"shipping p95 <b>{STATE.ship_p95_now:.0f}ms</b> · "
            f"pay-fail <b>{STATE.pay_fail_now:.1%}</b> · "
            f"plugin <b>{STATE.plugin_version}</b></p>")


@app.get("/health")
def health():
    return {"ok": True, "plugin": STATE.plugin_version}


@app.post("/investigate")
def run_investigation():
    inc = investigate()
    LAST["inc"] = inc.model_dump(mode="json")
    return LAST["inc"]


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
    LAST["approval"] = payload
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


# ---- HTMX UI (presentation over the same deterministic endpoints) ----
@app.get("/ui", response_class=HTMLResponse)
def ui():
    inc = LAST.get("inc")
    if inc and inc.get("diagnosis"):
        d = inc["diagnosis"]
        imp = inc.get("signals", {}).get("impact", {})
        banner = (f"<div class=crit><b>CRITICAL — checkout regression</b><br>"
                  f"Likely cause: {d['selected_hypothesis']} ({d['confidence']})<br>"
                  f"Est. impact: ${imp.get('estimated_impact', '?')} "
                  f"({imp.get('lost_orders', '?')} orders)<br>"
                  f"Recommended: {inc['signals'].get('recommendation', '')}</div>")
    elif inc:
        banner = f"<div class=ok>State: {inc['state']} — no breach (honest IDK when healthy).</div>"
    else:
        banner = "<div class=ok>No investigation yet. Seed, inject, then investigate.</div>"
    deploys = "".join(f"<li>{x.version} {x.component} @T+{x.t_offset_s:.0f}s</li>"
                      for x in STATE.deploys) or "<li>none</li>"
    return _page("Revenue Guard", _health_block() + banner + (
        "<form method=post action=/ui/seed><button>1. Seed healthy</button></form> "
        "<form method=post action=/ui/inject><button>2. Inject bad shipping v2.4.1</button></form> "
        "<form method=post action=/ui/investigate><button>3. Investigate</button></form> "
        f"<h2>Deploys</h2><ul>{deploys}</ul>"
        '<p><a href="/ui/incident">Incident detail →</a> · '
        '<a href="/docs">API docs</a></p>'))


@app.post("/ui/seed")
def ui_seed():
    from commerce.sim.seed import seed as _seed
    _seed()
    LAST.clear()
    return RedirectResponse("/ui", status_code=303)


@app.post("/ui/inject")
def ui_inject():
    STATE.deploys.append(Deploy(deploy_id=f"dep_{len(STATE.deploys)+1}", version="2.4.1",
                                sha="abc123", component="shipping-plugin",
                                t_offset_s=STATE.clock.offset_s))
    STATE.plugin_version = "2.4.1"
    STATE.faults.shipping_latency_ms_add = 1620.0
    from commerce.sim.store import checkout as _co
    _co()
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    return RedirectResponse("/ui", status_code=303)


@app.post("/ui/investigate")
def ui_investigate():
    LAST["inc"] = investigate().model_dump(mode="json")
    return RedirectResponse("/ui/incident", status_code=303)


@app.get("/ui/incident", response_class=HTMLResponse)
def ui_incident():
    inc = LAST.get("inc")
    if not inc:
        return _page("Incident", "<p>No investigation yet. <a href=/ui>Back</a></p>")
    d = inc.get("diagnosis") or {}
    rows = "".join(
        f"<tr><td>{e['tool_name']}</td><td>{e['extracted_claim']}</td>"
        f"<td>{e['reliability']}</td></tr>" for e in inc.get("evidence", []))
    hyps = "".join(f"<li>{h['name']}</li>" for h in inc.get("hypotheses", [])) or "<li>—</li>"
    return _page("Incident detail", (
        f"<p>State: <b>{inc['state']}</b> · confidence: <b>{d.get('confidence', '—')}</b></p>"
        f"<p class=muted>{inc.get('signals', {}).get('summary', '')}</p>"
        f"<h2>Competing hypotheses</h2><ul>{hyps}</ul>"
        f"<h2>Evidence (provenance, no raw CoT)</h2><table>"
        "<tr><th>tool</th><th>claim</th><th>reliability</th></tr>" + rows + "</table>"
        f"<h2>Impact</h2><pre>{inc.get('signals', {}).get('impact', {})}</pre>"
        f"<p>Dry run: {inc.get('signals', {}).get('dry_run', '—')}</p>"
        "<form method=post action=/ui/stage><button>Stage rollback</button></form> "
        "<form method=post action=/ui/validate><button>Validate</button></form> "
        "<form method=post action=/ui/approve><button>Approve (human)</button></form> "
        "<form method=post action=/ui/verify><button>Verify recovery</button></form>"
        f"<p class=muted>{LAST.get('op', '')}</p><p><a href=/ui>← Dashboard</a></p>"))


@app.post("/ui/stage")
def ui_stage():
    reg = ToolRegistry()
    p, _ = reg.create_staging_change("rollback shipping-plugin v2.4.1->v2.4.0", stage="STAGING")
    LAST["op"] = f"staged: {p}"
    return RedirectResponse("/ui/incident", status_code=303)


@app.post("/ui/validate")
def ui_validate():
    reg = ToolRegistry()
    p, _ = reg.run_validation(stage="VALIDATION")
    LAST["op"] = f"validation passed={p['passed']}"
    return RedirectResponse("/ui/incident", status_code=303)


@app.post("/ui/approve")
def ui_approve():
    LAST["op"] = "APPROVED by human (simulated explicit click)"
    return RedirectResponse("/ui/incident", status_code=303)


@app.post("/ui/verify")
def ui_verify():
    reg = ToolRegistry()
    m, _ = reg.get_checkout_metrics("TRIAGE")
    LAST["op"] = f"verification {'PASS' if not m['detection'].breached else 'FAIL'}: " \
                 f"{m['detection'].summary}"
    return RedirectResponse("/ui/incident", status_code=303)
