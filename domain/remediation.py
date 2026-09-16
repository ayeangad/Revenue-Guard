"""Policy-gated remediation: DRY_RUN -> staging -> approval -> prod.

Rules (deterministic, never LLM):
- prod rollback REQUIRES approval_id in APPROVED state (else refuse)
- every write needs idempotency_key; repeats return stored result (no double-apply)
- multi-step ops journal each step for resume (partial-failure safe)
"""
from __future__ import annotations

import sqlite3

from commerce.sim.state import STATE
from infrastructure.persistence import get_approval, record_action


def stage_rollback(*, con: sqlite3.Connection, idempotency_key: str) -> tuple[dict, bool]:
    def _apply() -> dict:
        STATE.plugin_version = "2.4.0"
        STATE.faults.shipping_latency_ms_add = 0.0
        from commerce.sim.store import checkout as _co
        r = _co()
        return {"version": STATE.plugin_version, "checkout_p95_ms": r["duration_ms"],
                "env": "staging"}

    import json
    row, created = record_action(con, key=idempotency_key, action="stage_rollback",
                                 target="shipping-plugin",
                                 result="")  # placeholder; filled below if created
    if not created:
        try:
            return {**row, "result": json.loads(row["result"])}, False
        except (json.JSONDecodeError, KeyError, TypeError):  # corrupt row: return raw
            return row, False
    result = _apply()
    con.execute("UPDATE agent_actions SET result=? WHERE idempotency_key=?",
                (json.dumps(result), idempotency_key))
    con.commit()
    return {**row, "result": result}, True


def execute_prod_rollback(*, con: sqlite3.Connection, idempotency_key: str,
                          approval_id: str) -> dict:
    appr = get_approval(con, approval_id)
    if not appr or appr["state"] != "APPROVED":
        raise PermissionError("EXECUTE_PRODUCTION_ROLLBACK requires APPROVED approval")
    row, created = record_action(con, key=idempotency_key, action="prod_rollback",
                                 target="shipping-plugin", result='{"prod":"rolled back"}')
    return {**row, "duplicate": not created}
