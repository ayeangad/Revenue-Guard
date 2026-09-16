"""Simulated Woo-compatible store. Default commerce runtime for evals."""
from __future__ import annotations

import time

from fastapi import FastAPI
from pydantic import BaseModel

from commerce.sim.state import STATE

app = FastAPI(title="sim-store (Woo-shim)")


class FaultIn(BaseModel):
    shipping_latency_ms_add: float = 0.0
    db_latency_ms_add: float = 0.0
    payment_fail_rate_add: float = 0.0
    pricing_bug: bool = False
    telemetry_gap: bool = False


class DeployIn(BaseModel):
    version: str
    sha: str = "abc123"
    component: str = "shipping-plugin"


@app.get("/products")
def products():
    return {"products": [{"sku": "RING-001", "price": 84.0, "stock": 100}]}


@app.post("/cart")
def cart():
    return {"cart_id": "cart_demo", "ok": True}


@app.post("/checkout")
def checkout():
    """Transaction-style journey check: product -> cart -> checkout -> payment -> order."""
    started = time.perf_counter()
    # Deterministic latency model: baseline + injected faults
    ship = 200.0 + STATE.faults.shipping_latency_ms_add
    db = 60.0 + STATE.faults.db_latency_ms_add
    checkout_ms = 250.0 + ship * 0.6 + db * 1.5
    STATE.checkout_latency_ms = checkout_ms
    STATE.ship_p95_now = ship
    # Conversion degrades with latency (simple, explainable model)
    excess = max(0.0, checkout_ms - 500.0)
    STATE.conv_now = max(0.005, 0.038 - excess * 0.000008 - STATE.faults.payment_fail_rate_add)
    STATE.checkout_p95_now = checkout_ms
    elapsed_ms = (time.perf_counter() - started) * 1000
    ok = STATE.faults.payment_fail_rate_add < 0.5
    return {
        "journey": "checkout",
        "status": "ok" if ok else "failed",
        "duration_ms": round(checkout_ms, 1),
        "compute_ms": round(elapsed_ms, 2),
        "step": "payment" if not ok else "order_creation",
        "environment": "staging",
    }


@app.get("/metrics/checkout")
def m_checkout():
    return {
        "p95_ms": STATE.checkout_p95_now,
        "history": list(STATE.checkout_p95_hist),
        "observed_at": STATE.now().isoformat(),
    }


@app.get("/metrics/conversion")
def m_conv():
    return {
        "rate": STATE.conv_now,
        "history": list(STATE.conv_hist),
        "sessions": STATE.sessions_window,
        "aov": STATE.aov,
    }


@app.get("/metrics/dependency")
def m_dep():
    if STATE.faults.telemetry_gap:
        return {"unavailable": True}
    return {"shipping_p95_ms": STATE.ship_p95_now, "history": list(STATE.ship_p95_hist)}


@app.get("/deploys")
def deploys():
    return [
        {"deploy_id": d.deploy_id, "version": d.version, "sha": d.sha,
         "component": d.component, "t_offset_s": d.t_offset_s}
        for d in STATE.deploys
    ]


@app.post("/admin/fault")
def set_fault(f: FaultIn):
    STATE.faults.shipping_latency_ms_add = f.shipping_latency_ms_add
    STATE.faults.db_latency_ms_add = f.db_latency_ms_add
    STATE.faults.payment_fail_rate_add = f.payment_fail_rate_add
    STATE.faults.pricing_bug = f.pricing_bug
    STATE.faults.telemetry_gap = f.telemetry_gap
    # Immediately reflect in "now" signals (deterministic, no sleep)
    checkout()
    STATE.clock.advance(30)
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    return {"ok": True, "checkout_p95_ms": STATE.checkout_p95_now}


@app.post("/admin/deploy")
def deploy(d: DeployIn):
    from commerce.sim.state import Deploy
    dep = Deploy(deploy_id=f"dep_{len(STATE.deploys)+1}", version=d.version,
                 sha=d.sha, component=d.component, t_offset_s=STATE.clock.offset_s)
    STATE.deploys.append(dep)
    STATE.plugin_version = d.version
    # Golden fault coupling: shipping-plugin v2.4.1 injects shipping latency
    if d.component == "shipping-plugin" and d.version == "2.4.1":
        STATE.faults.shipping_latency_ms_add = 1620.0
        checkout()
    STATE.clock.advance(60)
    return {"deploy_id": dep.deploy_id, "version": d.version}


@app.post("/admin/rollback")
def rollback():
    STATE.plugin_version = "2.4.0"
    STATE.faults.shipping_latency_ms_add = 0.0
    checkout()
    STATE.clock.advance(60)
    STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
    STATE.conv_hist.append(STATE.conv_now)
    STATE.ship_p95_hist.append(STATE.ship_p95_now)
    return {"version": STATE.plugin_version, "checkout_p95_ms": STATE.checkout_p95_now}


@app.post("/admin/reset")
def reset():
    STATE.reset()
    return {"ok": True}


@app.get("/health")
def health():
    r = checkout()
    return {"healthy": r["status"] == "ok" and r["duration_ms"] < 1000, "journey": r}
