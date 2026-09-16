"""LLM provider abstraction: mock (deterministic, default for CI) + OpenAI."""
from __future__ import annotations

import os


class MockProvider:
    """Heuristic hypothesis ranking without network. Used in tests/CI."""

    def rank_hypotheses(self, *, checkout_spike: bool, ship_spike: bool,
                        recent_deploy: bool, telemetry_gap: bool) -> list[dict]:
        if telemetry_gap:
            return [{"name": "unknown_insufficient_evidence", "confidence": "LOW"}]
        hyps = []
        if recent_deploy and ship_spike:
            hyps.append({"name": "shipping_plugin_regression", "confidence": "HIGH"})
        if ship_spike:
            hyps.append({"name": "shipping_dependency_degradation_via_deploy"
                         if recent_deploy else "shipping_dependency_degradation",
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
            return json.loads(txt[txt.find("["):txt.rfind("]") + 1])
        except Exception:  # noqa: BLE001 - fallback to deterministic mock
            return MockProvider().rank_hypotheses(**ctx)


def get_provider():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return MockProvider()
