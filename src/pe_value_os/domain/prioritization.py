"""Deterministic prioritization and in-year value phasing (PVC-025).

score = w_ebitda * (base EBITDA / max base EBITDA)
      + w_confidence * confidence_score
      + w_time_to_value * (13 - start_month) / 12
      - w_one_time_cost * (one-time cost / max one-time cost)

Ties break on opportunity_id. In-year value accrues from the lever's start month with a linear ramp, so
|in-year| <= |run-rate| always.
"""

from __future__ import annotations

from decimal import Decimal

from ..policy import PolicyConfig
from .calc import q_money, q_ratio
from .models import Confidence
from .project_models import Lever, Opportunity, PriorityScore, ValueCase

CONFIDENCE_SCORE = {
    Confidence.LOW: Decimal("0.3333"),
    Confidence.MEDIUM: Decimal("0.6667"),
    Confidence.HIGH: Decimal(1),
}


def in_year_factor(start_month: int, ramp_months: int) -> Decimal:
    """Fraction of annual run-rate captured in year one (0..1)."""
    if not 1 <= start_month <= 12:
        raise ValueError("start_month must be 1..12")
    ramp = max(ramp_months, 1)
    months_active = 13 - start_month
    captured = sum((min(Decimal(k) / ramp, Decimal(1)) for k in range(1, months_active + 1)), Decimal(0))
    return captured / 12


def phase(run_rate: Decimal, lever: Lever, policy: PolicyConfig) -> tuple[Decimal, int]:
    start = policy.prioritization.start_month[lever]
    factor = in_year_factor(start, policy.prioritization.ramp_months[lever])
    return q_money(run_rate * factor), start


def prioritize(items: list[tuple[Opportunity, ValueCase]], policy: PolicyConfig) -> list[PriorityScore]:
    if not items:
        return []
    w = policy.prioritization.weights
    max_base = max((vc.annual_ebitda_base for _, vc in items), default=Decimal(0))
    max_cost = max((o.one_time_cost for o, _ in items), default=Decimal(0))
    scored: list[tuple[Decimal, str, PriorityScore]] = []
    for opp, vc in items:
        start = policy.prioritization.start_month[opp.lever]
        comp = {
            "ebitda": q_ratio(max(vc.annual_ebitda_base, Decimal(0)) / max_base) if max_base > 0 else Decimal(0),
            "confidence": CONFIDENCE_SCORE[opp.confidence],
            "time_to_value": q_ratio(Decimal(13 - start) / 12),
            "one_time_cost": q_ratio(opp.one_time_cost / max_cost) if max_cost > 0 else Decimal(0),
        }
        score = q_ratio(
            w["ebitda"] * comp["ebitda"]
            + w["confidence"] * comp["confidence"]
            + w["time_to_value"] * comp["time_to_value"]
            - w["one_time_cost"] * comp["one_time_cost"]
        )
        in_year, _ = phase(vc.annual_ebitda_base, opp.lever, policy)
        scored.append(
            (
                score,
                opp.opportunity_id,
                PriorityScore(
                    opportunity_id=opp.opportunity_id,
                    rank=0,
                    score=score,
                    components=comp,
                    run_rate_ebitda_base=vc.annual_ebitda_base,
                    in_year_ebitda_base=in_year,
                    start_month=start,
                ),
            )
        )
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [ps.model_copy(update={"rank": i}) for i, (_, _, ps) in enumerate(scored, start=1)]
