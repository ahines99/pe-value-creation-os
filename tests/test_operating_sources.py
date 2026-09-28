"""Source eligibility, independent worked amounts, corrections and timing limits."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.build_operating_plan_example import example as plan_example
from scripts.build_operating_sources_example import example
from scripts.build_underwriting_example import example as case_example

from pe_value_os.diligence.operating_sources import OperatingSourceBook, source_forecast
from pe_value_os.diligence.operating_sources_render import build_sources_report, render_sources
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.underwriting import Entry, UnderwritingCase, ledger, totals


def report(book=None, case=None, plan=None):
    return source_forecast(book or example(), case or case_example(), plan or plan_example())


def base(result):
    return next(s for s in result["scenarios"] if s["scenario_id"] == "base")


def revise(book, edit):
    raw = book.model_dump(mode="json")
    edit(raw)
    return OperatingSourceBook.model_validate(raw)


def test_contract_deadlines_permission_caps_and_term_end():
    result = base(report())
    rows = {d["record_id"]: d for d in result["decisions"] if d["kind"] == "renewal"}
    assert rows["early-90-day"]["reason"] == "Notice deadline missed"
    assert rows["prohibited"]["reason"] == "Contract permission absent"
    assert rows["unknown-rights"]["reason"] == "Contract permission absent"
    assert rows["spring-capped"]["eligible"] and rows["short-term"]["eligible"]
    entries = tuple(Entry.model_validate(e) for e in result["entries"] if e["reference"] == "short-term")
    feb = totals(entries, date(2027, 2, 1), date(2027, 2, 28))
    # 150,000 * 3% contractual cap * 65% capture * 99.5% retained.
    assert feb["gross_price_benefit"] == Decimal("2910.38")
    assert feb["revenue_leakage"] == -750
    assert feb["variable_cost"] == Decimal("-432.08")
    assert feb["incremental_ebitda"] == Decimal("1728.30")
    july = totals(entries, date(2027, 7, 1), date(2027, 7, 31))
    assert july["incremental_ebitda"] == 0
    assert july["operating_cash"] == Decimal("2160.38")  # final June receipt survives expiry
    assert totals(entries, date(2027, 8, 1), date(2028, 9, 30))["incremental_ebitda"] == 0


def test_service_quality_recontacts_qa_vendor_floor_and_release():
    result = base(report())
    jan, feb, march = result["monthly"][3:6]
    # 7,000 coverage-capped contacts * 60% resolution * 12/60 - 80 QA = 760 hours.
    assert jan["capacity_hours"] == 760
    assert jan["cost_removed"] == 0
    # $18k available spend, released Feb 15; 14/28 days => $9k.
    assert feb["cost_removed"] == 9000
    assert march["cost_removed"] == 18000
    review = next(d for d in result["decisions"] if d["kind"] == "service" and d["month"] == date(2027, 3, 1))
    assert review["excluded_queues"] == ["sensitive"]
    assert review["quality_eligible_contacts"] == 8000
    assert review["net_full_month_hours"] == 760


def test_invoice_exclusions_reversal_and_zero_earnings():
    result = base(report())
    invoices = [Entry.model_validate(e) for e in result["entries"] if e["initiative_id"] == "collections-timing"]
    # 600k open + (300k open - 150k disputed), each accelerated by 15%.
    assert sum(e.amount for e in invoices if e.component == "working_capital_cash" and e.amount > 0) == 112500
    assert sum(e.amount for e in invoices if e.component == "working_capital_cash") == 0
    assert not any(e.component in {"gross_price_benefit", "revenue_leakage", "cost_removed"} for e in invoices)
    rows = {d["record_id"]: d for d in result["decisions"] if d["kind"] == "invoice"}
    assert not rows["already-paid"]["eligible"]
    assert not rows["full-dispute"]["eligible"]
    assert not rows["window-missed"]["eligible"]


def test_missing_service_month_is_explicit_and_keeps_original_costs():
    book = revise(example(), lambda r: r.update(service_months=[]))
    result = base(report(book))
    assert result["total"]["capacity_hours"] == result["total"]["cost_removed"] == 0
    assert len([d for d in result["decisions"] if d["reason"] == "Missing service month"]) == 24
    original = next(s for s in case_example().scenarios if s.scenario_id == "base")
    ids = frozenset(d.initiative_id for d in original.drivers)
    costs = ledger(case_example(), original, ids, ids)
    assert {e.model_dump_json() for e in costs} <= {
        Entry.model_validate(e).model_dump_json() for e in result["entries"]
    }


def test_no_vendor_release_can_create_capacity_but_never_spend_savings():
    raw = example().model_dump(mode="json")
    for row in raw["service_months"]:
        row.update(release_on=None, release_evidence=None)
    result = base(report(OperatingSourceBook.model_validate(raw)))
    assert result["total"]["capacity_hours"] > 0
    assert result["total"]["cost_removed"] == 0
    assert result["total"]["recurring_cost"] < 0


def test_blocked_capacity_keeps_all_commitments_and_blocks_source_credit():
    case = case_example()
    raw = plan_example().model_dump(mode="json")
    for resource in raw["resources"]:
        resource["weekly_hours"] = [None] * 15
    plan = OperatingPlan.model_validate(raw)
    book = revise(example(), lambda r: r.update(plan_sha256=fingerprint(plan)))
    result = base(report(book, case, plan))
    assert result["total"]["incremental_ebitda"] < 0
    for name in ("gross_price_benefit", "revenue_leakage", "cost_removed", "capacity_hours", "working_capital_cash"):
        assert result["total"][name] == 0


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda r: r.update(renewal_monthly_revenue_control="1"), "renewal revenue"),
        (lambda r: r.update(invoice_open_balance_control="1"), "invoice open"),
        (lambda r: r["renewals"].append(r["renewals"][0]), "duplicate"),
        (lambda r: r["invoices"].append(r["invoices"][0]), "duplicate"),
        (lambda r: r["service_months"].append(r["service_months"][0]), "duplicate"),
        (lambda r: r["service_months"][0].update(contacts_control=1), "contacts do not reconcile"),
        (lambda r: r["service_months"][0]["queues"][0].update(resolved_count=101), "quality counts"),
        (lambda r: r["service_months"][0].update(vendor_minimum="100001"), "vendor minimum"),
        (lambda r: r["invoices"][0].update(disputed="9999999"), "invoice credits"),
        (
            lambda r: r["invoices"][0].update(issued_on="2026-10-02", due_on="2026-10-03", accelerated_on="2026-10-04"),
            "source cutoff",
        ),
        (lambda r: r.update(classification="permissioned_operating_records"), "Input should be"),
    ],
)
def test_invalid_populations_rejected(change, match):
    with pytest.raises(ValueError, match=match):
        revise(example(), change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("underwriting_sha256", "0" * 64),
        ("plan_sha256", "0" * 64),
        ("case_id", "other-case"),
        ("company", "other-company"),
        ("currency", "EUR"),
    ],
)
def test_exact_binding_required(field, value):
    with pytest.raises(ValueError, match="exact case"):
        report(revise(example(), lambda r: r.update({field: value})))


def test_revised_source_changes_fingerprint_and_result_without_rewriting_inputs():
    book, case, plan = example(), case_example(), plan_example()
    snapshots = tuple(x.model_dump_json() for x in (book, case, plan))
    original = report(book, case, plan)
    revised = revise(book, lambda r: r["renewals"][1].update(uplift_cap="0"))
    updated = report(revised, case, plan)
    assert updated["report_sha256"] != original["report_sha256"]
    assert base(updated)["total"]["incremental_ebitda"] < base(original)["total"]["incremental_ebitda"]
    assert tuple(x.model_dump_json() for x in (book, case, plan)) == snapshots
    assert updated["actual_company_realized_value"] is None


def test_finite_partial_month_accrual_and_cash_settlement():
    case = case_example()
    scenario = next(s for s in case.scenarios if s.scenario_id == "base")
    driver = next(d for d in scenario.drivers if d.kind == "pricing")
    entries = ledger(
        case, scenario, frozenset({driver.initiative_id}), benefit_end_dates={driver.initiative_id: date(2027, 1, 15)}
    )
    pricing = tuple(e for e in entries if e.reference == driver.initiative_id)
    jan = totals(pricing, date(2027, 1, 1), date(2027, 1, 31))
    feb = totals(pricing, date(2027, 2, 1), date(2027, 2, 28))
    # 1m * 6% * 65% * 99.5% * 15/31, rounded once cumulatively.
    assert jan["gross_price_benefit"] == Decimal("18776.61")
    assert jan["revenue_leakage"] == Decimal("-2419.35")
    assert feb["incremental_ebitda"] == 0
    assert feb["operating_cash"] == Decimal("16357.26")


def test_collection_end_window_rejected_so_reversal_cannot_disappear():
    case = case_example()
    scenario = case.scenarios[0]
    with pytest.raises(ValueError, match="reversals cannot be truncated"):
        ledger(case, scenario, frozenset({"collections-timing"}), benefit_end_dates={"collections-timing": case.start})


def test_shared_assumption_alias_cannot_corrupt_source_projection():
    case_raw = case_example().model_dump(mode="json")
    for scenario in case_raw["scenarios"]:
        scenario["drivers"][0]["capture"] = scenario["drivers"][0]["uplift"]
    case = UnderwritingCase.model_validate(case_raw)
    plan_raw = plan_example().model_dump(mode="json")
    plan_raw["underwriting_sha256"] = fingerprint(case)
    plan = OperatingPlan.model_validate(plan_raw)
    book = revise(example(), lambda r: r.update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan)))
    with pytest.raises(ValueError, match="distinct assumption"):
        report(book, case, plan)


def test_fixture_is_reproducible():
    saved = OperatingSourceBook.model_validate_json(
        Path("data/constructed/progress/operating-sources.json").read_bytes()
    )
    assert saved == example()


def test_rendered_review_updates_counts_dispositions_and_escapes_source_text():
    book = revise(example(), lambda r: r["renewals"][1].update(record_id="<script>source</script>", uplift_cap="0"))
    rendered = render_sources(report(book), "review.json")
    assert "1 of 5 contracts" in rendered
    assert "No positive permissible uplift" in rendered
    assert "<script>source</script>" not in rendered
    assert "&lt;script&gt;source&lt;/script&gt;" in rendered


def test_report_builder_protects_all_inputs_and_rejects_stale_binding(tmp_path, capsys):
    from pe_value_os.cli import build_parser

    source, case, plan = (tmp_path / name for name in ("sources.json", "case.json", "plan.json"))
    for path, record in ((source, example()), (case, case_example()), (plan, plan_example())):
        path.write_text(record.model_dump_json(), encoding="utf-8")
    for path in (source, case, plan):
        with pytest.raises(ValueError, match="overwrite"):
            build_sources_report(source, case, plan, path)
    args = build_parser().parse_args(
        [
            "operating-sources",
            "--sources",
            str(source),
            "--underwriting",
            str(case),
            "--operating-plan",
            str(plan),
            "--output",
            str(tmp_path / "out/report"),
        ]
    )
    assert args.fn(args) == 0
    assert (tmp_path / "out/report.html").exists()
    assert (tmp_path / "out/report.json").exists()
    source.write_text(revise(example(), lambda r: r.update(plan_sha256="0" * 64)).model_dump_json(), encoding="utf-8")
    args.output = str(tmp_path / "rejected/report")
    assert args.fn(args) == 2
    assert not (tmp_path / "rejected").exists()
    assert "exact case bindings" in capsys.readouterr().err


def test_high_recontacts_or_qa_load_cannot_create_negative_or_positive_false_savings():
    raw = example().model_dump(mode="json")
    for service in raw["service_months"]:
        service["qa_hours"] = "100000"
        for queue in service["queues"]:
            queue["recontact_count"] = queue["resolved_count"]
    result = base(report(OperatingSourceBook.model_validate(raw)))
    assert result["total"]["capacity_hours"] == 0
    assert result["total"]["cost_removed"] == 0
    assert result["total"]["recurring_cost"] < 0


def test_complete_months_day100_total_and_settlements_reconcile_to_same_entries():
    for scenario in report()["scenarios"]:
        entries = tuple(Entry.model_validate(e) for e in scenario["entries"])
        for month in scenario["monthly"]:
            assert month["incremental_ebitda"] == totals(entries, month["start"], month["end"])["incremental_ebitda"]
        for component in ("incremental_ebitda", "pre_tax_cash_proxy", "working_capital_cash"):
            assert sum(month[component] for month in scenario["monthly"]) == scenario["total"][component]
        assert scenario["day_100"] == totals(entries, date(2026, 10, 1), date(2027, 1, 8))


def test_contract_beyond_forecast_horizon_keeps_its_term_and_lagged_cash():
    book = revise(example(), lambda r: r["renewals"][1].update(term_ends_on="2030-03-31"))
    result = base(report(book))
    decision = next(d for d in result["decisions"] if d.get("record_id") == "spring-capped")
    assert decision["term_ends_on"] == date(2030, 3, 31)
    entries = tuple(Entry.model_validate(e) for e in result["entries"] if e["reference"] == "spring-capped")
    assert totals(entries, date(2028, 9, 1), date(2028, 9, 30))["incremental_ebitda"] == 4174
    tail = totals(entries, date(2028, 10, 1), date(2030, 3, 31))
    assert tail["incremental_ebitda"] == 0
    assert tail["operating_cash"] == Decimal("5217.50")
