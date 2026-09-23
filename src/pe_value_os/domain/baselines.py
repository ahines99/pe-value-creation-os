"""Server-side baselines and EBITDA flow-through (PVC-028).

Proposers name a baseline metric; they never supply its value. Every metric here is computed from company
data and returns the evidence it used. The same registry backs KPI monitoring (PVC-120/121), so a KPI is
"monitorable" exactly when its metric is registered here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ..policy import PolicyConfig
from .calc import (
    SUB_COGS,
    ZERO,
    ArrLedger,
    MetricUnavailable,
    add_months,
    month_range,
    pnl_by_month,
    q_money,
    q_ratio,
    sum_accounts,
)
from .dataset import CompanyData
from .metrics import compute_saas_metrics
from .pricing import price_waterfall
from .project_models import Lever
from .retention import analyse_retention
from .source_models import ChurnType, ContractTerm, DatasetKind, PnLAccount


class BaselineValue(BaseModel):
    metric: str
    value: Decimal
    unit: str
    description: str
    period_end: date | None = None
    params: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str]


MetricFn = Callable[[CompanyData, dict[str, str]], BaselineValue]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    unit: str
    description: str
    fn: MetricFn
    direction: str  # which way is better for KPI monitoring: increase | decrease
    params: tuple[str, ...] = ()


REGISTRY: dict[str, MetricSpec] = {}


def metric(
    name: str, unit: str, description: str, direction: str, params: tuple[str, ...] = ()
) -> Callable[[MetricFn], MetricFn]:
    def deco(fn: MetricFn) -> MetricFn:
        REGISTRY[name] = MetricSpec(name, unit, description, fn, direction, params)
        return fn

    return deco


def _ledger(data: CompanyData) -> ArrLedger:
    ledger = ArrLedger(data.records(DatasetKind.ARR))
    if not ledger.months:
        raise MetricUnavailable("No ARR data")
    return ledger


def _segment_ids(data: CompanyData, params: dict[str, str]) -> set[str] | None:
    seg = params.get("segment")
    if not seg:
        return None
    ids = {c.customer_id for c in data.records(DatasetKind.CUSTOMERS) if c.segment == seg}
    if not ids:
        raise MetricUnavailable(f"No customers in segment {seg!r}")
    return ids


def _bv(
    name: str,
    value: Decimal,
    data: CompanyData,
    params: dict[str, str],
    kinds: tuple[DatasetKind, ...],
    period_end: date | None = None,
) -> BaselineValue:
    spec = REGISTRY[name]
    ev = data.evidence(*kinds)
    if not ev:
        raise MetricUnavailable(f"No evidence for {name}")
    return BaselineValue(
        metric=name,
        value=value,
        unit=spec.unit,
        description=spec.description,
        period_end=period_end,
        params=params,
        evidence_ids=ev,
    )


def _t12_churned(data: CompanyData, params: dict[str, str], types: set[ChurnType]) -> tuple[Decimal, date]:
    ledger = _ledger(data)
    ids = _segment_ids(data, params)
    end = ledger.last_month
    start = add_months(end, -12)
    total = ZERO
    for ev in data.records(DatasetKind.CHURN):
        if ev.churn_type in types and start < ev.month <= end and (ids is None or ev.customer_id in ids):
            total += ledger.last_arr_before(ev.customer_id, ev.month)
    return q_money(total), end


@metric("total_arr", "currency", "Total ARR at the latest month", "increase", ("segment",))
def _total_arr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    ledger = _ledger(data)
    ids = _segment_ids(data, params)
    total = sum(
        (ledger.arr(c, ledger.last_month) for c in ledger.active(ledger.last_month) if ids is None or c in ids), ZERO
    )
    return _bv("total_arr", q_money(total), data, params, (DatasetKind.ARR, DatasetKind.CUSTOMERS), ledger.last_month)


@metric(
    "renewing_arr",
    "currency",
    "ARR whose current contract ends within 12 months of the reference date",
    "increase",
    ("segment",),
)
def _renewing_arr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    contracts: list[ContractTerm] = data.records(DatasetKind.CONTRACTS)
    if not contracts:
        raise MetricUnavailable("Contract terms are required to identify renewing ARR")
    ledger = _ledger(data)
    ids = _segment_ids(data, params)
    horizon = add_months(data.reference_date, 12)
    renewing = {c.customer_id for c in contracts if data.reference_date <= c.end_date < horizon}
    total = sum(
        (
            ledger.arr(c, ledger.last_month)
            for c in ledger.active(ledger.last_month)
            if c in renewing and (ids is None or c in ids)
        ),
        ZERO,
    )
    return _bv(
        "renewing_arr",
        q_money(total),
        data,
        params,
        (DatasetKind.ARR, DatasetKind.CONTRACTS, DatasetKind.CUSTOMERS),
        ledger.last_month,
    )


@metric(
    "discounted_arr",
    "currency",
    "List-price value of ARR in scope (ARR grossed up by each customer's latest discount rate)",
    "increase",
    ("segment",),
)
def _discounted_arr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    ledger = _ledger(data)
    ids = _segment_ids(data, params)
    latest: dict[str, tuple[date, Decimal]] = {}
    for ln in data.records(DatasetKind.INVOICES):
        gross = ln.list_price_per_unit * ln.quantity
        if gross and (ln.customer_id not in latest or ln.invoice_date >= latest[ln.customer_id][0]):
            latest[ln.customer_id] = (ln.invoice_date, ln.on_invoice_discount / gross)
    if not latest:
        raise MetricUnavailable("No invoices")
    total = ZERO
    for c in ledger.active(ledger.last_month):
        if (ids is None or c in ids) and c in latest and latest[c][1] < 1:
            total += ledger.arr(c, ledger.last_month) / (1 - latest[c][1])
    return _bv(
        "discounted_arr",
        q_money(total),
        data,
        params,
        (DatasetKind.ARR, DatasetKind.INVOICES, DatasetKind.CUSTOMERS),
        ledger.last_month,
    )


@metric("legacy_price_book_arr", "currency", "ARR billed on non-current (legacy) price books", "decrease", ("segment",))
def _legacy_arr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    if not data.has(DatasetKind.PRICE_BOOKS):
        raise MetricUnavailable("Price books required")
    pw = price_waterfall(data, segment=params.get("segment"))
    return _bv(
        "legacy_price_book_arr",
        pw.legacy.legacy_arr,
        data,
        params,
        (DatasetKind.ARR, DatasetKind.PRICE_BOOKS),
        pw.period_end,
    )


@metric("addressable_churned_arr", "currency", "Trailing-12-month voluntary churned ARR", "decrease", ("segment",))
def _addressable_churn(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _t12_churned(data, params, {ChurnType.VOLUNTARY})
    return _bv(
        "addressable_churned_arr", v, data, params, (DatasetKind.ARR, DatasetKind.CHURN, DatasetKind.CUSTOMERS), end
    )


@metric(
    "failed_payment_churned_arr", "currency", "Trailing-12-month ARR lost to failed payments", "decrease", ("segment",)
)
def _failed_payment(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _t12_churned(data, params, {ChurnType.INVOLUNTARY_PAYMENT})
    return _bv("failed_payment_churned_arr", v, data, params, (DatasetKind.ARR, DatasetKind.CHURN), end)


@metric(
    "annual_contracted_arr",
    "currency",
    "Trailing-12-month contraction ARR from retained customers",
    "decrease",
    ("segment",),
)
def _contracted(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    ledger = _ledger(data)
    ids = _segment_ids(data, params)
    end = ledger.last_month
    start = add_months(end, -12)
    total = sum(
        (
            ledger.arr(c, start) - ledger.arr(c, end)
            for c in ledger.active(start)
            if (ids is None or c in ids) and 0 < ledger.arr(c, end) < ledger.arr(c, start)
        ),
        ZERO,
    )
    return _bv("annual_contracted_arr", q_money(total), data, params, (DatasetKind.ARR,), end)


def _t12_pnl(data: CompanyData, *accounts: PnLAccount) -> tuple[Decimal, date]:
    pnl = pnl_by_month(data.records(DatasetKind.PNL))
    if not pnl:
        raise MetricUnavailable("No P&L data")
    end = max(pnl)
    months = month_range(add_months(end, -11), end)
    if any(m not in pnl for m in months):
        raise MetricUnavailable("P&L has missing months in the trailing 12 months")
    return q_money(sum_accounts(pnl, months, *accounts)), end


@metric("s_and_m_expense", "currency", "Trailing-12-month sales and marketing expense", "decrease")
def _sm(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _t12_pnl(data, PnLAccount.SALES_MARKETING)
    return _bv("s_and_m_expense", v, data, params, (DatasetKind.PNL,), end)


@metric("subscription_cogs", "currency", "Trailing-12-month hosting, third-party and support COGS", "decrease")
def _sub_cogs(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _t12_pnl(data, *SUB_COGS)
    return _bv("subscription_cogs", v, data, params, (DatasetKind.PNL,), end)


@metric("hosting_cost", "currency", "Trailing-12-month hosting COGS", "decrease")
def _hosting(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _t12_pnl(data, PnLAccount.COGS_HOSTING)
    return _bv("hosting_cost", v, data, params, (DatasetKind.PNL,), end)


def _function_cost(data: CompanyData, function: str) -> tuple[Decimal, date]:
    rows = [h for h in data.records(DatasetKind.HEADCOUNT) if h.function == function]
    if not rows:
        raise MetricUnavailable(f"No headcount for function {function!r}")
    last = max(h.month for h in rows)
    cost = sum((h.fte * h.fully_loaded_annual_cost_per_fte for h in rows if h.month == last), ZERO)
    return q_money(cost), last


@metric("support_cost_tier1", "currency", "Annualised tier-1 support headcount cost at the latest month", "decrease")
def _tier1(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _function_cost(data, "support_tier1")
    return _bv("support_cost_tier1", v, data, params, (DatasetKind.HEADCOUNT, DatasetKind.SUPPORT), end)


@metric("finance_ops_cost", "currency", "Annualised finance-operations headcount cost at the latest month", "decrease")
def _finops(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    v, end = _function_cost(data, "finance_ops")
    return _bv("finance_ops_cost", v, data, params, (DatasetKind.HEADCOUNT,), end)


def _saas_ratio(name: str, data: CompanyData, params: dict[str, str], kinds: tuple[DatasetKind, ...]) -> BaselineValue:
    m = compute_saas_metrics(data).metrics[name]
    if m.value is None:
        raise MetricUnavailable(m.note or f"{name} unavailable")
    return _bv(name, m.value, data, params, kinds, m.period_end)


@metric("subscription_gross_margin", "ratio", "Trailing-12-month subscription gross margin", "increase")
def _gm(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    return _saas_ratio("subscription_gross_margin", data, params, (DatasetKind.PNL,))


@metric("grr", "ratio", "Trailing-12-month gross revenue retention (opening cohort)", "increase")
def _grr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    return _saas_ratio("grr", data, params, (DatasetKind.ARR,))


@metric("nrr", "ratio", "Trailing-12-month net revenue retention (opening cohort)", "increase")
def _nrr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    return _saas_ratio("nrr", data, params, (DatasetKind.ARR,))


@metric("cac_payback_months", "months", "CAC payback in months (prior-quarter S&M over net new ARR x GM)", "decrease")
def _payback(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    return _saas_ratio("cac_payback_months", data, params, (DatasetKind.PNL, DatasetKind.ARR))


@metric("segment_grr", "ratio", "Trailing-12-month GRR for one segment", "increase", ("segment",))
def _segment_grr(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    seg = params.get("segment")
    if not seg:
        raise MetricUnavailable("segment parameter required")
    ra = analyse_retention(data)
    row = next((s for s in ra.segments if s.dimension == "segment" and s.value == seg), None)
    if row is None or row.grr is None:
        raise MetricUnavailable(f"No GRR for segment {seg!r}")
    return _bv("segment_grr", row.grr, data, params, (DatasetKind.ARR, DatasetKind.CUSTOMERS), ra.period_end)


@metric(
    "involuntary_churn_share", "ratio", "Share of trailing-12-month churned ARR lost to failed payments", "decrease"
)
def _invol_share(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    ra = analyse_retention(data)
    if ra.involuntary_payment_share is None:
        raise MetricUnavailable("No churn in period")
    return _bv(
        "involuntary_churn_share",
        ra.involuntary_payment_share,
        data,
        params,
        (DatasetKind.ARR, DatasetKind.CHURN),
        ra.period_end,
    )


@metric(
    "avg_new_deal_discount_rate",
    "ratio",
    "Average on-invoice discount on new deals (24 months)",
    "decrease",
    ("segment",),
)
def _avg_disc(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    pw = price_waterfall(data, segment=params.get("segment"))
    rows = [d for d in pw.dispersion if d.mean_discount_rate is not None]
    if not rows:
        raise MetricUnavailable("No new deals")
    n = sum(d.lines for d in rows)
    v = sum((d.mean_discount_rate * d.lines for d in rows if d.mean_discount_rate is not None), ZERO) / n
    return _bv(
        "avg_new_deal_discount_rate",
        q_ratio(v),
        data,
        params,
        (DatasetKind.INVOICES, DatasetKind.CUSTOMERS),
        pw.period_end,
    )


@metric("renewal_uplift_realization", "ratio", "Realized renewal uplift divided by contracted uplift", "increase")
def _uplift_real(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    pw = price_waterfall(data)
    v = pw.renewal_realization.realization_ratio
    if v is None:
        raise MetricUnavailable("Renewal realization requires invoices and contracts")
    return _bv(
        "renewal_uplift_realization", v, data, params, (DatasetKind.INVOICES, DatasetKind.CONTRACTS), pw.period_end
    )


@metric("legacy_arr_share", "ratio", "Share of ARR on legacy price books", "decrease")
def _legacy_share(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    pw = price_waterfall(data)
    if pw.legacy.legacy_arr_share is None:
        raise MetricUnavailable("No ARR")
    return _bv(
        "legacy_arr_share",
        pw.legacy.legacy_arr_share,
        data,
        params,
        (DatasetKind.ARR, DatasetKind.PRICE_BOOKS),
        pw.period_end,
    )


@metric(
    "tier1_tickets_per_customer_month",
    "ratio",
    "Tier-1 tickets per active customer per month (last 3 months)",
    "decrease",
)
def _t1_rate(data: CompanyData, params: dict[str, str]) -> BaselineValue:
    ledger = _ledger(data)
    months = month_range(add_months(ledger.last_month, -2), ledger.last_month)
    tickets = [
        t
        for t in data.records(DatasetKind.SUPPORT)
        if t.tier == "tier1" and date(t.created_at.year, t.created_at.month, 1) in months
    ]
    cm = sum(len(ledger.active(m)) for m in months)
    if not cm:
        raise MetricUnavailable("No active customers")
    return _bv(
        "tier1_tickets_per_customer_month",
        q_ratio(Decimal(len(tickets)) / cm),
        data,
        params,
        (DatasetKind.SUPPORT, DatasetKind.ARR),
        ledger.last_month,
    )


LEVER_METRICS: dict[Lever, set[str]] = {
    Lever.PRICING: {"renewing_arr", "discounted_arr", "legacy_price_book_arr", "total_arr"},
    Lever.RETENTION: {"addressable_churned_arr", "failed_payment_churned_arr", "annual_contracted_arr"},
    Lever.SALES_EFFICIENCY: {"s_and_m_expense"},
    Lever.GROSS_MARGIN: {"subscription_cogs", "hosting_cost"},
    Lever.AI_AUTOMATION: {"support_cost_tier1", "finance_ops_cost", "subscription_cogs"},
}


class DerivedBaseline(BaseModel):
    baseline: BaselineValue
    ebitda_flow_through: Decimal
    flow_through_rule: str
    evidence_ids: list[str]


def compute_metric(data: CompanyData, name: str, params: dict[str, str] | None = None) -> BaselineValue:
    if name not in REGISTRY:
        raise MetricUnavailable(f"Unknown metric {name!r}; valid: {sorted(REGISTRY)}")
    spec = REGISTRY[name]
    params = {k: v for k, v in (params or {}).items() if v}
    unknown = set(params) - set(spec.params)
    if unknown:
        raise MetricUnavailable(f"Metric {name!r} does not accept params {sorted(unknown)}")
    return spec.fn(data, params)


def derive_baseline(
    data: CompanyData, lever: Lever, metric_name: str, params: dict[str, str] | None, policy: PolicyConfig
) -> DerivedBaseline:
    allowed = LEVER_METRICS[lever]
    if metric_name not in allowed:
        raise MetricUnavailable(
            f"Metric {metric_name!r} is not a valid baseline for lever {lever.value!r}; valid: {sorted(allowed)}"
        )
    baseline = compute_metric(data, metric_name, params)
    rule = policy.flow_through[lever]
    evidence = list(baseline.evidence_ids)
    if rule.type == "constant":
        assert rule.value is not None
        ft, desc = rule.value, f"policy constant {rule.value} ({policy.version})"
    else:
        assert rule.metric is not None
        m = compute_metric(data, rule.metric)
        ft, desc = m.value, f"company metric {rule.metric}={m.value} ({policy.version})"
        evidence += [e for e in m.evidence_ids if e not in evidence]
    if not (Decimal(0) < ft <= Decimal(1)):
        raise MetricUnavailable(f"Flow-through {ft} outside (0, 1]")
    return DerivedBaseline(baseline=baseline, ebitda_flow_through=ft, flow_through_rule=desc, evidence_ids=evidence)


# Cost baselines that contain other cost baselines: sizing both would count the contained cost twice.
BASELINE_CONTAINS: dict[str, frozenset[str]] = {
    "subscription_cogs": frozenset({"hosting_cost", "support_cost_tier1"}),
}


def baseline_overlap(m1: str, p1: dict[str, str], m2: str, p2: dict[str, str]) -> str | None:
    """Why two opportunity baselines overlap, or None. Different segments of one metric are disjoint."""
    if m1 == m2:
        if p1 == p2:
            return f"same baseline {m1}"
        if not p1 or not p2:
            return f"{m1} for a segment is part of the unscoped {m1}"
        return None
    for outer, inner in ((m1, m2), (m2, m1)):
        if inner in BASELINE_CONTAINS.get(outer, frozenset()):
            return f"{inner} is part of {outer}"
    return None
