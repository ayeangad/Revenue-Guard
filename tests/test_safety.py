import sqlite3

from commerce.sim.seed import seed
from domain.remediation import execute_prod_rollback, stage_rollback
from infrastructure.persistence import connect, create_approval, set_approval


def _mem():
    import pathlib
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(pathlib.Path("infrastructure/postgres/schema.sql").read_text())
    return con


def test_idempotent_stage_no_double_apply():
    seed()
    con = _mem()
    r1, created1 = stage_rollback(con=con, idempotency_key="k1")
    r2, created2 = stage_rollback(con=con, idempotency_key="k1")
    assert created1 is True and created2 is False
    assert r1["result"] == r2["result"]


def test_prod_requires_approval():
    seed()
    con = _mem()
    a = create_approval(con, "a1", "inc_1", "rollback shipping")
    try:
        execute_prod_rollback(con=con, idempotency_key="p1", approval_id="a1")
        raise AssertionError("should refuse without approval")
    except PermissionError:
        pass
    set_approval(con, "a1", "APPROVED")
    out = execute_prod_rollback(con=con, idempotency_key="p1", approval_id="a1")
    assert out["duplicate"] is False
    out2 = execute_prod_rollback(con=con, idempotency_key="p1", approval_id="a1")
    assert out2["duplicate"] is True
    assert a["state"] == "PENDING"


def test_connect_helper():
    con = connect(":memory:")
    assert con.execute("SELECT count(*) FROM incidents").fetchone()[0] == 0
