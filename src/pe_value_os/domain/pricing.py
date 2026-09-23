"""Price waterfall and leakage analysis (PVC-023).

List price -> on-invoice discount -> invoice price -> off-invoice concessions -> pocket price, by segment,
plus discount dispersion, quarter-end discounting, renewal-uplift realization, legacy price books, and the
contract constraints that limit price action. Definitions follow skills/pricing-value-creation/SKILL.md.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import pairwise
from statistics import mean, pstdev

from pydantic import BaseModel, Field

from .calc import ZERO, ArrLedger, add_months, cv, dec, is_quarter_end_window, month_of, pearson, q_money, q_ratio
from .dataset import CompanyData
from .source_models import Concession, ContractTerm, Customer, DatasetKind, InvoiceLine, PriceBook

CALC_VERSION = "price-waterfall/1"


class WaterfallLayer(BaseModel):
    list_revenue: Decimal
    on_invoice_discount: Decimal
    invoice_revenue: Decimal
    off_invoice_concessions: Decimal
    pocket_revenue: Decimal
    on_invoice_leakage_rate: Decimal | None
    off_invoice_leakage_rate: Decimal | None
    pocket_price_realization: Decimal | None


class Dispersion(BaseModel):
    segment: str
    lines: int
    mean_discount_rate: Decimal | None
    discount_sd: Decimal | None
    discount_cv: Decimal | None
    discount_size_correlation: Decimal | None
    comparable_groups: list[dict[str, str | int | None]]


class RenewalRealization(BaseModel):
    renewals: int
    mean_contracted_uplift: Decimal | None
    mean_realized_uplift: Decimal | None
    realization_ratio: Decimal | None


class LegacyPriceBooks(BaseModel):
    legacy_arr: Decimal
    total_arr: Decimal
    legacy_arr_share: Decimal | None
    uplift_to_current_list: Decimal


class ContractConstraints(BaseModel):
    available: bool
    active_contracts: int
    capped_share: Decimal | None = None
    cpi_linked_share: Decimal | None = None
    mfn_share: Decimal | None = None
    termination_for_convenience_share: Decimal | None = None
    min_notice_days: int | None = None
    max_notice_days: int | None = None


class PriceWaterfall(BaseModel):
    company_id: str
    period_start: date
    period_end: date
    segment: str | None
    calc_version: str = CALC_VERSION
    total: WaterfallLayer
    by_segment: dict[str, WaterfallLayer]
    dispersion: list[Dispersion]
    quarter_end_new_deal_discount: Decimal | None
    other_new_deal_discount: Decimal | None
    quarter_end_discount_gap: Decimal | None
    new_deals_analysed: int = 0
    renewal_realization: RenewalRealization
    legacy: LegacyPriceBooks
    contract_constraints: ContractConstraints
    evidence_ids: list[str] = Field(default_factory=list)

    def highest_dispersion(self) -> Dispersion | None:
        rows = [d for d in self.dispersion if d.discount_sd is not None and d.lines >= 10]
        return max(rows, key=lambda d: (d.discount_sd, d.segment)) if rows else None


def _layer(lines: list[InvoiceLine], concessions: list[Concession]) -> WaterfallLayer:
    lst = sum((ln.list_price_per_unit * ln.quantity for ln in lines), ZERO)
    disc = sum((ln.on_invoice_discount for ln in lines), ZERO)
    inv = sum((ln.net_amount for ln in lines), ZERO)
    conc = sum((c.amount for c in concessions), ZERO)
    pocket = inv - conc
    return WaterfallLayer(
        list_revenue=q_money(lst),
        on_invoice_discount=q_money(disc),
        invoice_revenue=q_money(inv),
        off_invoice_concessions=q_money(conc),
        pocket_revenue=q_money(pocket),
        on_invoice_leakage_rate=q_ratio(disc / lst) if lst else None,
        off_invoice_leakage_rate=q_ratio(conc / lst) if lst else None,
        pocket_price_realization=q_ratio(pocket / lst) if lst else None,
    )


def _rate(ln: InvoiceLine) -> float:
    gross = ln.list_price_per_unit * ln.quantity
    return float(ln.on_invoice_discount / gross) if gross else 0.0


def price_waterfall(data: CompanyData, period_end: date | None = None, segment: str | None = None) -> PriceWaterfall:
    customers: dict[str, Customer] = {c.customer_id: c for c in data.records(DatasetKind.CUSTOMERS)}
    invoices: list[InvoiceLine] = data.records(DatasetKind.INVOICES)
    concessions: list[Concession] = data.records(DatasetKind.CONCESSIONS)
    contracts: list[ContractTerm] = data.records(DatasetKind.CONTRACTS)
    books: dict[str, PriceBook] = {b.price_book_id: b for b in data.records(DatasetKind.PRICE_BOOKS)}
    ledger = ArrLedger(data.records(DatasetKind.ARR))
    end = period_end or (ledger.last_month if ledger.months else month_of(max(i.invoice_date for i in invoices)))
    start = add_months(end, -11)
    end_excl = add_months(end, 1)

    def seg_of(cid: str) -> str:
        return customers[cid].segment if cid in customers else "unknown"

    in_period = [i for i in invoices if start <= i.invoice_date < end_excl]
    conc_period = [c for c in concessions if start <= c.concession_date < end_excl]
    if segment:
        in_period = [i for i in in_period if seg_of(i.customer_id) == segment]
        conc_period = [c for c in conc_period if seg_of(c.customer_id) == segment]

    seg_lines: dict[str, list[InvoiceLine]] = defaultdict(list)
    seg_conc: dict[str, list[Concession]] = defaultdict(list)
    for ln in in_period:
        seg_lines[seg_of(ln.customer_id)].append(ln)
    for c in conc_period:
        seg_conc[seg_of(c.customer_id)].append(c)

    # Dispersion and quarter-end discounting are measured on new-deal invoices (where discount is negotiated)
    # over 24 months: renewal invoices carry uplift drift, not negotiated discount.
    deal_start = add_months(end, -23)
    new_deals = [
        ln
        for ln in invoices
        if deal_start <= ln.invoice_date < end_excl
        and ln.customer_id in customers
        and customers[ln.customer_id].first_contract_date == ln.invoice_date
        and (not segment or seg_of(ln.customer_id) == segment)
    ]
    deals_by_seg: dict[str, list[InvoiceLine]] = defaultdict(list)
    for ln in new_deals:
        deals_by_seg[seg_of(ln.customer_id)].append(ln)

    dispersion: list[Dispersion] = []
    for seg, lines in sorted(deals_by_seg.items()):
        rates = [_rate(ln) for ln in lines]
        groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        for ln in lines:
            groups[(ln.product, ln.deal_size_band)].append(_rate(ln))
        comparable = [
            {"product": p, "deal_size_band": b, "lines": len(v), "discount_sd": str(dec(pstdev(v)))}
            for (p, b), v in sorted(groups.items())
            if len(v) >= 5
        ]
        dispersion.append(
            Dispersion(
                segment=seg,
                lines=len(lines),
                mean_discount_rate=dec(mean(rates)) if rates else None,
                discount_sd=dec(pstdev(rates)) if len(rates) >= 2 else None,
                discount_cv=dec(cv(rates)),
                discount_size_correlation=dec(pearson([float(ln.quantity) for ln in lines], rates)),
                comparable_groups=comparable,
            )
        )

    # Quarter-end discounting: within-segment gap between quarter-end and other new deals, weighted by
    # quarter-end deal count (removes segment-mix effects).
    qe = [_rate(ln) for ln in new_deals if is_quarter_end_window(ln.invoice_date)]
    other = [_rate(ln) for ln in new_deals if not is_quarter_end_window(ln.invoice_date)]
    qe_mean, other_mean = (mean(qe) if qe else None), (mean(other) if other else None)
    gaps: list[tuple[float, int]] = []
    for lines in deals_by_seg.values():
        q_r = [_rate(ln) for ln in lines if is_quarter_end_window(ln.invoice_date)]
        o_r = [_rate(ln) for ln in lines if not is_quarter_end_window(ln.invoice_date)]
        if q_r and o_r:
            gaps.append((mean(q_r) - mean(o_r), len(q_r)))
    qe_gap = sum(g * n for g, n in gaps) / sum(n for _, n in gaps) if gaps else None

    # Renewal realization: unit net price change between consecutive annual invoices of the same customer
    by_cust: dict[str, list[InvoiceLine]] = defaultdict(list)
    for ln in invoices:
        by_cust[ln.customer_id].append(ln)
    contract_by_cust: dict[str, list[ContractTerm]] = defaultdict(list)
    for ct in contracts:
        contract_by_cust[ct.customer_id].append(ct)
    realized: list[float] = []  # every renewal, for the mean realized uplift
    matched_realized: list[float] = []  # renewals that also have a contracted uplift, for the realization ratio
    contracted: list[float] = []
    for cid, lines in by_cust.items():
        if segment and seg_of(cid) != segment:
            continue
        lines = sorted(lines, key=lambda ln: ln.invoice_date)
        for prev, cur in pairwise(lines):
            if not (start <= cur.invoice_date < end_excl):
                continue
            if (cur.invoice_date - prev.invoice_date).days < 330 or cur.product != prev.product:
                continue
            if not prev.quantity or not cur.quantity or prev.net_amount <= 0:
                continue  # free or zero-quantity periods (pilots, credits) have no unit price to compare
            prev_unit = prev.net_amount / prev.quantity
            if prev_unit >= prev.list_price_per_unit:
                continue  # already at list; uplift is not available
            change = float(cur.net_amount / cur.quantity / prev_unit - 1)
            realized.append(change)
            terms = [ct for ct in contract_by_cust.get(cid, []) if ct.start_date <= prev.invoice_date <= ct.end_date]
            if terms:
                t = terms[-1]
                up = t.contracted_uplift_rate
                if t.price_cap_rate is not None:
                    up = min(up, t.price_cap_rate)
                contracted.append(float(up))
                matched_realized.append(change)
    mean_real = dec(mean(realized)) if realized else None
    mean_contr = dec(mean(contracted)) if contracted else None
    # Compare like with like: realized and contracted uplift over the same renewals.
    matched_real = dec(mean(matched_realized)) if matched_realized else None
    ratio = q_ratio(matched_real / mean_contr) if matched_real is not None and mean_contr else None

    # Legacy price books (ARR at period end)
    arr_rows = [r for r in data.records(DatasetKind.ARR) if r.month == end]
    if segment:
        arr_rows = [r for r in arr_rows if seg_of(r.customer_id) == segment]
    current_by_product = {b.product: b for b in books.values() if b.is_current}
    legacy_arr = uplift = ZERO
    total_arr = sum((r.arr for r in arr_rows), ZERO)
    for r in arr_rows:
        book = books.get(r.price_book_id)
        if book and not book.is_current and r.product in current_by_product:
            legacy_arr += r.arr
            uplift += r.arr * (current_by_product[r.product].list_price_per_unit / book.list_price_per_unit - 1)

    active = [ct for ct in contracts if ct.start_date <= end <= ct.end_date or ct.start_date <= end_excl <= ct.end_date]
    n = len(active)
    constraints = ContractConstraints(
        available=bool(contracts),
        active_contracts=n,
        capped_share=q_ratio(Decimal(sum(ct.price_cap_rate is not None for ct in active)) / n) if n else None,
        cpi_linked_share=q_ratio(Decimal(sum(ct.cpi_linked for ct in active)) / n) if n else None,
        mfn_share=q_ratio(Decimal(sum(ct.mfn_clause for ct in active)) / n) if n else None,
        termination_for_convenience_share=q_ratio(Decimal(sum(ct.termination_for_convenience for ct in active)) / n)
        if n
        else None,
        min_notice_days=min((ct.notice_days for ct in active), default=None),
        max_notice_days=max((ct.notice_days for ct in active), default=None),
    )

    return PriceWaterfall(
        company_id=data.company_id,
        period_start=start,
        period_end=end,
        segment=segment,
        total=_layer(in_period, conc_period),
        by_segment={s: _layer(seg_lines[s], seg_conc.get(s, [])) for s in sorted(seg_lines)},
        dispersion=dispersion,
        quarter_end_new_deal_discount=dec(qe_mean),
        other_new_deal_discount=dec(other_mean),
        quarter_end_discount_gap=dec(qe_gap),
        new_deals_analysed=len(new_deals),
        renewal_realization=RenewalRealization(
            renewals=len(realized),
            mean_contracted_uplift=mean_contr,
            mean_realized_uplift=mean_real,
            realization_ratio=ratio,
        ),
        legacy=LegacyPriceBooks(
            legacy_arr=q_money(legacy_arr),
            total_arr=q_money(total_arr),
            legacy_arr_share=q_ratio(legacy_arr / total_arr) if total_arr else None,
            uplift_to_current_list=q_money(uplift),
        ),
        contract_constraints=constraints,
        evidence_ids=data.evidence(
            DatasetKind.INVOICES,
            DatasetKind.CONCESSIONS,
            DatasetKind.PRICE_BOOKS,
            DatasetKind.CONTRACTS,
            DatasetKind.ARR,
            DatasetKind.CUSTOMERS,
        ),
    )
