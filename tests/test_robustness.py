"""C4: determinism (50x golden), concurrency isolation, tenant scoping, metamorphic."""
import pathlib
import sqlite3
import threading

from agent.orchestrator.loop import investigate
from commerce.sim.seed import seed
from commerce.sim.state import STATE, Deploy
from commerce.sim.store import checkout as _co
from infrastructure.persistence import incidents_for, save_incident

SCHEMA = pathlib.Path("infrastructure/postgres/schema.sql").read_text()


def _inject_shipping():
    STATE.deploys.append(Deploy(deploy_id="d1", version="2.4.1", sha="s",
                                component="shipping-plugin",
                                t_offset_s=STATE.clock.offset_s))
    STATE.plugin_version = "2.4.1"
    STATE.faults.shipping_latency_ms_add = 1620.0
    _co()
    for hist, val in ((STATE.checkout_p95_hist, STATE.checkout_p95_now),
                      (STATE.conv_hist, STATE.conv_now),
                      (STATE.ship_p95_hist, STATE.ship_p95_now),
                      (STATE.pay_fail_hist, STATE.pay_fail_now)):
        hist.append(val)


def test_golden_deterministic_50_runs():
    """Same seed + same inputs x50: identical diagnosis, evidence, transitions."""
    seen = set()
    for _ in range(50):
        seed()
        _inject_shipping()
        inc = investigate()
        seen.add((inc.diagnosis.selected_hypothesis, inc.diagnosis.confidence.value,
                  inc.state.value, len(inc.evidence), len(inc.hypotheses),
                  tuple(h.name for h in inc.hypotheses)))
    assert len(seen) == 1
    assert seen.pop()[0] == "shipping_plugin_regression"


def test_concurrent_incidents_no_crosstalk():
    """10 simultaneous investigations: store_ids preserved, same verdict, no crash.

    Documents a real boundary: sim STATE is a single-process demo fixture, so
    fault setup is serialized; the investigator itself is read-only and safe
    to run concurrently (production: per-run telemetry snapshots).
    """
    seed()
    _inject_shipping()
    results, errors = [], []

    def worker(i: int):
        try:
            inc = investigate(store_id=f"store_{i % 2}")
            results.append((inc.store_id, inc.diagnosis.selected_hypothesis,
                            inc.state.value))
        except Exception as e:  # noqa: BLE001 - collected below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert len(results) == 10
    assert {s for s, _, _ in results} == {"store_0", "store_1"}
    assert {d for _, d, _ in results} == {"shipping_plugin_regression"}


def test_tenant_isolation_enforced():
    """store_A and store_B share deploy ids/product ids: reads never cross."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    save_incident(con, "inc_1", "store_A", "checkout", "DRY_RUN", "shipping_plugin")
    save_incident(con, "inc_2", "store_B", "checkout", "DRY_RUN", "payment_gateway")
    save_incident(con, "inc_3", "store_A", "payment", "RESOLVED", "pricing_bug")
    a = incidents_for(con, "store_A")
    b = incidents_for(con, "store_B")
    assert {i["incident_id"] for i in a} == {"inc_1", "inc_3"}
    assert [i["incident_id"] for i in b] == ["inc_2"]
    assert incidents_for(con, "store_C") == []


def test_metamorphic_irrelevant_changes_keep_diagnosis():
    """Renaming deploy id / reordering history must not change the verdict."""
    seed()
    _inject_shipping()
    base = investigate().diagnosis.selected_hypothesis
    # irrelevant mutation 1: deploy id renamed
    STATE.deploys[0].deploy_id = "dep_RENAMED"
    assert investigate().diagnosis.selected_hypothesis == base
    # irrelevant mutation 2: history order shuffled (same multiset of values)
    import random
    for hist in (STATE.checkout_p95_hist, STATE.conv_hist, STATE.ship_p95_hist):
        lst = list(hist)
        random.Random(0).shuffle(lst)
        hist.clear()
        hist.extend(lst)
    assert investigate().diagnosis.selected_hypothesis == base


def test_metamorphic_signal_change_flips_diagnosis():
    """Removing the ship spike must change the verdict (evidence, not luck)."""
    seed()
    _inject_shipping()
    assert investigate().diagnosis.selected_hypothesis == "shipping_plugin_regression"
    STATE.faults.shipping_latency_ms_add = 0.0
    _co()
    STATE.ship_p95_now = 200.0
    STATE.ship_p95_hist.append(200.0)
    inc2 = investigate()
    # signal gone -> either a different cause or honest no-breach (both valid flips)
    assert (inc2.diagnosis is None
            or inc2.diagnosis.selected_hypothesis != "shipping_plugin_regression")
