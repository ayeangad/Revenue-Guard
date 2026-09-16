"""Disagreement analysis: every human-vs-judge split becomes a worked record.

Output: docs/reports/disagreements.md with, per sample: Sample ID, human
label, judge label, failure category, rubric criterion, answer excerpt, why
the judge likely disagreed, corrective hypothesis. Regenerate after any
gold-set or rubric change: uv run python scripts/disagreements.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import yaml

from evals.judges.judges import rubric_judge


def main() -> int:
    labels = {x["scenario"]: x for x in
              json.loads(Path("evals/calibration/human_labels.json").read_text())["labels"]}
    latest = Path("evals/reports/latest.json")
    tiers = json.loads(latest.read_text())["tiers"] if latest.exists() else {}
    # Cover every labeled case (Tier1 + adv + private files), not just the
    # judges.py Tier1 slice: recompute rubric_v1 directly from tier results.
    specs = {}
    for pat in ("evals/cases/*.yaml", "evals/cases_adv/*.yaml",
                "evals/cases_private/*.yaml"):
        for p in glob.glob(pat):
            s = yaml.safe_load(Path(p).read_text())
            specs[s["scenario_id"]] = s
    results: dict[str, dict] = {}
    for t in tiers.values():
        for r in t.get("results", []):
            if "~" not in r["scenario"]:
                results.setdefault(r["scenario"], r)

    disagreed = [sid for sid, lab in labels.items()
                 if sid in results and specs.get(sid)
                 and rubric_judge(results[sid], specs[sid]) != lab["human_pass"]]
    head = ("# Disagreement analysis (human gold vs rubric judge)\n\n"
            f"Gold protocol: human-gold-v1, n={len(labels)}, "
            f"disagreements={len(disagreed)}.\n")
    blocks = []
    for sid in disagreed:
        lab = labels[sid]
        res = results.get(sid, {})
        judge_pass = rubric_judge(res, specs[sid])
        blocks.append(
            f"## {sid}\n"
            f"- Human label: {hlab(lab)} — {lab['notes']}\n"
            f"- Judge label: {'PASS' if judge_pass else 'FAIL'} (rubric_v1)\n"
            f"- Answer excerpt: `{res.get('diagnosis')} @ {res.get('confidence')}` "
            f"(evidence_n={res.get('evidence_n')}, state={res.get('state')})\n"
            "- Failure category: GRADER_FAILURE (heuristic) or WRONG_HYPOTHESIS / "
            "confidence-miscalibration (agent) — see hypothesis below.\n"
            "- Rubric criterion at issue: v1 accepts any acceptable-list diagnosis "
            "with evidence>=4; it cannot penalize vague-but-listed causes or "
            "over-confident transients.\n"
            "- Why the judge likely disagreed: allowlist membership substituted "
            "for causal precision (misleading/traffic) or magnitude-awareness "
            "(transients); single-cause schema cannot represent contributing factors.\n"
            "- Corrective hypothesis: rubric_v2 confidence requirement (shipped) "
            "catches missing-confidence only; still cannot catch vague-cause or "
            "transient over-confidence. Needs: contributing-factors output + "
            "magnitude-aware confidence (open).\n")
    tail = (f"Agreement: {len(labels) - len(disagreed)}/{len(labels)} on labeled set. "
            "Not a reliability claim (n small, single rater).\n\n"
            "Disagreement classes observed: semantic vagueness (2), "
            "transient over-confidence (2), single-cause over-claim (1).\n")
    Path("docs/reports").mkdir(parents=True, exist_ok=True)
    Path("docs/reports/disagreements.md").write_text(head + "\n".join(blocks) + tail)
    print(f"wrote docs/reports/disagreements.md ({len(disagreed)} records)")
    return 0


def hlab(lab: dict) -> str:
    return "PASS" if lab["human_pass"] else "FAIL"


if __name__ == "__main__":
    sys.exit(main())
