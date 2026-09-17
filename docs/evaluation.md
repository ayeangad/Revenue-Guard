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
| Tier2 generated | 1.0000 95%CI[0.9915,1.0000] n=450 |
| Tier3 adversarial | 1.0000 95%CI[0.5101,1.0000] n=4 |
| Private held-out (5 files + 100 quarantined) | 1.0000 95%CI[0.9647,1.0000] n=105 |

- False positives: 0 (healthy -> INSUFFICIENT_EVIDENCE, IDK family 93/93 Tier1+2).
- Attribution|detected (Tier2): 360/360 — false-attribution rate 0.000 among
  tripped cases. (A previous "30 sub-threshold misses" reading was retracted:
  it was a benchmark bug — faults never injected under perturbed ids. See
  failure-analysis #6. The corrected sensitivity probe shows the detector
  trips even at +20ms DB fault: over-sensitivity on noisy baselines, not
  misses, is the real boundary risk.)
- Remediation: staging rollback + synthetic validation PASS on golden path;
  prod writes 0 without approval (300-case fuzz + policy tests).
- Mean investigation time: ~0.001s (mock, in-process); ~11s/call live
  (gpt-5-mini reasoning). Token usage: 0 mock; metered per call live.
- Unsafe actions: 0/574.

## Live model (gpt-5-mini, condition C, Tier1 n=15, $0.084, REAL DATA)

- Investigator: 14/15 (only `multi_fault_001` wrong — live deploy-blame the
  mock avoids; golden path shows finer nuance than mock: via_deploy variant).
- Freeform judge: 15/15 agreement with heuristic — mirrors it exactly,
  discriminates nothing beyond it (vacuous leniency documented, not celebrated).
- Rubric judge: 3/15 — systematically fails on `humility`, demanding LOW
  confidence even with complete evidence. rubric_v1 recorded as
  unusable-as-shipped; rewording hypothesized but NOT applied (frozen protocol).
- Human gold (n=15 Tier1 slice): vs heuristic 11/15, vs freeform 11/15,
  vs rubric 5/15. Direction only (single rater).
- Validity: 0 fallbacks, 0 transport losses, prompts frozen, spend capped.

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
