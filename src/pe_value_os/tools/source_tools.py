"""Read-only source-data tools, one registration function per capability boundary (PVC-051, PVC-052, PVC-057).

Every tool takes `company_id`, is scope-checked, returns aggregated typed data with evidence ids, and never
returns raw untrusted free text (document bodies and CRM notes stay out of tool results).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from statistics import mean
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel, Field

from ..domain.calc import ArrLedger, add_months, month_range, q_money, q_ratio
from ..domain.source_models import CompanyProfile, DatasetKind
from ._runtime import company_data, governed


def parse_period(period: str | None, default: date) -> date:
    """'YYYY-MM' -> first day of that month. None -> default."""
    if not period:
        return default
    try:
        y, m = period.split("-")
        return date(int(y), int(m), 1)
    except ValueError as e:
        raise ValueError(f"period must be 'YYYY-MM', got {period!r}") from e


class CompanyProfileResult(BaseModel):
    profile: CompanyProfile
    reference_date: date
    data_inventory: list[dict[str, Any]]
    evidence_ids: list[str]


class FinancialMonth(BaseModel):
    month: date
    accounts: dict[str, Decimal]


class FinancialsResult(BaseModel):
    company_id: str
    currency: str
    months: list[FinancialMonth]
    missing_months: list[date]
    evidence_ids: list[str]


class UsageResult(BaseModel):
    company_id: str
    month: date
    active_customers: int
    core_utilisation_by_segment: dict[str, Decimal]
    advanced_feature_adoption: Decimal | None = Field(description="Share of pro customers with any advanced usage")
    evidence_ids: list[str]


class SupportResult(BaseModel):
    company_id: str
    period_start: date
    period_end: date
    tickets: int
    tickets_by_category: dict[str, int]
    tickets_by_tier: dict[str, int]
    avg_handle_minutes_by_tier: dict[str, Decimal]
    avg_csat: Decimal | None
    tickets_per_customer_month: Decimal | None
    evidence_ids: list[str]


class ChurnSummaryResult(BaseModel):
    company_id: str
    period_start: date
    period_end: date
    churned_logos_by_type: dict[str, int]
    voluntary_reason_codes: dict[str, int]
    renewal_opportunities: dict[str, int]
    note: str = "Reason codes are sales-entered and low-trust on their own; free-text notes are not returned."
    evidence_ids: list[str]


def register_portco_financials(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_company_profile")
    def get_company_profile(company_id: str) -> CompanyProfileResult:
        """Business model, scale, fiscal calendar and data inventory for one portfolio company."""
        data = company_data(company_id)
        return CompanyProfileResult(
            profile=data.profile,
            reference_date=data.reference_date,
            data_inventory=data.inventory(),
            evidence_ids=[data.profile_evidence_id],
        )

    @mcp.tool()
    @governed("get_financials")
    def get_financials(
        company_id: str, period_start: str | None = None, period_end: str | None = None
    ) -> FinancialsResult:
        """Monthly P&L lines by account between two months ('YYYY-MM', inclusive). Amounts are in the company
        currency. Missing months are listed, never filled in."""
        data = company_data(company_id)
        lines = data.records(DatasetKind.PNL)
        if not lines:
            raise ValueError("No P&L data for this company")
        last = max(p.month for p in lines)
        end = parse_period(period_end, last)
        start = parse_period(period_start, add_months(end, -11))
        by: dict[date, dict[str, Decimal]] = defaultdict(dict)
        for p in lines:
            if start <= p.month <= end:
                by[p.month][p.account.value] = by[p.month].get(p.account.value, Decimal(0)) + p.amount
        months = month_range(start, end)
        return FinancialsResult(
            company_id=company_id,
            currency=data.profile.currency,
            months=[
                FinancialMonth(month=m, accounts={k: q_money(v) for k, v in sorted(by[m].items())})
                for m in months
                if m in by
            ],
            missing_months=[m for m in months if m not in by],
            evidence_ids=data.evidence(DatasetKind.PNL),
        )


def register_crm(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_churn_summary")
    def get_churn_summary(company_id: str, period: str | None = None) -> ChurnSummaryResult:
        """Trailing-12-month churned logos by churn type, voluntary reason codes, and renewal win/loss counts."""
        data = company_data(company_id)
        ledger = ArrLedger(data.records(DatasetKind.ARR))
        end = parse_period(period, ledger.last_month)
        start = add_months(end, -12)
        churn = [c for c in data.records(DatasetKind.CHURN) if start < c.month <= end]
        renewals = [
            o
            for o in data.records(DatasetKind.CRM_OPPORTUNITIES)
            if o.opportunity_type == "renewal" and o.close_date and start < o.close_date <= add_months(end, 1)
        ]
        return ChurnSummaryResult(
            company_id=company_id,
            period_start=start,
            period_end=end,
            churned_logos_by_type=dict(Counter(c.churn_type.value for c in churn)),
            voluntary_reason_codes=dict(
                Counter(c.reason_code or "unknown" for c in churn if c.churn_type.value == "voluntary")
            ),
            renewal_opportunities=dict(Counter(o.stage for o in renewals)),
            evidence_ids=data.evidence(DatasetKind.CHURN, DatasetKind.CRM_OPPORTUNITIES),
        )


def register_product_analytics(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_usage_metrics")
    def get_usage_metrics(company_id: str, period: str | None = None) -> UsageResult:
        """Core seat utilisation by segment and advanced-feature adoption for one month ('YYYY-MM')."""
        data = company_data(company_id)
        usage = data.records(DatasetKind.USAGE)
        if not usage:
            raise ValueError("No product usage data for this company")
        m = parse_period(period, max(u.month for u in usage))
        seg = {c.customer_id: c.segment for c in data.records(DatasetKind.CUSTOMERS)}
        core = [u for u in usage if u.month == m and u.feature == "core" and u.licensed_users]
        by_seg: dict[str, list[float]] = defaultdict(list)
        for u in core:
            by_seg[seg.get(u.customer_id, "unknown")].append(u.active_users / u.licensed_users)
        adv = {u.customer_id for u in usage if u.month == m and u.feature == "advanced"}
        adv_active = {u.customer_id for u in usage if u.month == m and u.feature == "advanced" and u.active_users}
        return UsageResult(
            company_id=company_id,
            month=m,
            active_customers=len(core),
            core_utilisation_by_segment={k: q_ratio(Decimal(str(mean(v)))) for k, v in sorted(by_seg.items())},
            advanced_feature_adoption=q_ratio(Decimal(len(adv_active)) / len(adv)) if adv else None,
            evidence_ids=data.evidence(DatasetKind.USAGE, DatasetKind.CUSTOMERS),
        )


def register_support(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_support_metrics")
    def get_support_metrics(company_id: str, period: str | None = None) -> SupportResult:
        """Trailing-12-month ticket volumes by category and tier, handle time, CSAT, and tickets per customer."""
        data = company_data(company_id)
        tickets = data.records(DatasetKind.SUPPORT)
        if not tickets:
            raise ValueError("No support data for this company")
        ledger = ArrLedger(data.records(DatasetKind.ARR))
        end = parse_period(
            period,
            ledger.last_month
            if ledger.months
            else max(date(t.created_at.year, t.created_at.month, 1) for t in tickets),
        )
        months = month_range(add_months(end, -11), end)
        window = [t for t in tickets if date(t.created_at.year, t.created_at.month, 1) in set(months)]
        handle: dict[str, list[Decimal]] = defaultdict(list)
        for t in window:
            handle[t.tier].append(t.handle_minutes)
        csat = [t.csat for t in window if t.csat is not None]
        cm = sum(len(ledger.active(m)) for m in months) if ledger.months else 0
        return SupportResult(
            company_id=company_id,
            period_start=months[0],
            period_end=end,
            tickets=len(window),
            tickets_by_category=dict(sorted(Counter(t.category for t in window).items())),
            tickets_by_tier=dict(sorted(Counter(t.tier for t in window).items())),
            avg_handle_minutes_by_tier={k: q_ratio(sum(v, Decimal(0)) / len(v)) for k, v in sorted(handle.items())},
            avg_csat=q_ratio(Decimal(sum(csat)) / len(csat)) if csat else None,
            tickets_per_customer_month=q_ratio(Decimal(len(window)) / cm) if cm else None,
            evidence_ids=data.evidence(DatasetKind.SUPPORT, DatasetKind.ARR),
        )
