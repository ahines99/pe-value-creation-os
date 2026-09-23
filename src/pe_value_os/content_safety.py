"""Deterministic screening of untrusted text for prompt injection and cross-company lures (PVC-073).

Retrieved text is data. This screen does not make text safe; it records `suspicious_content` findings so a
human sees them, and the model layer additionally delimits untrusted text and restricts tools per step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(previous|prior|above|all|your|the)\b[^.]{0,30}"
        r"\b(instructions?|rules?|prompts?|guidelines?|policy|policies)\b", re.I)),
    ("addressed_to_ai", re.compile(
        r"\b(note|instructions?|message|directive)s?\b[^.]{0,20}\b(to|for)\b[^.]{0,20}\b(ai|assistant|agent|model|"
        r"llm|claude|gpt)\b", re.I)),
    ("role_hijack", re.compile(r"\b(you are now|act as|pretend to be|new system prompt|system prompt:)\b", re.I)),
    ("approval_manipulation", re.compile(
        r"\b(approve|auto-?approve|sign off)\b[^.]{0,30}\b(plan|automatically|without review)\b", re.I)),
    ("confidence_manipulation", re.compile(
        r"\b(mark|set|report)\b[^.]{0,40}\b(high confidence|every opportunity|ebitda uplift)\b", re.I)),
    ("exfiltration", re.compile(r"\b(send|email|post|upload|exfiltrate)\b[^.]{0,40}\b(to|at)\b[^.]{0,20}(https?://|@)",
                                re.I)),
]


@dataclass(frozen=True)
class Detection:
    reasons: tuple[str, ...]
    excerpt: str

    @property
    def suspicious(self) -> bool:
        return bool(self.reasons)


def scan(text: str, other_company_ids: set[str] | None = None) -> Detection:
    reasons = [name for name, rx in PATTERNS if rx.search(text)]
    lowered = text.lower()
    for cid in sorted(other_company_ids or ()):
        if cid.lower() in lowered:
            reasons.append(f"cross_company_reference:{cid}")
    excerpt = re.sub(r"\s+", " ", text.strip())[:160]
    return Detection(tuple(reasons), excerpt)
