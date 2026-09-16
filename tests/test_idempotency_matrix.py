"""Idempotency attack suite: repeats, intent conflicts, 10-thread stampede."""
import pathlib
import sqlite3
import threading

import pytest

from domain.remediation import execute_prod_rollback
from infrastructure.persistence import (
    IntentConflictError,
    connect,
    create_approval,
    record_action,
    set_approval,
)

SCHEMA = pathlib.Path("infrastructure/postgres/schema.sql").read_text()


def _mem():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def test_triple_execute_single_side_effect():
    con = _mem()
    r1, c1 = record_action(con, key="ABC", action="rollback", target="ship:2.4.1->2.4.0",
                           result="ok")
    r2, c2 = record_action(con, key="ABC", action="rollback", target="ship:2.4.1->2.4.0",
                           result="ok")
    r3, c3 = record_action(con, key="ABC", action="rollback", target="ship:2.4.1->2.4.0",
                           result="ok")
    assert (c1, c2, c3) == (True, False, False)
    key = lambda r: (r["action"], r["target"], r["result"])
    assert key(r1) == key(r2) == key(r3)
    assert con.execute("SELECT count(*) FROM agent_actions").fetchone()[0] == 1


def test_same_key_different_args_rejected():
    con = _mem()
    record_action(con, key="ABC", action="rollback", target="ship:2.4.1->2.4.0", result="ok")
    with pytest.raises(IntentConflictError):
        record_action(con, key="ABC", action="rollback", target="ship:2.4.1->2.3.9",
                      result="ok")
    with pytest.raises(IntentConflictError):
        record_action(con, key="ABC", action="config_change", target="ship:2.4.1->2.4.0",
                      result="ok")


def test_ten_workers_one_side_effect(tmp_path):
    db = str(tmp_path / "race.db")
    connect(db).close()
    created, errors = [], []

    def worker():
        try:
            con = sqlite3.connect(db, timeout=30.0)
            con.row_factory = sqlite3.Row
            _, c = record_action(con, key="STAMPEDE", action="rollback",
                                 target="ship:2.4.1->2.4.0", result="ok")
            created.append(c)
            con.close()
        except Exception as e:  # noqa: BLE001 - collected, asserted below
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert sum(created) == 1  # exactly one side effect
    assert len(created) == 10  # all got deterministic replay


def test_safety_fuzz_no_unapproved_prod(tmp_path):
    """Fuzz approval states x keys: prod succeeds ONLY with APPROVED."""
    import random
    rng = random.Random(2026)
    violations = 0
    trials = 0
    for i in range(300):
        con = _mem()
        aid = f"a{i}"
        state = rng.choice(["PENDING", "APPROVED", "REJECTED", None, "approved", ""])
        if state in ("PENDING", "APPROVED", "REJECTED"):
            create_approval(con, aid, "inc", "rollback")
            if state != "PENDING":
                set_approval(con, aid, state)
        key = f"k{rng.choice([1, 1, 2])}"  # force key reuse
        trials += 1
        try:
            execute_prod_rollback(con=con, idempotency_key=key, approval_id=aid)
            appr = con.execute("SELECT state FROM approvals WHERE approval_id=?",
                               (aid,)).fetchone()
            if appr is None or appr[0] != "APPROVED":
                violations += 1
        except (PermissionError, IntentConflictError):
            pass
    assert trials == 300
    assert violations == 0
