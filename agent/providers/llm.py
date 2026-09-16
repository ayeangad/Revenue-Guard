"""LLM provider abstraction: mock (deterministic, default for CI) + OpenAI."""
from __future__ import annotations

import os

ALLOWED_HYPOTHESES = {
    "shipping_plugin_regression", "shipping_dependency_degradation",
    "shipping_dependency_degradation_via_deploy", "deployment_regression",
    "traffic_resource_saturation", "payment_gateway_degradation", "pricing_bug",
    "mobile_checkout_regression", "database_regression", "cache_failure",
    "unknown_insufficient_evidence",
}


class MockProvider:
    """Heuristic hypothesis ranking without network. Used in tests/CI."""

    def rank_hypotheses(self, *, checkout_spike: bool = False, ship_spike: bool = False,
                        recent_deploy: bool = False, telemetry_gap: bool = False,
                        payment_spike: bool = False, pricing_anomaly: bool = False,
                        mobile_only: bool = False, db_spike: bool = False,
                        cache_drop: bool = False, **_kw) -> list[dict]:
        if telemetry_gap:
            return [{"name": "unknown_insufficient_evidence", "confidence": "LOW"}]
        hyps: list[dict] = []
        # Order matters: most specific first. Dependency-first rule (v0.4 lesson):
        # check payment/pricing/cohort signals before blaming the most recent deploy.
        if payment_spike:
            hyps.append({"name": "payment_gateway_degradation", "confidence": "HIGH"})
        if pricing_anomaly:
            hyps.append({"name": "pricing_bug", "confidence": "HIGH"})
        if mobile_only:
            hyps.append({"name": "mobile_checkout_regression", "confidence": "HIGH"})
        if recent_deploy and ship_spike:
            hyps.append({"name": "shipping_plugin_regression", "confidence": "HIGH"})
        if ship_spike:
            hyps.append({"name": "shipping_dependency_degradation_via_deploy"
                         if recent_deploy else "shipping_dependency_degradation",
                         "confidence": "MEDIUM"})
        if db_spike or cache_drop:
            hyps.append({"name": "database_regression" if db_spike else "cache_failure",
                         "confidence": "MEDIUM"})
        if recent_deploy:
            hyps.append({"name": "deployment_regression", "confidence": "MEDIUM"})
        hyps.append({"name": "traffic_resource_saturation", "confidence": "LOW"})
        # de-dup preserve order
        seen, out = set(), []
        for h in hyps:
            if h["name"] not in seen:
                seen.add(h["name"])
                out.append(h)
        return out[:4]


class OpenAIProvider:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def rank_hypotheses(self, **ctx) -> list[dict]:
        # Lazy import so CI without key still works; falls back to mock logic.
        if not os.getenv("OPENAI_API_KEY"):
            return MockProvider().rank_hypotheses(**ctx)
        try:
            from openai import OpenAI
            client = OpenAI()
            prompt = (
                "Rank checkout-regression hypotheses given flags "
                f"{ctx}. Return JSON list of {{name, confidence}}."
            )
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300, temperature=0)
            import json
            txt = resp.choices[0].message.content or "[]"
            out = json.loads(txt[txt.find("["):txt.rfind("]") + 1])
            # Hostile-review fix: never trust model output shape/names.
            # Unknown names or bad confidence -> fall back to deterministic mock.
            clean = [h for h in out if isinstance(h, dict)
                     and h.get("name") in ALLOWED_HYPOTHESES
                     and h.get("confidence") in ("HIGH", "MEDIUM", "LOW")]
            return clean if clean else MockProvider().rank_hypotheses(**ctx)
        except Exception:  # noqa: BLE001 - fallback to deterministic mock
            return MockProvider().rank_hypotheses(**ctx)


def get_provider():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return MockProvider()
