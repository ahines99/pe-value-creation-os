"""Deterministic 100-day plan builder (supports skills/100-day-planning).

The plan adds sequencing, ownership and measurement; it never adds value that the value cases did not size.
KPI baselines come from the metric registry (with evidence); targets are derived from each opportunity's
base-case effective rate by the functions below, so every target is reproducible from stored inputs.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ..domain.baselines import REGISTRY, MetricUnavailable, compute_metric
from ..domain.calc import q_money, q_ratio
from ..domain.dataset import CompanyData
from ..domain.project_models import (
    Initiative,
    InitiativeClass,
    Lever,
    Opportunity,
    Plan,
    PlanKpi,
    PriorityScore,
    ValueCase,
    Workstream,
)
from ..domain.retention import analyse_retention
from ..policy import PolicyConfig

OWNER = {
    Lever.PRICING: "Chief Revenue Officer",
    Lever.RETENTION: "VP Customer Success",
    Lever.SALES_EFFICIENCY: "Chief Revenue Officer",
    Lever.GROSS_MARGIN: "Chief Technology Officer",
    Lever.AI_AUTOMATION: "Chief Operating Officer",
}
WORKSTREAM_NAME = {
    Lever.PRICING: "Pricing and monetisation",
    Lever.RETENTION: "Retention and customer success",
    Lever.SALES_EFFICIENCY: "Go-to-market efficiency",
    Lever.GROSS_MARGIN: "Gross margin",
    Lever.AI_AUTOMATION: "AI and automation",
}
APPROVAL_REASONS = {
    Lever.PRICING: "Customer-facing price or discount-policy change",
    Lever.AI_AUTOMATION: "Operating-model change with possible headcount implications (HR/legal review)",
    Lever.SALES_EFFICIENCY: "Go-to-market budget or headcount change",
}


@dataclass(frozen=True)
class KpiRule:
    metric: str
    description: str
    params_from: str | None  # opportunity metric_params key to copy
    target: Callable[[Decimal, Opportunity, CompanyData], Decimal]
    unscoped_metric: str | None = None  # metric to use when the opportunity has no params_from value


def _eff(o: Opportunity) -> Decimal:
    return o.base.effective_rate


def _segment_opening(o: Opportunity, data: CompanyData) -> Decimal:
    seg = o.metric_params.get("segment")
    ra = analyse_retention(data)
    row = next((s for s in ra.segments if s.dimension == "segment" and s.value == seg), None) if seg else None
    return row.opening_arr if row else sum((s.opening_arr for s in ra.segments if s.dimension == "segment"),
                                           Decimal(0))


def _grr_target(b: Decimal, o: Opportunity, d: CompanyData) -> Decimal:
    opening = _segment_opening(o, d)
    return min(Decimal(1), b + (o.baseline_value * _eff(o) / opening if opening else Decimal(0)))


def _gm_target(b: Decimal, o: Opportunity, d: CompanyData) -> Decimal:
    rev = compute_metric(d, "total_arr").value
    return min(Decimal(1), b + (o.baseline_value * _eff(o) / rev if rev else Decimal(0)))


KPI_RULES: dict[tuple[Lever, str], KpiRule] = {
    (Lever.PRICING, "discounted_arr"): KpiRule(
        "avg_new_deal_discount_rate", "Average new-deal discount", "segment",
        lambda b, o, d: max(Decimal(0), b - _eff(o))),
    (Lever.PRICING, "renewing_arr"): KpiRule(
        "renewal_uplift_realization", "Realized / contracted renewal uplift", None,
        lambda b, o, d: min(Decimal(1), b + o.base.realization_rate * (1 - b))),
    (Lever.PRICING, "legacy_price_book_arr"): KpiRule(
        "legacy_arr_share", "Share of ARR on legacy price books", None,
        lambda b, o, d: b * (1 - o.base.realization_rate)),
    (Lever.RETENTION, "addressable_churned_arr"): KpiRule(
        "segment_grr", "Segment gross revenue retention", "segment", _grr_target, unscoped_metric="grr"),
    (Lever.RETENTION, "failed_payment_churned_arr"): KpiRule(
        "involuntary_churn_share", "Share of churn from failed payments", None, lambda b, o, d: b * (1 - _eff(o))),
    (Lever.SALES_EFFICIENCY, "s_and_m_expense"): KpiRule(
        "cac_payback_months", "CAC payback (months)", None, lambda b, o, d: b * (1 - _eff(o))),
    (Lever.GROSS_MARGIN, "hosting_cost"): KpiRule(
        "subscription_gross_margin", "Subscription gross margin", None, _gm_target),
    (Lever.AI_AUTOMATION, "support_cost_tier1"): KpiRule(
        "tier1_tickets_per_customer_month", "Tier-1 tickets per customer per month", None,
        lambda b, o, d: b * (1 - _eff(o))),
}


def classify(o: Opportunity, policy: PolicyConfig) -> InitiativeClass:
    return InitiativeClass.QUICK_WIN if policy.prioritization.start_month[o.lever] <= 3 else InitiativeClass.STRUCTURAL


def day_100_fraction(o: Opportunity, policy: PolicyConfig) -> Decimal:
    """Share of the move from baseline to run-rate target expected by day 100 (about 3.3 months)."""
    start = policy.prioritization.start_month[o.lever]
    ramp = max(policy.prioritization.ramp_months[o.lever], 1)
    active = max(Decimal(0), Decimal("3.3") - (start - 1))
    return min(Decimal(1), active / ramp)


def _kpi(o: Opportunity, data: CompanyData, policy: PolicyConfig) -> PlanKpi | None:
    rule = KPI_RULES.get((o.lever, o.baseline_metric))
    if rule is None:
        return None
    params = {rule.params_from: o.metric_params[rule.params_from]} if rule.params_from and \
        o.metric_params.get(rule.params_from) else {}
    if rule.params_from and not params and rule.unscoped_metric:
        rule = KpiRule(rule.unscoped_metric, "Gross revenue retention", None, rule.target)
    try:
        base = compute_metric(data, rule.metric, params)
    except MetricUnavailable:
        return None
    target = q_ratio(rule.target(base.value, o, data))
    frac = day_100_fraction(o, policy)
    spec = REGISTRY[rule.metric]
    return PlanKpi(
        kpi_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"kpi:{o.opportunity_id}:{rule.metric}")),
        opportunity_id=o.opportunity_id,
        metric=rule.metric, description=rule.description + (f" ({params['segment']})" if params else ""),
        baseline=base.value, day_100_target=q_ratio(base.value + (target - base.value) * frac),
        run_rate_target=target, direction=spec.direction, cadence_days=policy.kpi.default_cadence_days,
        source=f"metric:{rule.metric}", evidence_ids=base.evidence_ids,
        monitorable=rule.metric in REGISTRY, metric_params=params,
    )


def build_plan(
    run_id: str,
    data: CompanyData,
    items: list[tuple[Opportunity, ValueCase]],
    priorities: list[PriorityScore],
    policy: PolicyConfig,
    *,
    excluded: list[dict[str, str]] | None = None,
    data_gaps: list[str] | None = None,
    reviewer_notes: str | None = None,
) -> Plan:
    rank = {p.opportunity_id: p for p in priorities}
    ordered = sorted(items, key=lambda it: rank[it[0].opportunity_id].rank if it[0].opportunity_id in rank else 999)
    by_lever: dict[Lever, list[tuple[Opportunity, ValueCase]]] = {}
    for opp, vc in ordered:
        by_lever.setdefault(opp.lever, []).append((opp, vc))

    workstreams: list[Workstream] = []
    decisions: list[str] = []
    for lever, lever_items in by_lever.items():
        initiatives, kpis, risks = [], [], []
        for opp, vc in lever_items:
            ps = rank.get(opp.opportunity_id)
            reasons = [APPROVAL_REASONS[lever]] if lever in APPROVAL_REASONS else []
            initiatives.append(Initiative(
                opportunity_id=opp.opportunity_id, title=opp.title, classification=classify(opp, policy),
                run_rate_ebitda_base=vc.annual_ebitda_base,
                in_year_ebitda_base=ps.in_year_ebitda_base if ps else Decimal(0),
                requires_approval_reasons=reasons))
            decisions += [f"{opp.title}: {r}" for r in reasons]
            k = _kpi(opp, data, policy)
            if k:
                kpis.append(k)
            risks += [f"{opp.title}: {a}" for a in opp.assumptions]
        quick = [i.title for i in initiatives if i.classification == InitiativeClass.QUICK_WIN]
        structural = [i.title for i in initiatives if i.classification == InitiativeClass.STRUCTURAL]
        milestones = {
            "day_30": ["Baselines confirmed against system data and signed off by the owner",
                       "Workstream owner and team named", *[f"Launch: {t}" for t in quick],
                       *[f"Design and pilot scope agreed: {t}" for t in structural]],
            "day_60": [*[f"First KPI readout: {t}" for t in quick],
                       *[f"Pilot live in at least one segment: {t}" for t in structural]],
            "day_100": ["Rollout decision for each pilot", "KPIs tracking against day-100 targets",
                        "Next-phase plan and budget request"],
        }
        deps = []
        if lever == Lever.PRICING:
            deps.append("Contract notice periods and caps reviewed before any customer communication")
            if Lever.RETENTION in by_lever:
                deps.append("Price changes sequenced after the retention health score identifies at-risk accounts")
        if lever == Lever.AI_AUTOMATION:
            deps.append("Evaluation set and rollback plan before any customer-facing automation")
        workstreams.append(Workstream(
            workstream_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"ws:{run_id}:{lever.value}")),
            name=WORKSTREAM_NAME[lever], lever=lever, owner_role=OWNER[lever], initiatives=initiatives,
            milestones=milestones, kpis=kpis, dependencies=deps, risks=risks))

    if data_gaps:
        decisions.append("Accept or remediate open data gaps: " + "; ".join(data_gaps[:5]))
    total_rr = sum((vc.annual_ebitda_base for _, vc in items), Decimal(0))
    total_iy = sum((rank[o.opportunity_id].in_year_ebitda_base for o, _ in items if o.opportunity_id in rank),
                   Decimal(0))
    return Plan(
        plan_id=str(uuid.uuid4()), run_id=run_id, company_id=data.company_id, workstreams=workstreams,
        total_run_rate_ebitda_base=q_money(total_rr), total_in_year_ebitda_base=q_money(total_iy),
        excluded_opportunities=list(excluded or []), decisions_requiring_approval=decisions,
        governance=["Weekly workstream check-in", "Biweekly steering committee", "Monthly sponsor update"],
        narrative=f"Reviewer notes applied: {reviewer_notes}" if reviewer_notes else None,
    )
