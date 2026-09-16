"""Judges: free-form vs rubric vs evidence-structured + calibration (Cohen's kappa)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def rubric_judge(result: dict, spec: dict) -> bool:
    """Pass iff diagnosis in acceptable set AND evidence count >= 4 (unless IDK case)."""
    diag = result["diagnosis"]
    if diag == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE" in spec.get("acceptable_diagnoses", [])
    return diag in spec.get("acceptable_diagnoses", []) and result["evidence_n"] >= 4


def evidence_judge(result: dict, spec: dict) -> bool:
    """Stricter: also requires hypotheses_n >= 2 (competing hypotheses)."""
    return rubric_judge(result, spec) and (
        result.get("hypotheses_n", 0) >= 2 or result["diagnosis"] == "INSUFFICIENT_EVIDENCE")


RUBRIC_V1 = "rubric_v1"
RUBRIC_V2 = "rubric_v2"


def rubric_judge_v2(result: dict, spec: dict) -> bool:
    """Deliberate drift candidate: v1 + confidence required on non-IDK verdicts
    (a confident-sounding label with confidence=None must not pass)."""
    if not evidence_judge(result, spec):
        return False
    return not (result["diagnosis"] != "INSUFFICIENT_EVIDENCE"
                and not result.get("confidence"))


def freeform_judge(result: dict, spec: dict) -> bool:
    """Lenient: substring match on root cause tokens."""
    root = spec.get("root_cause", "")
    return result["diagnosis"] in spec.get("acceptable_diagnoses", []) or \
        root.split("_")[0] in result["diagnosis"]


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / max(1, n)
    pa = sum(a) / max(1, n)
    pb = sum(b) / max(1, n)
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe) if pe != 1 else 1.0, 3)


def confusion(a: list[bool]) -> dict:
    c = Counter(a)
    return {"pass": c[True], "fail": c[False]}


if __name__ == "__main__":
    import glob

    import yaml
    report = json.loads(Path("evals/reports/latest.json").read_text())
    # runner writes {"tiers": {...}}; legacy flat {"results": [...]} still accepted
    if "tiers" in report:
        t1 = report["tiers"].get("tier1_canonical", {})
        res = {r["scenario"]: r for r in t1.get("results", [])}
    else:
        res = {r["scenario"]: r for r in report["results"]}
    rows = []
    for p in sorted(glob.glob("evals/cases/*.yaml")):
        spec = yaml.safe_load(Path(p).read_text())
        r = res[spec["scenario_id"]]
        rows.append({"scenario": spec["scenario_id"],
                     "freeform": freeform_judge(r, spec),
                     "rubric": rubric_judge(r, spec),
                     "evidence": evidence_judge(r, spec)})
    f = [x["freeform"] for x in rows]
    rb = [x["rubric"] for x in rows]
    ev = [x["evidence"] for x in rows]
    v2 = []
    for p in sorted(glob.glob("evals/cases/*.yaml")):
        spec = yaml.safe_load(Path(p).read_text())
        v2.append(rubric_judge_v2(res[spec["scenario_id"]], spec))
    out = {"rows": rows,
           "rubric_v1": RUBRIC_V1, "rubric_v2": RUBRIC_V2,
           "agreement_freeform_vs_rubric": sum(x == y for x, y in zip(f, rb)) / len(rows),
           "kappa_freeform_vs_rubric": cohen_kappa(f, rb),
           "kappa_rubric_vs_evidence": cohen_kappa(rb, ev),
           "rubric_drift_v1_vs_v2": {
               "agreement": sum(x == y for x, y in zip(rb, v2)) / len(rows),
               "kappa": cohen_kappa(rb, v2),
               "changed": [r["scenario"] for r, a, b in
                           zip(rows, rb, v2) if a != b]},
           "confusion_rubric": confusion(rb)}
    # human vs judge: demonstrates the judge itself can be wrong (GRADER_FAILURE).
    # human_labels.json deliberately disagrees on 2/6 (transient over-confidence,
    # misleading vagueness) -> kappa < 1 is EXPECTED and healthy.
    try:
        human = {x["scenario"]: x["human_pass"] for x in
                 json.loads(Path("evals/calibration/human_labels.json").read_text())["labels"]}
        h, rj = [], []
        for row in rows:
            if row["scenario"] in human:
                h.append(human[row["scenario"]])
                rj.append(row["rubric"])
        out["human_vs_rubric_agreement"] = sum(x == y for x, y in zip(h, rj)) / max(1, len(h))
        out["human_vs_rubric_kappa"] = cohen_kappa(h, rj)
        out["grader_disagreements"] = [row["scenario"] for row in rows
                                       if row["scenario"] in human
                                       and human[row["scenario"]] != row["rubric"]]
    except FileNotFoundError:
        pass
    print(json.dumps(out, indent=2))
    Path("evals/reports/calibration.json").write_text(json.dumps(out, indent=2))
