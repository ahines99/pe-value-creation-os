"""PVC-023: price waterfall. Hand-computed mini waterfall plus planted-leak recovery."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.domain.pricing import price_waterfall
from pe_value_os.domain.source_models import Concession, Customer, CustomerArrMonth, InvoiceLine, PriceBook
from pe_value_os.policy import get_policy
from tests.helpers import D, make_data

FIXTURES = Path(__file__).parent / "fixtures" / "companies"


def mini():
    custs = [
        Customer(
            company_id="mini",
            customer_id="c1",
            name="c1",
            segment="smb",
            size_band="s",
            acquisition_channel="inbound",
            first_contract_date=date(2025, 3, 20),
        ),
        Customer(
            company_id="mini",
            customer_id="c2",
            name="c2",
            segment="mid_market",
            size_band="m",
            acquisition_channel="inbound",
            first_contract_date=date(2025, 5, 2),
        ),
    ]
    inv = [
        InvoiceLine(
            company_id="mini",
            invoice_id="i1",
            line_id="1",
            customer_id="c1",
            invoice_date=date(2025, 3, 20),
            product="p",
            price_book_id="pb-cur",
            quantity=D(10),
            list_price_per_unit=D(100),
            on_invoice_discount=D(100),
            net_amount=D(900),
            currency="USD",
            deal_size_band="small",
        ),
        InvoiceLine(
            company_id="mini",
            invoice_id="i2",
            line_id="1",
            customer_id="c2",
            invoice_date=date(2025, 5, 2),
            product="p",
            price_book_id="pb-old",
            quantity=D(5),
            list_price_per_unit=D(200),
            on_invoice_discount=D(300),
            net_amount=D(700),
            currency="USD",
            deal_size_band="small",
        ),
    ]
    conc = [
        Concession(
            company_id="mini",
            customer_id="c2",
            concession_date=date(2025, 6, 1),
            concession_type="credit",
            amount=D(50),
        )
    ]
    books = [
        PriceBook(
            company_id="mini",
            price_book_id="pb-cur",
            product="p",
            list_price_per_unit=D(100),
            effective_from=date(2025, 1, 1),
            is_current=True,
        ),
        PriceBook(
            company_id="mini",
            price_book_id="pb-old",
            product="p",
            list_price_per_unit=D(80),
            effective_from=date(2020, 1, 1),
            effective_to=date(2024, 12, 31),
            is_current=False,
        ),
    ]
    arr = [
        CustomerArrMonth(
            company_id="mini", customer_id="c1", month=date(2026, 1, 1), arr=D(900), product="p", price_book_id="pb-cur"
        ),
        CustomerArrMonth(
            company_id="mini", customer_id="c2", month=date(2026, 1, 1), arr=D(700), product="p", price_book_id="pb-old"
        ),
    ]
    return make_data(customers=custs, invoices=inv, concessions=conc, price_books=books, arr=arr)


def test_mini_waterfall_hand_computed():
    pw = price_waterfall(mini())
    t = pw.total
    # list 1000 + 1000 = 2000; discount 100 + 300 = 400; invoice 1600; concessions 50; pocket 1550
    assert (t.list_revenue, t.on_invoice_discount, t.invoice_revenue, t.off_invoice_concessions, t.pocket_revenue) == (
        D("2000.00"),
        D("400.00"),
        D("1600.00"),
        D("50.00"),
        D("1550.00"),
    )
    assert (t.on_invoice_leakage_rate, t.off_invoice_leakage_rate, t.pocket_price_realization) == (
        D("0.2000"),
        D("0.0250"),
        D("0.7750"),
    )
    assert pw.by_segment["mid_market"].pocket_revenue == D("650.00")
    # c1's deal is on 2025-03-20 (quarter-end window); c2 is not. Different segments -> no within-segment gap.
    assert pw.quarter_end_discount_gap is None
    # Legacy: c2 700 ARR of 1600 on the old book; uplift to current list = 700 x (100/80 - 1) = 175
    assert pw.legacy.legacy_arr == D("700.00") and pw.legacy.legacy_arr_share == D("0.4375")
    assert pw.legacy.uplift_to_current_list == D("175.00")
    assert pw.contract_constraints.available is False


def test_pricing_leak_recovered():
    pol = get_policy().screening
    pw = price_waterfall(FixtureAdapter().load("beacon-pricing"))
    planted = json.loads((FIXTURES / "beacon-pricing" / "planted.json").read_text())
    hd = pw.highest_dispersion()
    assert hd.segment == planted["planted"]["highest_dispersion_segment"] and hd.discount_sd > pol.discount_sd_max
    assert pw.quarter_end_discount_gap > pol.quarter_end_discount_gap_max
    assert pw.renewal_realization.realization_ratio < pol.renewal_uplift_realization_min
    # Ground truth averages every simulated uplift over 24 months; the service measures the last 12 months of
    # invoices below list price, so they agree within a tolerance rather than exactly.
    gt_uplift = Decimal(str(planted["ground_truth"]["mean_realized_uplift"]))
    assert abs(pw.renewal_realization.mean_realized_uplift - gt_uplift) < Decimal("0.003")
    assert pw.legacy.legacy_arr_share == Decimal(planted["ground_truth"]["legacy_arr_share_last_month"])
    assert pw.legacy.legacy_arr_share > pol.legacy_arr_share_max
    assert pw.evidence_ids


def test_healthy_company_has_no_leak_flags():
    pol = get_policy().screening
    pw = price_waterfall(FixtureAdapter().load("acme-healthy"))
    assert all(d.discount_sd <= pol.discount_sd_max for d in pw.dispersion if d.lines >= 10)
    assert pw.quarter_end_discount_gap <= pol.quarter_end_discount_gap_max
    assert pw.renewal_realization.realization_ratio >= pol.renewal_uplift_realization_min
    assert pw.legacy.legacy_arr_share <= pol.legacy_arr_share_max


def test_contract_constraints_reported():
    cc = price_waterfall(FixtureAdapter().load("beacon-pricing")).contract_constraints
    assert cc.available and cc.active_contracts > 0 and cc.capped_share is not None
