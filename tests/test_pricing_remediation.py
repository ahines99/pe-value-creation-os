"""Audit A03/A12: product-level pricing is independent of invoice row order and splitting."""

from datetime import date
from itertools import permutations

import pytest

from pe_value_os.domain.baselines import baseline_overlap, compute_metric
from pe_value_os.domain.calc import MetricUnavailable
from pe_value_os.domain.pricing import price_waterfall
from pe_value_os.domain.source_models import ContractTerm, CustomerArrMonth, InvoiceLine
from tests.helpers import D, make_data


def invoice(product, year, *, gross="200", net="100", quantity="1", line_id="1"):
    return InvoiceLine(
        company_id="mini",
        invoice_id=f"i-{year}",
        line_id=f"{product}-{line_id}",
        customer_id="c",
        invoice_date=date(year, 1, 1),
        product=product,
        price_book_id="book",
        quantity=D(quantity),
        list_price_per_unit=D(gross) / D(quantity),
        on_invoice_discount=D(gross) - D(net),
        net_amount=D(net),
        currency="USD",
        deal_size_band="small",
    )


def arr(product, amount):
    return CustomerArrMonth(
        company_id="mini",
        customer_id="c",
        month=date(2026, 1, 1),
        arr=D(amount),
        product=product,
        price_book_id="book",
    )


def test_product_discount_baseline_is_permutation_invariant():
    lines = [invoice("p", 2026), invoice("q", 2026, gross="900", net="900")]
    for ordered in permutations(lines):
        data = make_data(arr=[arr("p", "100"), arr("q", "900")], invoices=list(ordered))
        # Product P: 100 / (1 - .5) = 200. Product Q: 900 / (1 - 0) = 900.
        assert compute_metric(data, "discounted_arr").value == D("1100.00")


@pytest.mark.parametrize("contained", ["discounted_arr", "renewing_arr", "legacy_price_book_arr"])
def test_aggregate_arr_cannot_be_added_to_its_contained_scopes(contained):
    assert baseline_overlap("total_arr", {}, contained, {"segment": "smb"})
    assert baseline_overlap(contained, {}, "total_arr", {"segment": "smb"})
    assert baseline_overlap("total_arr", {"segment": "smb"}, contained, {"segment": "smb"})
    assert baseline_overlap("total_arr", {"segment": "smb"}, contained, {"segment": "enterprise"}) is None


def test_discount_baseline_aggregates_same_product_lines_and_ignores_future_invoices():
    lines = [
        invoice("p", 2026, gross="100", net="50", quantity=".5", line_id="1"),
        invoice("p", 2026, gross="300", net="250", quantity="1.5", line_id="2"),
        invoice("p", 2027, gross="500", net="50"),
    ]
    for ordered in permutations(lines):
        data = make_data(arr=[arr("p", "300")], invoices=list(ordered))
        assert compute_metric(data, "discounted_arr").value == D("400.00")


@pytest.mark.parametrize("lines", [[invoice("q", 2026)], [invoice("p", 2026, net="0")]])
def test_discount_baseline_refuses_unmatched_or_fully_discounted_positive_arr(lines):
    with pytest.raises(MetricUnavailable):
        compute_metric(make_data(arr=[arr("p", "100")], invoices=lines), "discounted_arr")


def test_renewals_match_each_product_and_aggregate_split_lines():
    contract = ContractTerm(
        company_id="mini",
        contract_id="ct",
        customer_id="c",
        start_date=date(2025, 1, 1),
        end_date=date(2026, 12, 31),
        contracted_uplift_rate=D(".05"),
        notice_days=30,
    )
    # Product P has a split prior invoice; product Q changes at the same dates.
    lines = [
        invoice("p", 2025, gross="1000", net="500", quantity="5", line_id="1"),
        invoice("p", 2025, gross="1000", net="500", quantity="5", line_id="2"),
        invoice("q", 2025, gross="2000", net="1000", quantity="10"),
        invoice("p", 2026, gross="2000", net="1050", quantity="10"),
        invoice("q", 2026, gross="2000", net="1050", quantity="10"),
    ]
    for ordered in permutations(lines):
        result = price_waterfall(make_data(invoices=list(ordered), contracts=[contract])).renewal_realization
        assert result.renewals == 2
        assert result.mean_realized_uplift == D(".05")
        assert result.mean_contracted_uplift == D(".05")
        assert result.realization_ratio == D("1")
