# Evaluation Report (measured, reproducible)

Reproduce: `uv run python evals/runner/run.py && uv run python evals/judges/judges.py`.
Seed: `SimulationClock` T+ offsets per case; `uv.lock` + `OPENAI_MODEL` recorded.

## System performance (mock provider, deterministic sim, n=15)

- Detection accuracy: 15/15 (1.00). Caveat: mock heuristic is matched to the
  sim by construction; this measures harness correctness, not LLM brilliance.
  Real `gpt-4o-mini` expected lower — the harness exists to measure exactly that.
- False positives: 0 (`false_alarm_001` healthy -> INSUFFICIENT_EVIDENCE).
- False negatives: 0.
- Root-cause accuracy: 15/15 within `acceptable_diagnoses` (includes justified
  alternatives, e.g. `database_regression` for traffic-induced DB saturation).
- Remediation: staging rollback + synthetic validation PASS on golden path;
  prod writes 0 without approval (policy-tested).
- Mean investigation time: ~0.00s (mock, in-process); mean evidence: ~6.1/case
  (7 full / 3 IDK). Token usage: 0 mock; metered via provider when key set.
- Unsafe actions: 0/15.

## Agent quality

- Evidence selection: every diagnosis links >=6 evidence_ids (full) with
  for/against/missing split; stage-gating enforced (PermissionError tested).
- Hypothesis quality: >=2 competing hypotheses on all full investigations.

## Judge quality (who evaluates the evaluator)

- free-form vs rubric: agreement 1.00, kappa 1.00 (all-pass suite).
- rubric vs evidence-structured: kappa 1.00.
- human (6 labeled) vs rubric: agreement 0.67, kappa 0.00 — 2 DELIBERATE
  disagreements (`misleading_corr_001` vagueness, `transient_001`
  over-confidence). This is the point: the grader can be wrong
  (GRADER_FAILURE), so releases need human labels, not LLM-only gates.

## Reliability

- Idempotent stage/prod actions (double-call returns stored result).
- Rollout resume: 5-step crash at step 3 -> resume completes 5/5, 5 rows.
- Injection blocked; stale/gapped telemetry -> honest IDK.
