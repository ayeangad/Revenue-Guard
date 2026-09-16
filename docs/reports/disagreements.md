# Disagreement analysis (human gold vs rubric judge)

Gold protocol: human-gold-v1, n=24, disagreements=5.
## misleading_corr_001
- Human label: FAIL — names DB location but misattributes traffic-caused saturation to the database; expect traffic_resource_saturation or contributing-factor framing. Debatable case demonstrating rubric ambiguity.
- Judge label: PASS (rubric_v1)
- Answer excerpt: `database_regression @ LOW` (evidence_n=7, state=DRY_RUN)
- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / confidence-miscalibration (agent) — see hypothesis below.
- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis with evidence>=4; it cannot penalize vague-but-listed causes or over-confident transients.
- Why the judge likely disagreed: allowlist membership substituted for causal precision (misleading/traffic) or magnitude-awareness (transients); single-cause schema cannot represent contributing factors.
- Corrective hypothesis: rubric_v2 confidence requirement (shipped) catches missing-confidence only; still cannot catch vague-cause or transient over-confidence. Needs: contributing-factors output + magnitude-aware confidence (open).

## traffic_spike_001
- Human label: FAIL — same category error as misleading_corr: traffic cause labeled as database; expect traffic framing
- Judge label: PASS (rubric_v1)
- Answer excerpt: `database_regression @ LOW` (evidence_n=7, state=DRY_RUN)
- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / confidence-miscalibration (agent) — see hypothesis below.
- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis with evidence>=4; it cannot penalize vague-but-listed causes or over-confident transients.
- Why the judge likely disagreed: allowlist membership substituted for causal precision (misleading/traffic) or magnitude-awareness (transients); single-cause schema cannot represent contributing factors.
- Corrective hypothesis: rubric_v2 confidence requirement (shipped) catches missing-confidence only; still cannot catch vague-cause or transient over-confidence. Needs: contributing-factors output + magnitude-aware confidence (open).

## transient_001
- Human label: FAIL — MEDIUM on a 500ms blip with no deploy is over-confident; expect LOW/watch. Systematic transient pattern, see also priv_transient_big_005.
- Judge label: PASS (rubric_v1)
- Answer excerpt: `shipping_dependency_degradation @ MEDIUM` (evidence_n=7, state=DRY_RUN)
- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / confidence-miscalibration (agent) — see hypothesis below.
- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis with evidence>=4; it cannot penalize vague-but-listed causes or over-confident transients.
- Why the judge likely disagreed: allowlist membership substituted for causal precision (misleading/traffic) or magnitude-awareness (transients); single-cause schema cannot represent contributing factors.
- Corrective hypothesis: rubric_v2 confidence requirement (shipped) catches missing-confidence only; still cannot catch vague-cause or transient over-confidence. Needs: contributing-factors output + magnitude-aware confidence (open).

## multi_3way_001
- Human label: FAIL — single HIGH cause on a 3-way fault over-claims; system cannot yet emit contributing factors (known limitation #1). The verdict is acceptable-adjacent but the confidence is not.
- Judge label: PASS (rubric_v1)
- Answer excerpt: `payment_gateway_degradation @ HIGH` (evidence_n=7, state=DRY_RUN)
- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / confidence-miscalibration (agent) — see hypothesis below.
- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis with evidence>=4; it cannot penalize vague-but-listed causes or over-confident transients.
- Why the judge likely disagreed: allowlist membership substituted for causal precision (misleading/traffic) or magnitude-awareness (transients); single-cause schema cannot represent contributing factors.
- Corrective hypothesis: rubric_v2 confidence requirement (shipped) catches missing-confidence only; still cannot catch vague-cause or transient over-confidence. Needs: contributing-factors output + magnitude-aware confidence (open).

## priv_transient_big_005
- Human label: FAIL — same transient over-confidence as transient_001: MEDIUM on a brief blip
- Judge label: PASS (rubric_v1)
- Answer excerpt: `shipping_dependency_degradation @ MEDIUM` (evidence_n=7, state=DRY_RUN)
- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / confidence-miscalibration (agent) — see hypothesis below.
- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis with evidence>=4; it cannot penalize vague-but-listed causes or over-confident transients.
- Why the judge likely disagreed: allowlist membership substituted for causal precision (misleading/traffic) or magnitude-awareness (transients); single-cause schema cannot represent contributing factors.
- Corrective hypothesis: rubric_v2 confidence requirement (shipped) catches missing-confidence only; still cannot catch vague-cause or transient over-confidence. Needs: contributing-factors output + magnitude-aware confidence (open).
Agreement: 19/24 on labeled set. Not a reliability claim (n small, single rater).

Disagreement classes observed: semantic vagueness (2), transient over-confidence (2), single-cause over-claim (1).
