"""Seed deterministic baselines: healthy history for detector."""
from __future__ import annotations

from commerce.sim.state import STATE


def seed(n: int = 30) -> None:
    import os
    STATE.reset()
    for _ in range(n):
        STATE.checkout_p95_now = 430 + (len(STATE.checkout_p95_hist) % 5) * 8  # ~430-462ms
        STATE.conv_now = 0.037 + (len(STATE.conv_hist) % 3) * 0.0005
        STATE.ship_p95_now = 190 + (len(STATE.ship_p95_hist) % 4) * 10
        STATE.pay_fail_now = 0.02
        STATE.cache_hit_now = 0.95
        STATE.mobile_conv_now = STATE.conv_now - 0.002
        STATE.desktop_conv_now = STATE.conv_now + 0.001
        STATE.pricing_error_now = 0.0
        STATE.checkout_p95_hist.append(STATE.checkout_p95_now)
        STATE.conv_hist.append(STATE.conv_now)
        STATE.ship_p95_hist.append(STATE.ship_p95_now)
        STATE.pay_fail_hist.append(STATE.pay_fail_now)
        STATE.clock.advance(60)
    if os.getenv("RG_QUIET") != "1":
        print(f"seeded {n} baseline points; checkout~450ms conv~3.8% ship~200ms")


if __name__ == "__main__":
    seed()
