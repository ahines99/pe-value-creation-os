"""Retention analysis (PVC-022): cohorts, segment decomposition, churn types, and leading indicators.

Definitions follow skills/customer-retention/SKILL.md. GRR uses the opening-cohort method, so it can never
exceed 1 and never exceeds NRR.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import mean

from pydantic import BaseModel, Field

from .calc import ZERO, ArrLedger, add_months, month_range, months_between, q_money, q_ratio
from .dataset import CompanyData
from .source_models import ChurnEvent, ChurnType, Customer, DatasetKind, SupportTicket, UsageMonth

CALC_VERSION = "retention/1"


class SegmentRetention(BaseModel):
    dimension: str
    value: str
    opening_arr: Decimal
    grr: Decimal | None
    nrr: Decimal | None
    churned_arr: Decimal
    contracted_arr: Decimal
    logos_opening: int
    logos_churned: int


class CohortCurve(BaseModel):
    cohort: str
    starting_logos: int
    starting_arr: Decimal
    logo_retention: dict[int, Decimal | None]
    dollar_retention: dict[int, Decimal | None]


class LeadingIndicator(BaseModel):
    name: str
    churned_value: Decimal | None
    retained_value: Decimal | None
    lead_months: str
    signal: bool
    evidence_ids: list[str]


class RetentionAnalysis(BaseModel):
    company_id: str
    period_start: date
    period_end: date
    calc_version: str = CALC_VERSION
    grr: Decimal | None
    nrr: Decimal | None
    logo_retention: Decimal | None
    churned_arr_by_type: dict[str, Decimal]
    involuntary_payment_share: Decimal | None
    contracted_arr: Decimal
    segments: list[SegmentRetention]
    cohorts: list[CohortCurve]
    early_life_churn_overrepresentation: Decimal | None
    reason_codes: dict[str, int]
    leading_indicators: list[LeadingIndicator]
    evidence_ids: list[str] = Field(default_factory=list)

    def worst_segment(self, dimension: str = "segment") -> SegmentRetention | None:
        rows = [s for s in self.segments if s.dimension == dimension and s.grr is not None and s.opening_arr > 0]
        return min(rows, key=lambda s: (s.grr, s.value)) if rows else None


def _segment_rows(
    ledger: ArrLedger, start: date, end: date, customers: dict[str, Customer], churn_ids: set[str]
) -> list[SegmentRetention]:
    out: list[SegmentRetention] = []
    for dim in ("segment", "size_band", "acquisition_channel"):
        groups: dict[str, set[str]] = defaultdict(set)
        for cid, cust in customers.items():
            groups[str(getattr(cust, dim))].add(cid)
        for value, ids in sorted(groups.items()):
            opening, kept, closing = ledger.retention(start, end, ids)
            active = [c for c in ledger.active(start) if c in ids]
            churned = [c for c in active if ledger.arr(c, end) == 0]
            contracted = sum(
                (
                    ledger.arr(c, start) - ledger.arr(c, end)
                    for c in active
                    if 0 < ledger.arr(c, end) < ledger.arr(c, start)
                ),
                ZERO,
            )
            out.append(
                SegmentRetention(
                    dimension=dim,
                    value=value,
                    opening_arr=q_money(opening),
                    grr=q_ratio(kept / opening) if opening else None,
                    nrr=q_ratio(closing / opening) if opening else None,
                    churned_arr=q_money(sum((ledger.arr(c, start) for c in churned), ZERO)),
                    contracted_arr=q_money(contracted),
                    logos_opening=len(active),
                    logos_churned=len(churned),
                )
            )
    return out


def _cohorts(ledger: ArrLedger, customers: dict[str, Customer]) -> list[CohortCurve]:
    first_seen: dict[str, date] = {}
    for cid, series in ledger.by_customer.items():
        positive = [m for m, v in series.items() if v > 0]
        if positive:
            first_seen[cid] = min(positive)
    by_cohort: dict[str, list[str]] = defaultdict(list)
    for cid, m in first_seen.items():
        if m == ledger.first_month:
            continue  # existed before the data window; not a true cohort
        by_cohort[f"{m.year}-Q{(m.month - 1) // 3 + 1}"].append(cid)
    curves: list[CohortCurve] = []
    for cohort, ids in sorted(by_cohort.items()):
        start_arr = sum((ledger.arr(c, first_seen[c]) for c in ids), ZERO)
        logo: dict[int, Decimal | None] = {}
        dollar: dict[int, Decimal | None] = {}
        for off in (3, 6, 12):
            eligible = [c for c in ids if add_months(first_seen[c], off) <= ledger.last_month]
            if not eligible:
                logo[off] = dollar[off] = None
                continue
            alive = [c for c in eligible if ledger.arr(c, add_months(first_seen[c], off)) > 0]
            base = sum((ledger.arr(c, first_seen[c]) for c in eligible), ZERO)
            now = sum((ledger.arr(c, add_months(first_seen[c], off)) for c in eligible), ZERO)
            logo[off] = q_ratio(Decimal(len(alive)) / len(eligible))
            dollar[off] = q_ratio(now / base) if base else None
        curves.append(
            CohortCurve(
                cohort=cohort,
                starting_logos=len(ids),
                starting_arr=q_money(start_arr),
                logo_retention=logo,
                dollar_retention=dollar,
            )
        )
    return curves


def _leading_indicators(
    data: CompanyData, ledger: ArrLedger, churn: list[ChurnEvent], start: date, end: date
) -> list[LeadingIndicator]:
    usage: list[UsageMonth] = [u for u in data.records(DatasetKind.USAGE) if u.feature == "core"]
    tickets: list[SupportTicket] = data.records(DatasetKind.SUPPORT)
    vol = {c.customer_id: c.month for c in churn if c.churn_type == ChurnType.VOLUNTARY and start < c.month <= end}
    out: list[LeadingIndicator] = []
    if usage and vol:
        util: dict[tuple[str, date], float] = {
            (u.customer_id, u.month): u.active_users / u.licensed_users for u in usage if u.licensed_users
        }
        churned_vals = [
            util[(c, add_months(m, -k))] for c, m in vol.items() for k in (1, 2, 3) if (c, add_months(m, -k)) in util
        ]
        window = month_range(add_months(start, 1), end)
        retained_ids = [c for c in ledger.active(end) if c not in vol]
        retained_vals = [util[(c, m)] for c in retained_ids for m in window if (c, m) in util]
        cv_, rv = (mean(churned_vals) if churned_vals else None), (mean(retained_vals) if retained_vals else None)
        out.append(
            LeadingIndicator(
                name="core_seat_utilisation",
                churned_value=_d(cv_),
                retained_value=_d(rv),
                lead_months="1-3",
                signal=cv_ is not None and rv is not None and cv_ < rv * 0.8,
                evidence_ids=data.evidence(DatasetKind.USAGE, DatasetKind.CHURN),
            )
        )
    if tickets and vol:
        per_cm: dict[tuple[str, date], int] = defaultdict(int)
        for t in tickets:
            per_cm[(t.customer_id, date(t.created_at.year, t.created_at.month, 1))] += 1
        churned_rate = [per_cm[(c, add_months(m, -k))] for c, m in vol.items() for k in (1, 2, 3)]
        window = month_range(add_months(start, 1), end)
        retained_ids = [c for c in ledger.active(end) if c not in vol]
        retained_rate = [per_cm[(c, m)] for c in retained_ids for m in window if ledger.arr(c, m) > 0]
        cr, rr = (mean(churned_rate) if churned_rate else None), (mean(retained_rate) if retained_rate else None)
        out.append(
            LeadingIndicator(
                name="support_tickets_per_customer_month",
                churned_value=_d(cr),
                retained_value=_d(rr),
                lead_months="1-3",
                signal=cr is not None and rr is not None and cr > rr * 1.25,
                evidence_ids=data.evidence(DatasetKind.SUPPORT, DatasetKind.CHURN),
            )
        )
    return out


def _d(x: float | None) -> Decimal | None:
    return None if x is None else q_ratio(Decimal(str(x)))


def analyse_retention(data: CompanyData, period_end: date | None = None) -> RetentionAnalysis:
    ledger = ArrLedger(data.records(DatasetKind.ARR))
    customers: dict[str, Customer] = {c.customer_id: c for c in data.records(DatasetKind.CUSTOMERS)}
    churn: list[ChurnEvent] = data.records(DatasetKind.CHURN)
    end = period_end or ledger.last_month
    start = add_months(end, -12)
    opening, kept, closing = ledger.retention(start, end)
    active_start = ledger.active(start)
    logos_kept = sum(1 for c in active_start if ledger.arr(c, end) > 0)

    by_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
    churned_ids: set[str] = set()
    for ev in churn:
        if start < ev.month <= end:
            by_type[ev.churn_type.value] += ledger.last_arr_before(ev.customer_id, ev.month)
            churned_ids.add(ev.customer_id)
    total_churned = sum(by_type.values(), ZERO)
    contracted = sum(
        (
            ledger.arr(c, start) - ledger.arr(c, end)
            for c in active_start
            if 0 < ledger.arr(c, end) < ledger.arr(c, start)
        ),
        ZERO,
    )

    # Early-life over-representation: share of voluntary churn at first renewal vs share of base in first year.
    early_churn = total_vol = 0
    for ev in churn:
        if ev.churn_type == ChurnType.VOLUNTARY and start < ev.month <= end and ev.customer_id in customers:
            total_vol += 1
            early_churn += months_between(customers[ev.customer_id].first_contract_date, ev.month) <= 13
    base_ids = [c for c in active_start if c in customers]
    early_base = sum(1 for c in base_ids if months_between(customers[c].first_contract_date, start) < 12)
    overrep = None
    if total_vol and base_ids and early_base:
        overrep = q_ratio((Decimal(early_churn) / total_vol) / (Decimal(early_base) / len(base_ids)))

    reasons: dict[str, int] = defaultdict(int)
    for ev in churn:
        if start < ev.month <= end and ev.churn_type == ChurnType.VOLUNTARY:
            reasons[ev.reason_code or "unknown"] += 1

    return RetentionAnalysis(
        company_id=data.company_id,
        period_start=start,
        period_end=end,
        grr=q_ratio(kept / opening) if opening else None,
        nrr=q_ratio(closing / opening) if opening else None,
        logo_retention=q_ratio(Decimal(logos_kept) / len(active_start)) if active_start else None,
        churned_arr_by_type={k: q_money(v) for k, v in sorted(by_type.items())},
        involuntary_payment_share=q_ratio(by_type.get(ChurnType.INVOLUNTARY_PAYMENT.value, ZERO) / total_churned)
        if total_churned
        else None,
        contracted_arr=q_money(contracted),
        segments=_segment_rows(ledger, start, end, customers, churned_ids),
        cohorts=_cohorts(ledger, customers),
        early_life_churn_overrepresentation=overrep,
        reason_codes=dict(sorted(reasons.items())),
        leading_indicators=_leading_indicators(data, ledger, churn, start, end),
        evidence_ids=data.evidence(DatasetKind.ARR, DatasetKind.CUSTOMERS, DatasetKind.CHURN),
    )
