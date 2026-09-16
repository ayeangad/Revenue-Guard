# Revenue Guard Validation Report

Generated from live runs (mock provider unless noted).

## Test environment
- python 3.12, uv-locked deps, sim-store + SimulationClock, model=mock (deterministic)
- tiers: canonical(15) + generated(450) + adversarial(4) + private held-out(5)

## Safety — must be zero
| check | result |
|---|---|
| Unauthorized production actions (300-case fuzz + 574 tier runs) | 0 / 874 |
| Duplicate destructive executions (10-thread stampede + repeats) | 0 |
| Cross-tenant leaks (store_A/B/C matrix) | 0 |
| Illegal state transitions (N x N = 361 checks) | 0 |

## Reliability
| check | result |
|---|---|
| pytest | 144 passed in 1.92s |
| Golden E2E reproducibility | 50/50 identical |
| Rollout resume after crash (5 steps, fail at 3) | 5/5, 5 rows, no dupes |

## Detection & diagnosis (with uncertainty — never bare %)
| tier | accuracy |
|---|---|
| Tier1 canonical (harness correctness, NOT model quality) | 1.0000 95%CI[0.7961,1.0000] n=15 |
| Tier2 generated | 1.0000 95%CI[0.9915,1.0000] n=450 |
| Tier3 adversarial | 1.0000 95%CI[0.5101,1.0000] n=4 |
| Private held-out (never tuned to) | 1.0000 95%CI[0.9647,1.0000] n=105 |
| Abstention (IDK family Tier1) | 3/3 |
| Unsafe actions (all tiers) | 0 |

Key decomposition (Tier2, n=450): attribution|detected = 330/330
(false-attribution rate 0.000 among tripped cases); 30 sub-threshold misses
(faults too small to move the needle — detector sensitivity floor, not
misattribution). Misleading-correlation family overall 30/60 only because
half the perturbations fall below the detection threshold.

## Confidence calibration (mock; circular by construction — direction only)
HIGH/MEDIUM/LOW all 100% correct on mock. Do NOT promote to probabilities:
numeric calibration requires live-model data (Future Work).

## Judge calibration
- free-form vs rubric kappa: 1.0
- rubric vs evidence kappa: 1.0
- rubric drift v1 vs v2: agreement 1.0, kappa 1.0, changed=[]
- human gold (human-gold-v1, n=24, single rater) vs rubric: 5 worked disagreements in docs/reports/disagreements.md (vague-cause x2, transient over-confidence x2, single-cause over-claim x1). Statistically negligible; methodologically load-bearing.
- Grader mutation testing: wrong-diagnosis / thin-evidence / false-confidence mutants all caught (tests/test_grader_mutation.py).
- Metamorphic judge tests (order/verbosity/statelessness): heuristic judges invariant by construction (tests/test_judge_bias.py); live-judge protocol defined, awaiting key.
- Bigger experiment (NOT yet run): n=300 (100 easy / 100 ambiguous / 100 adversarial), >=75 double-labeled, human↔human kappa + per-class P/R + drift tracking.

## Live-model evaluation: PENDING (no key in this environment)
- Harness built and contract-tested: evals/live_eval.py conditions B (live investigator) and C (live freeform-vs-rubric judges), frozen prompts (invest_rank_v1, judge_freeform_v1, judge_rubric_v1), temperature recorded, per-call tokens/latency/cost provenance, --max-cost-usd guard, exit 3 + INVALID without key (never silent).
- First experiment pre-registered: same Tier1 gold set, mock vs gpt-4o-mini freeform vs gpt-4o-mini rubric; question: does the rubric improve evaluator agreement? No tuning until baseline is recorded.

## Failure analysis (by class)
- WRONG_HYPOTHESIS v0.1 (deploy-blame) -> dependency-first fix, verified by misleading_corr.
- BASELINE/DATA: sim-vs-wall clock mixing made all evidence stale (C4) -> single-clock rule + regression test.
- GRADER_FAILURE: deliberate human-vs-rubric disagreements; transient over-confidence accepted as known limitation (needs alert hysteresis).
- FALSE_NEGATIVE (boundary): sub-threshold faults missed — sensitivity floor documented, not hidden.

## Red team
- prompt injection: 4 payloads x 8 carriers blocked; base64 obfuscation NOT caught by regex (documented gap) but contained: untrusted text only reaches read-only args, prod needs APPROVED row.
- LLM-output fuzz (10 malformed/malicious shapes): all fall back to deterministic mock.
- Tool failure (7 tools x 3 modes): all degrade to INSUFFICIENT_EVIDENCE, none invent data.

## Known failures / remaining limitations
1. Single-cause output: multi_3way records one top hypothesis; contributing-factors output not yet implemented (trigger for specialist-agents graduation per D1).
2. Transient blips open incidents (sensitive thresholds; needs hysteresis).
3. Live-model (gpt-4o-mini) performance unmeasured: all accuracy numbers above are mock-harness numbers. Agent/model performance is PENDING live evaluation.
4. Human judge calibration n=6: directionally useful, statistically negligible.
5. Sim STATE is process-global: concurrency safety demonstrated for the read-only investigator; true multi-tenant load needs per-run snapshots (documented, store_id boundary ready).
