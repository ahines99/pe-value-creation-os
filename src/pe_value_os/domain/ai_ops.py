"""AI / automation candidate profiling (supports skills/ai-opportunity-assessment).

Only workflows with measured volume and unit cost are sizeable. Scores are reported per dimension
(1 = weak, 3 = strong) and never combined; ranking happens in prioritization once candidates are sized.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from .calc import ZERO, add_months, month_range, q_money, q_ratio
from .dataset import CompanyData
from .source_models import DatasetKind, HeadcountMonth, SupportTicket

TIER1_CATEGORIES = {"how_to", "account_admin", "billing"}


class AiCandidate(BaseModel):
    workflow: str
    annual_volume: int | None
    annual_cost: Decimal | None
    unit_cost: Decimal | None
    addressable_share: Decimal | None
    scores: dict[str, int]
    sizeable: bool
    baseline_metric: str | None
    data_needed: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AiAssessment(BaseModel):
    company_id: str
    period_end: date | None
    support_cost_annual: Decimal | None
    tier1_cost_share: Decimal | None
    ticket_mix: dict[str, int]
    candidates: list[AiCandidate]


def _annual_cost(rows: list[HeadcountMonth], function: str) -> Decimal | None:
    fr = [h for h in rows if h.function == function]
    if not fr:
        return None
    last = max(h.month for h in fr)
    return q_money(sum((h.fte * h.fully_loaded_annual_cost_per_fte for h in fr if h.month == last), ZERO))


def assess(data: CompanyData) -> AiAssessment:
    hc: list[HeadcountMonth] = data.records(DatasetKind.HEADCOUNT)
    tickets: list[SupportTicket] = data.records(DatasetKind.SUPPORT)
    t1 = _annual_cost(hc, "support_tier1")
    t2 = _annual_cost(hc, "support_tier2")
    last = max((h.month for h in hc), default=None)
    recent: list[SupportTicket] = []
    if last is not None:
        window = set(month_range(add_months(last, -11), last))
        recent = [t for t in tickets if date(t.created_at.year, t.created_at.month, 1) in window]
    mix = Counter(t.category for t in recent)
    support_cost = (t1 or ZERO) + (t2 or ZERO)
    tier1_share = q_ratio(t1 / support_cost) if t1 and support_cost else None
    candidates: list[AiCandidate] = []
    if t1 and recent:
        vol = sum(1 for t in recent if t.tier == "tier1")
        addressable = sum(1 for t in recent if t.category in TIER1_CATEGORIES)
        candidates.append(
            AiCandidate(
                workflow="tier1_support_deflection",
                annual_volume=vol,
                annual_cost=t1,
                unit_cost=q_money(t1 / vol) if vol else None,
                addressable_share=q_ratio(Decimal(addressable) / len(recent)),
                scores={"value": 3 if t1 > 500_000 else 2, "feasibility": 3, "risk": 3, "time_to_value": 3},
                sizeable=True,
                baseline_metric="support_cost_tier1",
                evidence_ids=data.evidence(DatasetKind.SUPPORT, DatasetKind.HEADCOUNT),
            )
        )
    for function, workflow, need, scores in (
        (
            "finance_ops",
            "finance_ops_automation",
            "Transaction volumes by finance process (AP invoices, close tasks, collections)",
            {"value": 2, "feasibility": 2, "risk": 2, "time_to_value": 1},
        ),
        (
            "billing_ops",
            "billing_operations_automation",
            "Billing exception and dispute volumes",
            {"value": 1, "feasibility": 2, "risk": 2, "time_to_value": 2},
        ),
    ):
        cost = _annual_cost(hc, function)
        if cost:
            candidates.append(
                AiCandidate(
                    workflow=workflow,
                    annual_volume=None,
                    annual_cost=cost,
                    unit_cost=None,
                    addressable_share=None,
                    scores=scores,
                    sizeable=False,
                    baseline_metric=None,
                    data_needed=[need],
                    evidence_ids=data.evidence(DatasetKind.HEADCOUNT),
                )
            )
    return AiAssessment(
        company_id=data.company_id,
        period_end=last,
        support_cost_annual=q_money(support_cost),
        tier1_cost_share=tier1_share,
        ticket_mix=dict(sorted(mix.items())),
        candidates=candidates,
    )
