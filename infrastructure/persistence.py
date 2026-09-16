"""SQLite-backed persistence (same DDL as Postgres schema.sql).

DESIGN CHOICE: stdlib sqlite3, no ORM — keeps MVP debuggable. Postgres in
compose uses identical tables; swap by pointing DATABASE_URL at Postgres
and applying schema.sql (psycopg path stubbed in README Future Work).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "postgres" / "schema.sql"


class IntentConflictError(ValueError):
    """Same idempotency key reused with a DIFFERENT action/target -> reject."""


def connect(path: str | None = None) -> sqlite3.Connection:
    db = path or os.getenv("RG_DB", "./revenue_guard.db")
    con = sqlite3.connect(db, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA.read_text())
    return con


def record_action(con: sqlite3.Connection, *, key: str, action: str,
                  target: str, result: str) -> tuple[dict, bool]:
    """Atomic idempotent write.

    - INSERT-first (no SELECT-then-INSERT race): concurrent duplicates collapse
      to exactly one stored side effect via the PRIMARY KEY.
    - Same key + different (action, target) -> IntentConflictError (a retry must
      repeat the same intent, never smuggle a new one under an old key).
    Returns (row, created?).
    """
    try:
        con.execute(
            "INSERT INTO agent_actions(idempotency_key, action, target, result)"
            " VALUES (?,?,?,?)", (key, action, target, result))
        con.commit()
    except sqlite3.IntegrityError:
        row = con.execute("SELECT * FROM agent_actions WHERE idempotency_key=?",
                          (key,)).fetchone()
        assert row is not None
        stored = dict(row)
        if stored["action"] != action or stored["target"] != target:
            raise IntentConflictError(
                f"key {key} bound to {stored['action']}/{stored['target']}, "
                f"refusing {action}/{target}")
        return stored, False
    return {"idempotency_key": key, "action": action, "target": target,
            "result": result}, True


def create_approval(con: sqlite3.Connection, approval_id: str,
                    incident_id: str, summary: str) -> dict:
    con.execute("INSERT INTO approvals(approval_id, incident_id, summary) VALUES (?,?,?)",
                (approval_id, incident_id, summary))
    con.commit()
    return {"approval_id": approval_id, "state": "PENDING"}


def set_approval(con: sqlite3.Connection, approval_id: str, state: str) -> None:
    assert state in ("APPROVED", "REJECTED")
    con.execute("UPDATE approvals SET state=? WHERE approval_id=?", (state, approval_id))
    con.commit()


def get_approval(con: sqlite3.Connection, approval_id: str) -> dict | None:
    row = con.execute("SELECT * FROM approvals WHERE approval_id=?",
                      (approval_id,)).fetchone()
    return dict(row) if row else None


def save_incident(con: sqlite3.Connection, incident_id: str, store_id: str,
                  journey: str, state: str, diagnosis: str = "") -> None:
    con.execute("INSERT OR REPLACE INTO incidents(incident_id, store_id, journey,"
                " state, diagnosis) VALUES (?,?,?,?,?)",
                (incident_id, store_id, journey, state, diagnosis))
    con.commit()


def incidents_for(con: sqlite3.Connection, store_id: str) -> list[dict]:
    """Tenant-scoped read: the ONLY way UI/evals list incidents (no leaks)."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM incidents WHERE store_id=?", (store_id,))]
