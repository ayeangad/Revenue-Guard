"""Evidence freshness: stale data must affect behavior, not just sit in a field."""
from __future__ import annotations

from domain.models import Evidence


def age_s(ev: Evidence) -> float:
    return (ev.collected_at - ev.observed_at).total_seconds()


def is_stale(ev: Evidence) -> bool:
    return age_s(ev) > ev.freshness_window_s


def assess(evidence: list[Evidence]) -> dict:
    stale = [e.evidence_id for e in evidence if is_stale(e)]
    return {"stale_ids": stale,
            "fresh_ids": [e.evidence_id for e in evidence if not is_stale(e)],
            "all_fresh": not stale}


def downgrade(conf: str) -> str:
    return {"HIGH": "MEDIUM", "MEDIUM": "LOW"}.get(conf, "LOW")
