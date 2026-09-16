# Assumptions

Labels: CONFIRMED FROM PUBLIC URUMI MATERIAL | PROJECT ASSUMPTION |
DESIGN CHOICE | OPEN QUESTION.

- CONFIRMED: Urumi ships Dev/QA/Prod envs, one-click deploys, AI operates on
  Dev only, `Working on: Dev` indicator, review before prod
  (source: docs.urumi.ai Urumi AI Overview).
- CONFIRMED: Three AIs — Revenue (checkout/cart/pricing/payment regressions,
  $ impact reports), Builder (NL -> code via review pipeline, staging+rollback),
  Analytics (NL queries) + MCP BYO-AI (source: urumi.ai homepage/blog).
- CONFIRMED: FDE role = discover pain, prototype, deploy, iterate to autonomy,
  eval harnesses, production hardening, generalize to platform
  (source: urumi.ai/careers).
- PROJECT ASSUMPTION: merchants care about lost orders first, raw infra
  metrics second (drives UX order: impact -> journey -> evidence).
- PROJECT ASSUMPTION: partial regressions (slow checkout, payment fail rise,
  mobile-only) dominate over full outages for revenue loss.
- DESIGN CHOICE: GPT-4o-mini with mock provider for offline CI.
- DESIGN CHOICE: SQLite fallback locally; Postgres in compose.
- OPEN QUESTION: real Urumi detection thresholds / grading rubrics — unknown,
  we define our own transparent baselines.
- OPEN QUESTION: actual Urumi MCP tool surface — we expose our own minimal
  read-first subset; compat, not parity, claimed.
