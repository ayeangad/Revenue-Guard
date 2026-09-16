# Urumi Public Product Analysis

Rule: every claim below is Fact / Inference / Our design. No private
implementation claimed.

## What Urumi publicly confirms (Fact)

- Operations layer for WooCommerce: perf, infra, analytics, eng work
  (urumi.ai). Case studies: Do Amore ($251.5K saved, 6.1s->0.9s), grüum
  (-93% mobile load, 99.99% uptime).
- Revenue AI: catches business-logic + perf regressions in
  checkout/cart/pricing/payments, reports prioritized by $ impact, surfaces
  fix PRs (urumi.ai).
- Builder AI: NL -> tested code, staging + one-click rollback, via review
  workflow (urumi.ai).
- Platform: Dev/QA/Prod, one-click deploys, custom domains, SSH/SFTP,
  browser editor, backups, Git, cache (docs.urumi.ai).
- Urumi AI writes to Dev only; prod requires review/deploy
  (docs.urumi.ai/urumi-ai/overview). MCP: connect Claude/ChatGPT/Gemini
  with one config; zero AI markup (urumi.ai).
- FDE: client discovery -> prototype -> deploy -> iterate; prompt/tooling/
  evals/hardening; generalize to platform (urumi.ai/careers).

## What can reasonably be inferred (Inference)

- Platform value vs vanilla Woo-MCP = infra traces + deploy history +
  staging/rollback joined with commerce state (from "same store context"
  + APM traces + offending PR example).
- Recurring Slack/email $ reports imply scheduled evaluation, not
  chat-only.

## What cannot be known (Unknown)

- Internal thresholds, models, schema, MCP tool names, grading rubrics.

## Our corresponding capability (Our design)

- Revenue Guard joins sim/Woo journey telemetry + dependency + deploy
  history in one ToolRegistry; deterministic detection; LLM only for
  hypothesis/evidence; DRY_RUN -> staging -> validation -> approval ->
  symmetric verification; evals + provenance.
- Why this impl: smallest system proving the loop with measurable evals.
- Rejected: K8s, Kafka, vector DB, LangGraph-first, MCP-first, ML detector.
- Questions for an Urumi engineer: revenue-attribution formula? staging
  parity guarantees? MCP authZ model? eval rubric for Revenue AI?
