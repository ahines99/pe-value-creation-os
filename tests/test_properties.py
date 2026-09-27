"""PVC-027: property-based invariants for the calculation core."""

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from pe_value_os.domain.calc import ArrLedger, add_months
from pe_value_os.domain.project_models import Opportunity, ScenarioInputs
from pe_value_os.domain.services import size_value_case
from pe_value_os.domain.source_models import CustomerArrMonth

rates = st.decimals(min_value=0, max_value=1, places=4)
money = st.decimals(min_value=0, max_value=10_000_000, places=2)


def opp(baseline, ft, i, r, run):
    sc = ScenarioInputs(improvement_rate=i, realization_rate=r)
    return Opportunity(
        opportunity_id="o",
        run_id="r",
        company_id="c",
        lever="pricing",
        title="t",
        baseline_metric="renewing_arr",
        baseline_value=baseline,
        ebitda_flow_through=ft,
        low=sc,
        base=sc,
        high=sc,
        annual_run_cost=run,
        confidence="low",
        rationale="r",
        evidence_ids=["e"],
    )


@given(money, st.decimals(min_value=Decimal("0.01"), max_value=1, places=2), rates, rates, rates, money)
@settings(max_examples=200)
def test_sizing_monotonic_in_improvement(baseline, ft, i1, i2, r, run):
    lo, hi = sorted([i1, i2])
    a = size_value_case(opp(baseline, ft, lo, r, run)).annual_ebitda_base
    b = size_value_case(opp(baseline, ft, hi, r, run)).annual_ebitda_base
    assert a <= b


@given(money, money, rates, rates)
@settings(max_examples=200)
def test_sizing_monotonic_in_baseline_and_never_above_gross(b1, b2, i, r):
    lo, hi = sorted([b1, b2])
    a = size_value_case(opp(lo, Decimal(1), i, r, Decimal(0))).annual_ebitda_base
    b = size_value_case(opp(hi, Decimal(1), i, r, Decimal(0))).annual_ebitda_base
    assert a <= b <= hi


ledger_rows = st.lists(
    st.tuples(
        st.sampled_from(["a", "b", "c", "d", "e"]),
        st.integers(0, 12),
        st.decimals(min_value=0, max_value=100000, places=2),
    ),
    max_size=60,
)


def build(rows):
    start = date(2025, 1, 1)
    seen = {}
    for cid, off, arr in rows:
        seen[(cid, off)] = arr  # last write wins -> one row per customer-month
    return ArrLedger(
        CustomerArrMonth(
            company_id="x", customer_id=c, month=add_months(start, o), arr=a, product="p", price_book_id="pb"
        )
        for (c, o), a in seen.items()
    )


@given(ledger_rows)
@settings(max_examples=200)
def test_arr_bridge_identity(rows):
    led = build(rows)
    start, end = date(2025, 1, 1), date(2026, 1, 1)
    br = led.bridge(start, end)
    assert br["opening"] + br["new"] + br["expansion"] - br["contraction"] - br["churn"] == br["closing"]


@given(ledger_rows)
@settings(max_examples=200)
def test_grr_bounded_and_not_above_nrr(rows):
    led = build(rows)
    opening, kept, closing = led.retention(date(2025, 1, 1), date(2026, 1, 1))
    if opening:
        assert kept / opening <= 1
        assert kept <= closing
