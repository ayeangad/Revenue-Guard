# Decisions (GLOBAL DECISION POLICY applied)

Format per decision: problem / assumptions / approaches / simplest /
most-scalable / safest / tradeoffs / choice / why / how tested / flip signal.

## D1. Agent architecture: deterministic engine + LLM at decision points (chosen)

- Problem: need reliable incident response, not chatbot theatrics.
- Assumes: faults are partially observable via metrics/deploys/deps.
- Approaches: (A) single agent + tools, (B) planner + specialists,
  (C) deterministic engine + LLM analyst, (D) event workflow + LLM gates.
- Simplest: A. Scalable: B. Safest: C/D.
- Choice: D-variant (this repo). LLM never computes truth.
- Tested by: golden scenario + misleading-correlation benchmark
  (naive "recent deploy did it" must fail without dependency evidence).
- Flip if: concurrent multi-fault evals need parallel specialists -> add B
  behind same state machine.

## D2. Anomaly: boring rolling z-score + prev-period + percentiles (chosen)

- Rejects ML detector (opaque, data-hungry). Outputs
  `baseline/current/deviation%`, explainable.
- Tested by: detection accuracy + FP rate on 15-case suite.
- Flip if: seasonality dominates -> add time-of-day baseline (still deterministic).

## D3. Revenue: counterfactual, observed vs estimated split (chosen)

- `expected = sessions * baseline_conv; lost = expected - observed;
  impact = lost * AOV`. Labels OBSERVED vs ESTIMATED COUNTERFACTUAL.
  Refuses (`cannot be estimated reliably`) when telemetry gaps.
- Tested by: revenue-error metric on evals with known ground truth.
- Flip if: cohort-level AOV variance high -> per-cohort AOV.

## D4. Confidence: HIGH/MEDIUM/LOW + decomposition (chosen)

- Rejects naked 0.82 (uncalibrated). Breakdown:
  deploy_corr / dependency_corr / cohort_match / causal_direct.
- Numeric only after calibration demonstrates it. Tested by judge calibration.

## D5. Storage: Postgres required, SQLite fallback, Redis optional (chosen)

- Postgres for record; SQLite for `uv run pytest` speed; Redis only when
  ephemeral locks/rate-limit measured. Rejects Redis-as-required.
- Tested by: `DATABASE_URL` switch in CI.

## D6. Commerce: hybrid sim-default + woo-optional (chosen)

- Sim gives determinism + speed; Woo proves real integration (4 checks only).
- Tested by: sim suite always; Woo profile in nightly/manual.

## D7. Tools: 10 typed, stage-gated; MCP adapter later (chosen)

- Rejects giant tool belt (bad selection) and MCP-first (protocol cost).
- Tested by: bad-tool-selection failure rate; MCP compat smoke test.

## D8. Frontend: FastAPI + HTMX/Tailwind, CLI/API first (chosen)

- Rejects Next.js for MVP (toolchain cost). Dashboard only after CLI golden
  path passes. Tested by: golden CLI E2E before any HTMX work.
