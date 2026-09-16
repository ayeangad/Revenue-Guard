# Failure Analysis

Taxonomy (`domain/failures.py`): MODEL_REASONING_FAILURE, WRONG_HYPOTHESIS,
MISSING_EVIDENCE, BAD_TOOL_SELECTION, TOOL_FAILURE, OBSERVABILITY_GAP,
PROMPT_FAILURE, GRADER_FAILURE, DATA_QUALITY_FAILURE, BASELINE_FAILURE,
FALSE_POSITIVE, FALSE_NEGATIVE, INCORRECT_REMEDIATION, PARTIAL_REMEDIATION,
ROLLBACK_FAILURE.

## v0.1 -> v0.2: naive deploy-blame (WRONG_HYPOTHESIS, fixed)

- Failure: agent blamed most recent deploy on `misleading_corr_001`
  (traffic -> DB saturation with coincidental unrelated deploy).
- Contributing: no dependency-first rule; deploy correlation over-weighted.
- Fix: MockProvider reordered — payment/pricing/cohort/dependency signals
  rank before `deployment_regression`; eval gained `misleading_corr_001`.
- Result: `misleading_corr_001` now yields `database_regression`
  (accepted as justified alternative to `traffic_resource_saturation`).

## Open / accepted failures (red-team log)

- `transient_001`: brief 500ms blip still opens an incident (sensitive
  thresholds). Accepted for demo; production needs alert hysteresis.
  Human reviewer disagrees with HIGH confidence here (see calibration) —
  correct: confidence should be LOW for transients.
- `bad_rollback_001`: rollback fixes latency but pricing must NEVER be
  auto-modified (prohibited action enforced by policy, not prompt).
- Telemetry gaps: system correctly returns INSUFFICIENT_EVIDENCE; risk is
  operator fatigue if gaps are frequent — needs gap alerting (Future Work).
- Judge fallibility: human-vs-rubric kappa = 0.0 on 6 labeled cases with 2
  deliberate disagreements (GRADER_FAILURE demo). Lesson: keep human labels;
  never let a single LLM judge gate releases.
