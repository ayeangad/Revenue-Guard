# Revenue Guard — Architecture

> Evidence-driven incident response for commerce. Correlates revenue-journey
> telemetry with application, dependency, and deployment signals; uses an LLM
> only for hypothesis generation and evidence interpretation; moves verified
> remediations through deterministic staging and approval.

## Locked flow

```
Commerce runtime
  -> Deterministic telemetry
  -> Deterministic incident detection
  -> Typed investigation tools (stage-gated ToolRegistry)
  -> LLM hypothesis / evidence reasoning
  -> Deterministic diagnosis record
  -> Deterministic impact calculation (counterfactual)
  -> LLM-assisted remediation proposal
  -> Policy engine + DRY_RUN
  -> Staging -> Deterministic validation
  -> Human approval -> Production
  -> Deterministic verification (symmetric signals)
  -> Evaluation + provenance
```

Non-negotiable loop: `Detect -> Investigate -> Explain -> Quantify -> Stage -> Validate -> Approve -> Deploy -> Verify`.

## Investigation state machine (iterative, deterministic)

```
DETECTED -> TRIAGED -> INITIAL_HYPOTHESES ⇄ COLLECT_EVIDENCE ⇄ UPDATE_HYPOTHESES
  -> DIAGNOSIS -> IMPACT_ESTIMATION -> RECOMMENDATION -> DRY_RUN -> STAGING
  -> VALIDATION -> AWAITING_APPROVAL -> DEPLOYED -> VERIFICATION -> RESOLVED
```

Failure edges: `-> INSUFFICIENT_EVIDENCE`, `STAGING -> TEST_FAILED`,
`DEPLOYED -> REGRESSION_PERSISTS`, `VERIFICATION -> ROLLBACK_REQUIRED`.
All transitions persisted; LLM only selects `next_evidence_action`.

## Stage-gated tools (ToolRegistry is source of truth)

- TRIAGE: `get_checkout_metrics`, `get_conversion_metrics`, `get_recent_deploys`
- INVESTIGATING: `+ get_error_logs`, `get_dependency_health`, `get_diagnostics`
  (`get_diagnostics` merges slow-queries + trace; split only if eval demands it)
- IMPACT: `+ estimate_revenue_impact` (deterministic; LLM narrates only)
- STAGING: `+ create_staging_change` (after DRY_RUN)
- VALIDATION: `+ run_validation`
- APPROVAL/PROD: `+ request_approval` / policy-gated execute

MCP is a thin adapter over the same registry:
`Registry -> {Agent Runtime, MCP Server}`. Agent never depends on MCP.

## Evidence-first provenance (no raw CoT in UI)

`Evidence{evidence_id, source_type, source_id, tool_name, tool_args_hash,
observed_at, collected_at, freshness_window_s, observation_ids,
extracted_claim, reliability}`.

`Diagnosis{selected_hypothesis, confidence_level HIGH/MEDIUM/LOW,
breakdown{deploy_corr, dependency_corr, cohort_match, causal_direct},
supporting[], contradicting[], missing[], reasoning_summary}`.

## Deterministic vs LLM split ("LLM for reasoning, code for truth")

Code owns: timestamps, metrics/percentiles, baselines, incident creation,
transitions, authZ, idempotency, validation verdict, rollback exec, revenue math.
LLM (GPT-4o-mini, mockable) owns: hypothesis gen/compare, evidence
interpretation, next-step selection, synthesis, merchant explanation.

## Commerce

Hybrid: `commerce/sim` (FastAPI Woo-shim, default, boots in seconds,
deterministic faults) + `commerce/woo` (optional profile
`docker-compose.woo.yml`, proves real API + 1 injected fault only).
Both emit identical `CommerceEvent`. `SimulationClock` (T+ offsets) makes
scenarios repeatable; wall-clock never used in evals.

## Storage

Postgres is system of record (required in compose); SQLite file is local
dev fallback via `DATABASE_URL`. Redis is optional (ephemeral locks/rate
limit only, not required to boot).
