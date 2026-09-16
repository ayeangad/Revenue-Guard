"""Quality gates: safety/determinism/honesty invariants. No arbitrary % thresholds.

Safety gates (must be 0, always):
  unauthorized prod actions, duplicate destructive side effects,
  cross-tenant leaks, illegal state transitions
Determinism gates:
  golden E2E PASS, 50x determinism (via pytest), ruff clean
Honesty gates:
  IDK-family cases must abstain (insufficient/telemetry_gap/false_alarm)
Eval-validity gates:
  every reported rate carries N + CI (runner enforces structurally)

Exit != 0 on any violation. Expensive Tier2/3 run in CI nightly, not here.
"""
from __future__ import annotations

import subprocess
import sys


def sh(*args: str) -> str:
    out = subprocess.run(args, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        print(f"GATE FAIL: {' '.join(args)}\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}")
        sys.exit(1)
    return out.stdout


def main() -> int:
    sh("uv", "run", "ruff", "check", ".")
    out = sh("uv", "run", "pytest", "-q", "-k",
             "state_invariants or idempotency or safety or hostile or attack_matrix"
             " or robustness or grader_mutation or golden or redteam")
    print([l for l in out.splitlines() if "passed" in l][-1:])
    # Tier1 + judges must run green (harness-correctness gate)
    sh("uv", "run", "python", "evals/runner/run.py", "--tiers", "1")
    sh("uv", "run", "python", "evals/judges/judges.py")
    print("QUALITY GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
