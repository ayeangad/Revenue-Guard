# Demo script (3–5 min, technical credibility over polish)

Opening: "Traditional uptime can be green while checkout bleeds. Revenue Guard
joins revenue-journey telemetry with dependency + deploy signals, reasons with
evidence, and proves the fix through staging."

1. `cp .env.example .env && uv sync --extra dev && uv run python commerce/sim/seed.py`
   — healthy: checkout ~450ms, conv ~3.8%.
2. `uvicorn apps.api.main:app --port 8000` -> open `/ui` (dashboard).
3. Click "Inject bad shipping v2.4.1" (or `POST /admin/deploy` on sim-store :8001).
   Signals: checkout p95 ~450->~1650ms (+~270%), shipping ~200->~1820ms,
   conv 3.8%->~2.5%.
4. "Investigate": show competing hypotheses (shipping_plugin_regression vs
   dependency vs deploy vs traffic), linked evidence with freshness,
   confidence HIGH + breakdown (deploy strong / dependency strong /
   causal-direct weak — honest).
5. Impact: OBSERVED (orders/revenue) vs ESTIMATED COUNTERFACTUAL
   (expected 456 / observed 300 / lost 156 x $84 = $13,104-style).
6. DRY_RUN ("WOULD rollback, nothing done") -> Stage -> Validate
   (synthetic checkout PASS) -> Approve (explicit human click) -> Verify
   (same signals re-checked: 460ms / 3.7% / 190ms -> PASS -> RESOLVED).
7. `uv run python evals/runner/run.py` (15 cases) + `evals/judges/judges.py`
   (kappa incl. deliberate human disagreement) — measurement, not theatrics.
