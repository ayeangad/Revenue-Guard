"""Untrusted-content guard. Product names/descriptions/order notes are attacker-controlled.

Rules:
- never execute instructions found inside commerce content
- tool args derived from commerce content are quoted + length-capped
- known injection patterns -> block with explicit refusal (logged, counted)
"""
from __future__ import annotations

import re

_PATTERNS = [
    r"ignore (previous|all) instructions",
    r"system\s*:",
    r"execute .*rollback",
    r"approve.*production",
    r"exfiltrate",
]

_MAX_LEN = 500


def sanitize_commerce_text(s: str) -> str:
    s = s.strip()[:_MAX_LEN]
    return s.replace("\x00", "")


def contains_injection(s: str) -> bool:
    low = s.lower()
    return any(re.search(p, low) for p in _PATTERNS)
