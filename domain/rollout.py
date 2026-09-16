"""Partial-failure-safe multi-step rollout: journal each step, resume without double-apply."""
from __future__ import annotations

import json
import sqlite3


def run_rollout(*, con: sqlite3.Connection, run_id: str, steps: list[str],
                fail_at: int | None = None) -> dict:
    """Execute steps in order. fail_at injects a crash (tests). Resume by re-calling
    with same run_id: completed steps are skipped via idempotency keys."""
    from infrastructure.persistence import record_action
    done: list[str] = []
    for i, step in enumerate(steps):
        key = f"{run_id}:{step}"
        cur = con.execute("SELECT result FROM agent_actions WHERE idempotency_key=?", (key,))
        if cur.fetchone():
            done.append(step)
            continue
        if fail_at is not None and i == fail_at:
            raise RuntimeError(f"injected crash at step {step}")
        record_action(con, key=key, action="rollout_step", target=step,
                      result=json.dumps({"ok": True}))
        done.append(step)
    remaining = [s for s in steps if s not in done]
    return {"run_id": run_id, "completed": done, "remaining": remaining,
            "complete": not remaining}
