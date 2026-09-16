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


def connect(path: str | None = None) -> sqlite3.Connection:
    db = path or os.getenv("RG_DB", "./revenue_guard.db")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA.read_text())
    return con


def record_action(con: sqlite3.Connection, *, key: str, action: str,
                  target: str, result: str) -> tuple[dict, bool]:
    """Idempotent write. Returns (row, created?). Repeats return stored row."""
    cur = con.execute("SELECT * FROM agent_actions WHERE idempotency_key=?", (key,))
    row = cur.fetchone()
    if row:
        return dict(row), False
    con.execute(
        "INSERT INTO agent_actions(idempotency_key, action, target, result) VALUES (?,?,?,?)",
        (key, action, target, result))
    con.commit()
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
