"""Policy checks (PVC-026). Company scope lives in `pe_value_os.security`."""

from __future__ import annotations

from pydantic import BaseModel

from .models import Finding, FindingType

VALUE_CLAIM_TYPES = {FindingType.VALUE_CLAIM, FindingType.OPPORTUNITY}


class PolicyViolation(Exception):
    """A request broke an operating rule. Callers should surface this, never retry it."""


class ActionDecision(BaseModel):
    allowed: bool
    requires_human_approval: bool
    reason: str


def check_action(action: str, risk_tier: str, has_approval: bool) -> ActionDecision:
    if risk_tier in {"high", "critical"} and not has_approval:
        return ActionDecision(
            allowed=False, requires_human_approval=True, reason="Material action requires explicit human approval"
        )
    return ActionDecision(allowed=True, requires_human_approval=False, reason="Policy satisfied")


def require_citations(finding: Finding) -> None:
    if finding.finding_type in VALUE_CLAIM_TYPES and not finding.evidence_ids:
        raise PolicyViolation("Value claims must cite at least one evidence_id; return NEEDS_EVIDENCE instead.")
