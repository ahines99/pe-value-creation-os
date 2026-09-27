"""Shared deterministic screening for model and interactive proposals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..domain import ai_ops
from ..domain.baselines import LEVER_METRICS
from ..domain.dataset import CompanyData
from ..domain.metrics import compute_saas_metrics
from ..domain.pricing import price_waterfall
from ..domain.project_models import Lever
from ..domain.retention import analyse_retention
from ..policy import PolicyConfig
from ..workflows.proposals import (
    BranchContext,
    RuleBasedProposer,
    ai_findings,
    pricing_findings,
    retention_findings,
    unit_economics_findings,
)

BRANCH = {
    Lever.PRICING: "pricing",
    Lever.RETENTION: "retention",
    Lever.SALES_EFFICIENCY: "unit_economics",
    Lever.GROSS_MARGIN: "unit_economics",
    Lever.AI_AUTOMATION: "ai_opportunity",
}


def branch_context(data: CompanyData, branch: str, policy: PolicyConfig) -> BranchContext:
    computations: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {
        "pricing": (price_waterfall, pricing_findings),
        "retention": (analyse_retention, retention_findings),
        "unit_economics": (compute_saas_metrics, unit_economics_findings),
        "ai_opportunity": (ai_ops.assess, ai_findings),
    }
    compute, findings = computations[branch]
    result = compute(data)
    return BranchContext(
        branch, data.company_id, policy, result, findings(result, policy), data.evidence(*data.datasets)
    )


def eligibility_error(ctx: BranchContext, lever: Lever, metric: str, params: dict[str, str]) -> str | None:
    if metric not in LEVER_METRICS[lever]:
        return "baseline metric is not allowed for this lever"
    # Aggregate baselines use the same breached lever screening conditions. This
    # preserves the full baseline registry rather than restricting judgment to
    # the rule proposer's preferred sizing grain.
    equivalents = {
        (Lever.PRICING, "total_arr"): {"discounted_arr", "renewing_arr", "legacy_price_book_arr"},
        (Lever.RETENTION, "annual_contracted_arr"): {"addressable_churned_arr", "failed_payment_churned_arr"},
        (Lever.GROSS_MARGIN, "subscription_cogs"): {"hosting_cost"},
        (Lever.AI_AUTOMATION, "subscription_cogs"): {"support_cost_tier1"},
    }.get((lever, metric), {metric})
    eligible = [p for p in RuleBasedProposer().propose(ctx) if p.lever == lever and p.baseline_metric in equivalents]
    if lever == Lever.AI_AUTOMATION and metric == "finance_ops_cost":
        # Finance automation requires measured volume and unit cost, not just
        # finance headcount. The current assessment reports that named data gap.
        if any(c.sizeable and c.baseline_metric == metric for c in ctx.result.candidates):
            return None
        return "finance automation requires measured process volume and unit cost"
    if not eligible:
        return "no deterministic policy threshold breach supports this lever and metric"
    if params and not any(not p.metric_params or p.metric_params == params for p in eligible):
        return "no deterministic policy threshold breach supports this segment"
    return None
