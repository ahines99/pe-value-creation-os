"""PVC-021: SaaS metrics. Hand-built ledger with hand-computed results, plus fixture recovery."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.domain.calc import add_months, month_range
from pe_value_os.domain.metrics import compute_saas_metrics
from pe_value_os.domain.source_models import Customer, CustomerArrMonth, PnLAccount, PnLLine
from tests.helpers import D, make_data

MONTHS = month_range(date(2025, 1, 1), date(2026, 1, 1))  # 13 months; year_ago = 2025-01, end = 2026-01


def arr_series(cid, fn):
    return [
        CustomerArrMonth(company_id="mini", customer_id=cid, month=m, arr=D(fn(m)), product="p", price_book_id="pb")
        for m in MONTHS
        if fn(m) > 0
    ]


def ledger_rows():
    rows = []
    rows += arr_series("A", lambda m: 100)
    rows += arr_series("B", lambda m: 200 if m < date(2025, 7, 1) else 0)  # churns
    rows += arr_series("C", lambda m: 100 if m < date(2025, 7, 1) else 150)  # expands
    rows += arr_series("D", lambda m: 0 if m < date(2025, 3, 1) else 50)  # new
    rows += arr_series("E", lambda m: 80 if m < date(2025, 10, 1) else 60)  # contracts
    return rows


def pnl_rows(sub=D(100), hosting=D(10), third=D(5), support=D(5), sm=D(50), other=D(20)):
    out = []
    for m in month_range(date(2024, 2, 1), date(2026, 1, 1)):
        for acct, amt in [
            (PnLAccount.REVENUE_SUBSCRIPTION, sub),
            (PnLAccount.COGS_HOSTING, hosting),
            (PnLAccount.COGS_THIRD_PARTY, third),
            (PnLAccount.COGS_SUPPORT, support),
            (PnLAccount.SALES_MARKETING, sm),
            (PnLAccount.GENERAL_ADMIN, other),
        ]:
            out.append(PnLLine(company_id="mini", month=m, account=acct, amount=amt, currency="USD"))
    return out


def customers():
    return [
        Customer(
            company_id="mini",
            customer_id=c,
            name=c,
            segment="smb",
            size_band="1-50",
            acquisition_channel="inbound",
            first_contract_date=date(2024, 1, 1),
        )
        for c in "ABCDE"
    ]


def test_bridge_grr_nrr_hand_computed():
    m = compute_saas_metrics(make_data(arr=ledger_rows(), pnl=pnl_rows(), customers=customers()))
    # Opening (2025-01) = A100 + B200 + C100 + E80 = 480; D is new.
    assert m.value("arr_bridge_opening") == D("480.00")
    assert m.value("arr_bridge_new") == D("50.00")
    assert m.value("arr_bridge_expansion") == D("50.00")
    assert m.value("arr_bridge_contraction") == D("20.00")
    assert m.value("arr_bridge_churn") == D("200.00")
    assert m.value("arr_bridge_closing") == D("360.00")  # 480 + 50 + 50 - 20 - 200
    # GRR = (100 + 0 + 100 + 60) / 480 = 0.541666 -> 0.5417 ; NRR = (100 + 0 + 150 + 60) / 480 = 0.645833 -> 0.6458
    assert m.value("grr") == D("0.5417")
    assert m.value("nrr") == D("0.6458")
    # Subscription GM = (100 - 10 - 5 - 5) / 100 = 0.8
    assert m.value("subscription_gross_margin") == D("0.8000")
    assert m.metrics["grr"].variant == "t12m_opening_cohort"
    assert m.metrics["grr"].evidence_ids == ["ev-arr"]


def test_cac_payback_hand_computed():
    # Last complete quarter ending 2026-01 is Q4 2025 (Oct-Dec). Net new ARR in Q4 = ARR(Dec) - ARR(Sep).
    # Sep: A100 + C150 + D50 + E80 = 380; Dec: A100 + C150 + D50 + E60 = 360 -> negative -> undefined.
    m = compute_saas_metrics(make_data(arr=ledger_rows(), pnl=pnl_rows(), customers=customers()))
    assert m.value("cac_payback_months") is None and m.metrics["cac_payback_months"].note
    # Add customer F worth 120 from 2025-11: net new Q4 = 480 - 380 = 100.
    rows = ledger_rows() + arr_series("F", lambda mm: 120 if mm >= date(2025, 11, 1) else 0)
    m = compute_saas_metrics(make_data(arr=rows, pnl=pnl_rows(), customers=customers()))
    # Prior quarter (Jul-Sep) S&M = 3 x 50 = 150; Q4 GM = 0.8 -> 150 / (100 x 0.8) x 12 = 22.5
    assert m.value("cac_payback_months") == D("22.5000")
    assert m.metrics["cac_payback_months"].period_start == date(2025, 10, 1)


def test_incomplete_pnl_returns_none_not_approximation():
    pnl = [p for p in pnl_rows() if p.month != date(2025, 6, 1)]
    m = compute_saas_metrics(make_data(arr=ledger_rows(), pnl=pnl, customers=customers()))
    assert m.value("subscription_gross_margin") is None
    assert "2025-06-01" in m.metrics["subscription_gross_margin"].note
    assert m.value("rule_of_40") is None


def test_rule_of_40_and_magic_number_hand_computed():
    m = compute_saas_metrics(make_data(arr=ledger_rows(), pnl=pnl_rows(), customers=customers()))
    # Flat revenue: growth 0; EBITDA margin = (100 - 10 - 5 - 5 - 50 - 20) / 100 = 0.1 -> rule of 40 = 0.1
    assert m.value("revenue_growth") == D("0.0000")
    assert m.value("ebitda_margin") == D("0.1000")
    assert m.value("rule_of_40") == D("0.1000")
    assert m.value("magic_number") == D("0.0000")  # flat quarterly revenue
    assert m.value("burn_multiple") is None  # net new ARR over the year is negative


FIXTURES = Path(__file__).parent / "fixtures" / "companies"


@pytest.mark.parametrize("cid", ["acme-healthy", "beacon-pricing", "cedar-churn"])
def test_fixture_arr_matches_ground_truth(cid):
    truth = json.loads((FIXTURES / cid / "planted.json").read_text())["ground_truth"]
    m = compute_saas_metrics(FixtureAdapter().load(cid))
    assert m.value("arr") == Decimal(truth["arr_last_month"])
    assert m.value("customers") == truth["active_customers_last_month"]
    b = m.metrics
    assert (
        b["arr_bridge_opening"].value
        + b["arr_bridge_new"].value
        + b["arr_bridge_expansion"].value
        - b["arr_bridge_contraction"].value
        - b["arr_bridge_churn"].value
    ) == b["arr_bridge_closing"].value


def test_churn_company_has_worst_grr():
    a = FixtureAdapter()
    grr = {c: compute_saas_metrics(a.load(c)).value("grr") for c in ("acme-healthy", "beacon-pricing", "cedar-churn")}
    assert min(grr, key=grr.get) == "cedar-churn"


def test_period_end_parameter_aligns_all_metrics():
    data = FixtureAdapter().load("acme-healthy")
    end = add_months(date(2026, 8, 1), -3)
    m = compute_saas_metrics(data, period_end=end)
    assert all(v.period_end == end for v in m.metrics.values())
