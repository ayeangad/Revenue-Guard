"""Live-model evaluation harness: GPT-5-mini as investigator + judge.

Design (frozen before first run — no optimizing to the test set):
  Condition A: mock investigator + heuristic judges (harness correctness)
  Condition B: live investigator + heuristic judges (model reasoning quality)
  Condition C: live investigator + live LLM judges, freeform vs rubric
               (evaluator agreement experiment)

Key-gated: without a WORKING OPENAI_API_KEY every entrypoint exits status 3
with status=INVALID (missing/invalid key is LOUD, never a silent pass, never
a gate). A preflight call validates the key before any spend; an
all-fallback run is marked INVALID_AUTH, never COMPLETE.

Provenance per call (recorded, never reconstructed):
  model, prompt_v, rubric_v, temperature, latency_s, input/output tokens,
  estimated cost USD, tool calls, label, confidence.

Cost guard: --max-cost-usd aborts the run before exceeding budget.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_MODEL = "gpt-5-mini"

PRICES_USD_PER_1K = {
    # Public pricing at time of writing; override via env if stale.
    "gpt-5-mini": {"in": float(os.getenv("RG_PRICE_IN", "0.00025")),
                   "out": float(os.getenv("RG_PRICE_OUT", "0.002"))},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
}

PROMPT_V = "invest_rank_v1"
RUBRIC_FREEFORM_V = "judge_freeform_v1"
RUBRIC_STRUCTURED_V = "judge_rubric_v1"

JUDGE_RUBRIC = """You are grading a commerce incident investigation. Reply with EXACTLY one JSON object, no other text.
Criteria (in this fixed order):
1. correctness: is the diagnosis in the acceptable set?
2. evidence: does it cite >=2 distinct tool claims?
3. humility: is confidence LOW or missing-evidence named when telemetry gapped?
Schema: {"pass": boolean, "criterion": "correctness|evidence|humility|none", "quote": "<=20 words from the diagnosis"}"""

JUDGE_FREEFORM = """Did this incident investigation get the right root cause? Reply with EXACTLY one JSON object, no other text.
Schema: {"pass": boolean, "reason": "<=20 words"}"""


class MissingKeyError(RuntimeError):
    pass


def require_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise MissingKeyError(
            "OPENAI_API_KEY absent: live evaluation INVALID (not skipped, not passed)")
    return key


def estimate_cost(model: str, inp: int, out: int) -> float:
    p = PRICES_USD_PER_1K.get(model, PRICES_USD_PER_1K[DEFAULT_MODEL])
    return round(inp / 1000 * p["in"] + out / 1000 * p["out"], 6)


def preflight_key() -> None:
    """One cheap call proving the key works BEFORE any benchmark spend.

    Raises MissingKeyError on absent key, RuntimeError on rejected key.
    Catches the exact failure seen in the field: a well-formed but invalid
    key that would otherwise turn every call into a silent mock fallback.
    """
    require_key()
    from openai import OpenAI
    try:
        OpenAI().models.list()
    except Exception as e:  # noqa: BLE001 - preflight must translate, not crash
        raise RuntimeError(f"key preflight failed ({type(e).__name__}): "
                           "check the key at platform.openai.com/account/api-keys")


def chat(model: str, messages: list[dict], temperature: float,
         max_tokens: int) -> tuple[str, dict]:
    """One metered call. Returns (text, provenance). Raises on API failure."""
    import random

    import openai
    from openai import OpenAI
    client = OpenAI()
    t0 = time.perf_counter()
    kwargs: dict = {"model": model, "messages": messages,
                    "max_completion_tokens": max_tokens}
    if not model.startswith("gpt-5"):
        # gpt-5 family only supports temperature=1 (the default): passing any
        # other value is a 400 error, so omit it there.
        kwargs["temperature"] = temperature
        eff_temp = temperature
    else:
        eff_temp = 1.0
    # Retry transient flakes (429/5xx/connection + occasional transient 404s
    # seen in the field); auth errors fail fast on attempt 1 via preflight.
    last: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            break
        except (openai.RateLimitError, openai.InternalServerError,
                openai.APIConnectionError, openai.NotFoundError) as e:
            last = e
            time.sleep(2 ** attempt + random.uniform(0, 1))
    else:
        raise last  # type: ignore[misc]
    dt = time.perf_counter() - t0
    choice = resp.choices[0].message.content or ""
    usage = resp.usage
    inp, out = (usage.prompt_tokens if usage else 0), \
        (usage.completion_tokens if usage else 0)
    return choice, {"model": model, "temperature": eff_temp,
                    "latency_s": round(dt, 3), "input_tokens": inp,
                    "output_tokens": out,
                    "cost_usd": estimate_cost(model, inp, out)}


def live_rank_hypotheses(ctx: dict, model: str, temperature: float = 0.0) -> tuple[list, dict]:
    """Condition B/C investigator brain: live ranking with contract validation."""
    from agent.providers.llm import ALLOWED_HYPOTHESES, MockProvider
    prompt = ("Rank checkout-regression hypotheses for flags "
              f"{json.dumps(ctx, sort_keys=True)}. Reply with EXACTLY a JSON list "
              'of {"name": <one of: ' + ",".join(sorted(ALLOWED_HYPOTHESES)) +
              '>, "confidence": HIGH|MEDIUM|LOW}.')
    prov: dict = {"model": model, "prompt_v": PROMPT_V, "role": "investigator"}
    try:
        text, call_prov = chat(model, [{"role": "user", "content": prompt}],
                               temperature, 2500)
        prov.update(call_prov)
        start, end = text.find("["), text.rfind("]")
        out = json.loads(text[start:end + 1])
        clean = [h for h in out if isinstance(h, dict)
                 and h.get("name") in ALLOWED_HYPOTHESES
                 and h.get("confidence") in ("HIGH", "MEDIUM", "LOW")]
        if clean:
            return clean, prov
    except Exception as e:  # noqa: BLE001 - any live failure -> deterministic fallback
        prov["fallback"] = f"{type(e).__name__}"
        prov.update({"prompt_v": PROMPT_V, "role": "investigator"})
        from agent.providers.llm import MockProvider as _MP
        return _MP().rank_hypotheses(**ctx), prov
    prov["fallback"] = "contract-validation"
    return MockProvider().rank_hypotheses(**ctx), prov


def live_judge(spec: dict, result: dict, model: str, rubric: str,
               temperature: float = 0.0) -> tuple[dict, dict]:
    """Condition C: LLM as judge. Returns (verdict, provenance)."""
    payload = {"acceptable": spec.get("acceptable_diagnoses"),
               "diagnosis": result["diagnosis"],
               "confidence": result.get("confidence"),
               "evidence_n": result.get("evidence_n"),
               "hypotheses_n": result.get("hypotheses_n")}
    template = JUDGE_RUBRIC if rubric == "rubric" else JUDGE_FREEFORM
    rv = RUBRIC_STRUCTURED_V if rubric == "rubric" else RUBRIC_FREEFORM_V
    try:
        text, prov = chat(model, [{"role": "user",
                                   "content": template + "\nCASE:\n" + json.dumps(payload)}],
                          temperature, 1500)
    except Exception as e:  # noqa: BLE001 - judge transport failure is data
        return ({"pass": False, "criterion": "none",
                 "quote": "judge transport failure"},
                {"model": model, "prompt_v": PROMPT_V, "rubric_v": rv,
                 "role": f"judge:{rubric}", "transport_error": type(e).__name__,
                 "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    prov.update({"prompt_v": PROMPT_V,
                 "rubric_v": rv, "role": f"judge:{rubric}"})
    try:
        start, end = text.find("{"), text.rfind("}")
        verdict = json.loads(text[start:end + 1])
        assert isinstance(verdict.get("pass"), bool)
    except Exception:  # noqa: BLE001 - unparseable judge output is a judge failure
        verdict = {"pass": False, "criterion": "none",
                   "quote": "unparseable judge output"}
        prov["fallback"] = "unparseable"
    return verdict, prov


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", choices=["B", "C"], required=True)
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL))
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="ignored for gpt-5 family (API only supports 1.0)")
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0,
                    help="0 = full Tier1 set; N = first N cases (smoke)")
    ap.add_argument("--out", default="evals/reports/live.json")
    args = ap.parse_args(argv)
    try:
        preflight_key()
    except (MissingKeyError, RuntimeError) as e:
        print(json.dumps({"status": "INVALID", "reason": str(e)}))
        return 3
    import glob

    import yaml

    import agent.orchestrator.loop as loopmod
    import agent.providers.llm as llmmod
    from evals.runner.run import run_spec

    # Frozen protocol: the investigator ALWAYS uses MockProvider's dispatch
    # point (even with a key set, which would otherwise select OpenAIProvider
    # with a different prompt). All live intelligence flows through metered_rank.
    loopmod.get_provider = lambda: llmmod.MockProvider()
    real_rank = llmmod.MockProvider.rank_hypotheses
    provenances: list[dict] = []
    spent = 0.0

    def metered_rank(self, **ctx):
        nonlocal spent
        out, prov = live_rank_hypotheses(ctx, args.model, args.temperature)
        spent += prov.get("cost_usd", 0.0)
        if spent > args.max_cost_usd:
            raise RuntimeError(f"cost guard tripped at ${spent:.4f}")
        provenances.append({"scenario_ctx": sorted(ctx),
                            **{k: v for k, v in prov.items()}})
        return out  # live_rank guarantees the contract (fallback included)

    paths = sorted(glob.glob("evals/cases/*.yaml"))
    if args.limit:
        paths = paths[:args.limit]
    results = []
    try:
        llmmod.MockProvider.rank_hypotheses = metered_rank
        for p in paths:
            results.append(run_spec(yaml.safe_load(Path(p).read_text())))
    finally:
        llmmod.MockProvider.rank_hypotheses = real_rank

    out: dict = {"status": "COMPLETE", "condition": args.condition,
                 "model": args.model, "temperature": args.temperature,
                 "prompt_v": PROMPT_V, "n": len(results),
                 "spend_usd": round(spent, 6), "results": results,
                 "investigator_provenance": provenances}
    # All-fallback tripwire: if EVERY ranking fell back (e.g. key died
    # mid-run), this is mock data wearing a live label -> INVALID_AUTH.
    live_calls = [p for p in provenances if not p.get("fallback")]
    if args.condition in ("B", "C") and results and not live_calls:
        out["status"] = "INVALID_AUTH"
        out["reason"] = ("all investigator calls fell back; refusing to "
                         "publish mock results as live")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=2))
        print(json.dumps({"status": "INVALID_AUTH", "reason": out["reason"]}))
        return 3
    if args.condition == "C":
        verdicts = []
        for p, r in zip(paths, results):
            spec = yaml.safe_load(Path(p).read_text())
            for rubric in ("freeform", "rubric"):
                v, prov = live_judge(spec, r, args.model, rubric, args.temperature)
                spent += prov.get("cost_usd", 0.0)
                verdicts.append({"scenario": r["scenario"], "judge": rubric,
                                 "verdict": v, "provenance": prov})
        out["judge_verdicts"] = verdicts
        out["spend_usd"] = round(spent, 6)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    acc = sum(r["passed"] for r in results) / max(1, len(results))
    print(json.dumps({"status": "COMPLETE", "condition": args.condition,
                      "accuracy_heuristic": round(acc, 4), "n": len(results),
                      "spend_usd": round(spent, 6)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
