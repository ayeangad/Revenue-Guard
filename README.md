# Revenue Guard

Evidence-driven incident response for commerce. Correlates revenue-journey
telemetry with application, dependency, and deployment signals; uses an LLM
only for hypothesis generation and evidence interpretation; moves verified
remediations through deterministic staging and approval.

Independent project inspired by publicly described commerce reliability
problems. Not Urumi internals. See `docs/assumptions.md`.

## Why I Built This / Problem / Product Thesis

Uptime can be green while checkout bleeds: partial regressions (slow
checkout, payment failures, mobile-only collapse) don't trip `GET /` checks.
Vanilla Woo-MCP sees commerce data but not infra traces/deploy/staging.
Revenue Guard joins both and ranks by $ impact.

## System / Agent / Detection / Investigation / Revenue / Remediation

See `docs/architecture.md` + `docs/decisions.md`. Boring detector
(rolling z + prev-period + percentiles) -> stage-gated ToolRegistry ->
iterative hypotheses <-> evidence -> deterministic counterfactual
(`expected=sessions*baseline`, `lost=expected-observed`) -> DRY_RUN ->
staging -> validation -> approval -> symmetric verification.

## Evaluation / Failure Analysis / Red Teaming / Tradeoffs / Results

`uv run python evals/runner/run.py` runs `evals/cases/*.yaml` (golden +
misleading-correlation + insufficient-evidence). Report:
`evals/reports/latest.json`. Judge calibration + failure taxonomy land in P2.

## Running Locally

```bash
cp .env.example .env
uv sync --extra dev
uv run python commerce/sim/seed.py
uv run pytest -q
uv run python evals/runner/run.py
uvicorn apps.api.main:app --port 8000  # POST /investigate
docker compose up --build  # postgres profile
docker compose -f docker-compose.yml -f docker-compose.woo.yml up  # optional real Woo
```

## Demo (golden: bad_shipping_deploy_001)

Seed -> `POST /admin/deploy {v2.4.1}` on sim-store -> checkout p95 ~450->~1650ms,
conv 3.8%->~2.5% -> `POST /investigate` shows competing hypotheses + evidence +
counterfactual ($13k-style) + DRY_RUN -> stage -> validate -> approve -> verify PASS.

## Future Work

Postgres persistence, HTMX dashboard, 15-case suite + κ calibration,
MCP adapter, nightly Woo profile.
