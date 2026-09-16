# Security / Threat Model

## Trust boundaries

- Merchant operator (trusted, authenticated in real deploy; demo single-user).
- Commerce content (UNTRUSTED): product names/descriptions, order notes,
  plugin changelogs. Never executed; quoted + capped at 500 chars
  (`agent/tools/sanitize.py`); injection patterns
  (`ignore previous instructions`, `approve production`, `exfiltrate`)
  -> tool call blocked with logged refusal.
- Telemetry (semi-trusted): may be stale/gapped. Freshness
  (`observed_at/collected_at/freshness_window_s`) down-weights old evidence;
  gaps -> `INSUFFICIENT_EVIDENCE`, never a confident guess.
- LLM (probabilistic, unprivileged): no direct DB/prod access; only ranks
  hypotheses via `MockProvider`/`OpenAIProvider`. All writes go through
  deterministic policy gates.

## Least privilege

`READ_METRICS/LOGS/DEPLOYS/RUN_TESTS` (triage/investigate) <
`CREATE_STAGING_CHANGE/PROPOSE_ROLLBACK` (staging only) <
`EXECUTE_PRODUCTION_ROLLBACK` (requires APPROVED approval row; enforced in
`domain/remediation.py`, tested in `tests/test_safety.py`).
MCP adapter exposes READ tools + `request_approval` intent only; staging/prod
writes are NOT callable over MCP.

## Secrets / PII

- Secrets via env (`.env`, never committed; `.env.example` only).
- All merchant data synthetic; no real PII. Multi-tenancy boundary is
  `store_id` on every incident/evidence/action row (single-store demo, but
  the column exists so per-tenant isolation is a query predicate, not a rework).

## Audit

Append-only `agent_actions` (idempotency-keyed) + `approvals` +
`validation_runs` + `investigation_runs`. Every diagnosis links
`supporting[]/contradicting[]` evidence_ids — "why did it think this" without
exposing chain-of-thought.
