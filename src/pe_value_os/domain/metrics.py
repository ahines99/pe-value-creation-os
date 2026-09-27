"""SaaS growth-efficiency metrics (PVC-021).

Definitions follow skills/saas-unit-economics/SKILL.md. Every metric reports its variant, period, and the
evidence it was computed from. Periods must align; a metric that cannot be computed returns value=None
with a note rather than an approximation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from .calc import (
    ALL_COSTS,
    REVENUE,
    SUB_COGS,
    ZERO,
    ArrLedger,
    MetricValue,
    add_months,
    month_range,
    pnl_by_month,
    q_money,
    q_ratio,
    quarter_start,
    sum_accounts,
)
from .dataset import CompanyData
from .source_models import DatasetKind, PnLAccount

CALC_VERSION = "saas-metrics/1"


class SaasMetrics(BaseModel):
    company_id: str
    period_end: date
    calc_version: str = CALC_VERSION
    metrics: dict[str, MetricValue]

    def value(self, name: str) -> Decimal | None:
        return self.metrics[name].value


def _last_complete_quarter(last_month: date) -> tuple[date, date]:
    """(first month, last month) of the latest calendar quarter fully covered by data ending at last_month."""
    qs = quarter_start(last_month)
    if add_months(qs, 2) > last_month:
        qs = add_months(qs, -3)
    return qs, add_months(qs, 2)


def compute_saas_metrics(data: CompanyData, period_end: date | None = None) -> SaasMetrics:
    ledger = ArrLedger(data.records(DatasetKind.ARR))
    pnl = pnl_by_month(data.records(DatasetKind.PNL))
    ev_arr = data.evidence(DatasetKind.ARR)
    ev_pnl = data.evidence(DatasetKind.PNL)
    ev_both = ev_arr + ev_pnl
    end = period_end or ledger.last_month
    t12_start = add_months(end, -11)
    t12 = month_range(t12_start, end)
    prior12 = month_range(add_months(end, -23), add_months(end, -12))
    year_ago = add_months(end, -12)
    pnl_months = set(pnl)
    missing_pnl = [m for m in t12 if m not in pnl_months]

    m: dict[str, MetricValue] = {}

    def put(
        name: str,
        value: Decimal | None,
        unit: str,
        variant: str,
        ev: list[str],
        start: date | None = None,
        note: str | None = None,
    ) -> None:
        m[name] = MetricValue(
            name=name,
            value=value,
            unit=unit,
            period_start=start or t12_start,
            period_end=end,
            variant=variant,
            evidence_ids=ev,
            note=note,
        )

    # ARR bridge (T12M)
    br = ledger.bridge(year_ago, end)
    for k, v in br.items():
        put(f"arr_bridge_{k}", q_money(v), "currency", "t12m_monthly_accumulation", ev_arr, start=year_ago)
    put("arr", q_money(ledger.total(end)), "currency", "month_end", ev_arr, start=end)
    put("customers", Decimal(len(ledger.active(end))), "count", "month_end", ev_arr, start=end)

    # Retention (cohort method, trailing 12 months)
    opening, kept, closing = ledger.retention(year_ago, end)
    grr = q_ratio(kept / opening) if opening else None
    nrr = q_ratio(closing / opening) if opening else None
    put("grr", grr, "ratio", "t12m_opening_cohort", ev_arr, start=year_ago)
    put("nrr", nrr, "ratio", "t12m_opening_cohort", ev_arr, start=year_ago)

    # Gross margin (subscription only)
    pnl_note = f"P&L missing months: {', '.join(x.isoformat() for x in missing_pnl)}" if missing_pnl else None
    sub_rev = sum_accounts(pnl, t12, PnLAccount.REVENUE_SUBSCRIPTION)
    sub_cogs = sum_accounts(pnl, t12, *SUB_COGS)
    gm = q_ratio((sub_rev - sub_cogs) / sub_rev) if sub_rev > 0 and not missing_pnl else None
    put("subscription_gross_margin", gm, "ratio", "t12m_hosting_thirdparty_support_cogs", ev_pnl, note=pnl_note)

    # CAC payback: prior-quarter S&M / (net new ARR in quarter x GM) x 12
    q_first, q_last = _last_complete_quarter(end)
    pq = month_range(add_months(q_first, -3), add_months(q_first, -1))
    sm_prior_q = sum_accounts(pnl, pq, PnLAccount.SALES_MARKETING)
    net_new_q = ledger.total(q_last) - ledger.total(add_months(q_first, -1))
    q_gm = _gm(pnl, month_range(q_first, q_last))
    if net_new_q > 0 and q_gm is not None and q_gm > 0 and all(x in pnl_months for x in pq):
        payback: Decimal | None = q_ratio(sm_prior_q / (net_new_q * q_gm) * 12)
        note = None
    else:
        payback, note = None, "Net new ARR or gross margin not positive, or P&L incomplete; payback undefined"
    put(
        "cac_payback_months",
        payback,
        "months",
        "prior_quarter_sm_over_net_new_arr_x_gm",
        ev_both,
        start=q_first,
        note=note,
    )

    # LTV / CAC
    customers_end = len(ledger.active(end))
    new_logos = sum(
        1
        for c, series in ledger.by_customer.items()
        if any(series.get(mm, ZERO) > 0 and ledger.arr(c, add_months(mm, -1)) == 0 for mm in t12)
        and ledger.arr(c, year_ago) == 0
    )
    sm_t12 = sum_accounts(pnl, t12, PnLAccount.SALES_MARKETING)
    if (
        customers_end
        and new_logos
        and grr is not None
        and grr < 1
        and gm is not None
        and gm > 0
        and sm_t12 > 0
        and not missing_pnl
    ):
        arpa = ledger.total(end) / customers_end
        ltv = arpa * gm / (1 - grr)
        cac = sm_t12 / new_logos
        put(
            "ltv_to_cac",
            q_ratio(ltv / cac),
            "ratio",
            "arpa_x_gm_over_annual_dollar_churn__t12m_sm_per_new_logo",
            ev_both,
        )
    else:
        put(
            "ltv_to_cac",
            None,
            "ratio",
            "arpa_x_gm_over_annual_dollar_churn__t12m_sm_per_new_logo",
            ev_both,
            note="Insufficient inputs (no churn, no new logos, no S&M spend, non-positive margin, or incomplete P&L)",
        )

    # Magic number: (rev_q - rev_{q-1}) x 4 / S&M_{q-1}
    rev_q = sum_accounts(pnl, month_range(q_first, q_last), *REVENUE)
    rev_pq = sum_accounts(pnl, pq, *REVENUE)
    both_quarters = all(x in pnl_months for x in [*pq, *month_range(q_first, q_last)])
    magic = q_ratio((rev_q - rev_pq) * 4 / sm_prior_q) if sm_prior_q > 0 and both_quarters else None
    put("magic_number", magic, "ratio", "total_revenue_qoq_x4_over_prior_quarter_sm", ev_pnl, start=q_first)

    # Burn multiple: net burn / net new ARR (T12M), burn proxied by negative EBITDA
    ebitda_t12 = sum_accounts(pnl, t12, *REVENUE) - sum_accounts(pnl, t12, *ALL_COSTS)
    net_new_t12 = br["closing"] - br["opening"]
    burn = max(ZERO, -ebitda_t12)
    if net_new_t12 > 0 and not missing_pnl:
        put("burn_multiple", q_ratio(burn / net_new_t12), "ratio", "negative_ebitda_proxy_over_net_new_arr", ev_both)
    else:
        put(
            "burn_multiple",
            None,
            "ratio",
            "negative_ebitda_proxy_over_net_new_arr",
            ev_both,
            note="Net new ARR not positive or P&L incomplete",
        )

    # Rule of 40: revenue growth + EBITDA margin
    rev_t12 = sum_accounts(pnl, t12, *REVENUE)
    rev_prior = sum_accounts(pnl, prior12, *REVENUE)
    margin = ebitda_t12 / rev_t12 if rev_t12 > 0 else None
    if all(x in pnl_months for x in prior12) and rev_prior > 0 and margin is not None and not missing_pnl:
        growth, variant = rev_t12 / rev_prior - 1, "t12m_revenue_growth_plus_ebitda_margin"
    elif margin is not None and ledger.total(year_ago) > 0 and not missing_pnl:
        growth, variant = ledger.total(end) / ledger.total(year_ago) - 1, "arr_yoy_growth_plus_ebitda_margin"
    else:
        growth, variant = None, "unavailable"
    put("revenue_growth", q_ratio(growth) if growth is not None else None, "ratio", variant, ev_both)
    put(
        "ebitda_margin",
        q_ratio(margin) if margin is not None and not missing_pnl else None,
        "ratio",
        "t12m",
        ev_pnl,
        note=pnl_note,
    )
    put(
        "rule_of_40",
        q_ratio(growth + margin) if growth is not None and margin is not None else None,
        "ratio",
        variant,
        ev_both,
    )
    put("ebitda_t12m", q_money(ebitda_t12) if not missing_pnl else None, "currency", "t12m", ev_pnl, note=pnl_note)
    put("s_and_m_t12m", q_money(sm_t12) if not missing_pnl else None, "currency", "t12m", ev_pnl, note=pnl_note)
    put("new_logos_t12m", Decimal(new_logos), "count", "t12m", ev_arr)
    return SaasMetrics(company_id=data.company_id, period_end=end, metrics=m)


def _gm(pnl: dict[date, dict[PnLAccount, Decimal]], months: list[date]) -> Decimal | None:
    rev = sum_accounts(pnl, months, PnLAccount.REVENUE_SUBSCRIPTION)
    if rev <= 0 or any(mm not in pnl for mm in months):
        return None
    return (rev - sum_accounts(pnl, months, *SUB_COGS)) / rev
