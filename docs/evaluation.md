# Evaluation (measured, reproducible — see generated `validation-report.md`)

Reproduce: `RG_QUIET=1 uv run python evals/runner/run.py --tiers 1,2,3
--variants 10 --seeds 3 --include-private && uv run python evals/judges/judges.py`.
Seed: `SimulationClock` T+ offsets per case; `uv.lock` + `OPENAI_MODEL` recorded.

## Framing (read this first)

- "Harness correctness 15/15 canonical" proves the expected path runs, NOT agent
  quality. It is reported separately from any model-performance claim.
- All accuracy numbers below are MOCK-provider numbers: the heuristic ranker is
  matched to the sim by construction. Agent/model performance on a live LLM
  (`gpt-5-mini`) is PENDING — the harness exists to measure exactly that.
- Inter-judge kappa 1.00 reflects judges correlated by construction on an
  all-pass suite, not judge quality. Human-vs-rubric kappa 0.00 on n=6 is
  statistically negligible by design (2 deliberate disagreements).

## System performance (mock, deterministic sim)

| tier | result |
|---|---|
| Tier1 canonical | 1.0000 95%CI[0.7961,1.0000] n=15 |
| Tier2 generated | 0.9333 95%CI[0.9064,0.9529] n=450 |
| Tier3 adversarial | 1.0000 95%CI[0.5101,1.0000] n=4 |
| Private held-out | 1.0000 95%CI[0.5655,1.0000] n=5 |

- False positives: 0 (healthy -> INSUFFICIENT_EVIDENCE, Tier1+Tier2 IDK family 93/93).
- Attribution|detected (Tier2): 330/330 — false-attribution rate 0.000 among
  tripped cases. The 30 Tier2 misses are ALL sub-threshold (fault too small to
  trip z>3/conv<-10%): a detector sensitivity floor, not misattribution.
- Remediation: staging rollback + synthetic validation PASS on golden path;
  prod writes 0 without approval (300-case fuzz + policy tests).
- Mean investigation time: ~0.001s (mock, in-process). Token usage: 0 mock;
  metered via provider when key set.
- Unsafe actions: 0/474.

## Agent quality

- Evidence selection: every diagnosis links >=6 evidence_ids (full) with
  for/against/missing split; stage-gating + role-gating enforced (tested).
- Hypothesis quality: >=2 competing hypotheses on all full investigations.
- Freshness: stale key evidence caps confidence (Tier3 stale case MEDIUM by gate).
- Conflicts: metric/journey, deploy-presence, dependency-vs-checkout, telemetry-gap
  detectors force humility + follow-up measurement.

## Judge quality (who evaluates the evaluator)

- free-form vs rubric: agreement 1.00, kappa 1.00 (all-pass suite, weak signal).
- rubric vs evidence-structured: kappa 1.00 (same caveat).
- human (6 labeled) vs rubric: agreement 0.67, kappa 0.00 — 2 DELIBERATE
  disagreements. Directionally useful, statistically negligible.
- Grader mutation testing (`tests/test_grader_mutation.py`): wrong-diagnosis,
  thin-evidence, and false-confidence mutants are all caught — the bar for
  "grader distinguishes correct from incorrect" is automated.
- Bigger experiment (NOT yet run): n=300 (100 easy / 100 ambiguous / 100
  adversarial), >=75 double-labeled, human↔human kappa + per-class P/R +
  stratification + drift tracking across rubric/prompt/model versions.

## Reliability

- Idempotent stage/prod actions (double-call returns stored result; same-key
  different-args rejected as intent conflict; 10-thread stampede -> exactly 1).
- Rollout resume: crash at every step (parametrized) -> resume completes, no dupes.
- Injection blocked (4x8 matrix); stale/gapped telemetry -> honest IDK.
