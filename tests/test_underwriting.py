"""Independent worked economics, adverse cases, timing and source-policy boundaries."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.build_underwriting_example import example

from pe_value_os.diligence.underwriting import (
    Entry,
    UnderwritingCase,
    cash_profile,
    evaluate,
    ledger,
    month_start,
    totals,
)
from pe_value_os.diligence.underwriting_render import build_underwriting_report


def simplified(**values):
    raw = example().model_dump(mode="json")
    defaults = {
        "eligible-revenue": "3100",
        "uplift": ".10",
        "capture": "1",
        "churn": ".05",
        "contacts": "0",
        "cost-action": "0",
        "receivables": "0",
    }
    defaults.update(values)
    for scenario in raw["scenarios"]:
        scenario["costs"] = []
        for assumption in scenario["assumptions"]:
            if assumption["assumption_id"] in defaults:
                assumption["value"] = defaults[assumption["assumption_id"]]
        for driver in scenario["drivers"]:
            driver["effective_on"] = raw["start"]
            if driver["kind"] == "service":
                driver["cost_action"] = "none" if defaults["cost-action"] == "0" else "vendor_reduction"
    return UnderwritingCase.model_validate(raw)


def base(case):
    return next(s for s in evaluate(case)["scenarios"] if s["scenario_id"] == "base")


def test_worked_price_churn_interaction_cash_lags_and_day_100():
    result = base(simplified())
    october, november = result["monthly"][:2]
    # 3,100 * 10% * 95% retained = 294.50; lost baseline = 155.
    # Net revenue = 139.50; 20% variable expense = 27.90; EBITDA = 111.60.
    assert october["gross_price_benefit"] == Decimal("294.50")
    assert october["revenue_leakage"] == -155
    assert october["variable_cost"] == Decimal("-27.90")
    assert october["incremental_ebitda"] == Decimal("111.60")
    assert october["pre_tax_cash_proxy"] == Decimal("-27.90")
    assert november["pre_tax_cash_proxy"] == Decimal("111.60")
    assert result["day_100"]["incremental_ebitda"] == Decimal("363.60")
    assert result["day_100"]["pre_tax_cash_proxy"] == Decimal("195.30")
    assert result["year_one"]["incremental_ebitda"] == Decimal("1339.20")
    assert result["total"]["incremental_ebitda"] == Decimal("2678.40")
    assert result["total"]["pre_tax_cash_proxy"] == Decimal("2538.90")
    assert result["cash_settlement_after_horizon"] == Decimal("139.50")


def test_expense_payment_and_capex_are_not_double_counted():
    raw = simplified(uplift="0", churn="0", setup="100", capex="50", **{"service-fee": "60"}).model_dump(mode="json")
    months = raw["months"]
    for scenario in raw["scenarios"]:
        scenario["costs"] = [
            {
                "cost_id": "setup",
                "initiative_ids": ["service-automation"],
                "kind": "implementation",
                "amount": "setup",
                "recognized_on": "2026-10-10",
                "paid_on": "2026-11-10",
                "retained_if_excluded": False,
            },
            {
                "cost_id": "capex",
                "initiative_ids": ["service-automation"],
                "kind": "capex",
                "amount": "capex",
                "recognized_on": "2026-10-10",
                "paid_on": "2026-10-10",
                "retained_if_excluded": False,
            },
            # A recurring fee is one posting per month. The first is paid a month in arrears, the rest on the day.
            *[
                {
                    "cost_id": f"recurring-{i}",
                    "initiative_ids": ["service-automation"],
                    "kind": "recurring",
                    "amount": "service-fee",
                    "recognized_on": month_start(date(2026, 10, 1), i).replace(day=15).isoformat(),
                    "paid_on": "2026-11-20"
                    if i == 0
                    else month_start(date(2026, 10, 1), i).replace(day=15).isoformat(),
                    "retained_if_excluded": False,
                }
                for i in range(months)
            ],
        ]
    result = base(UnderwritingCase.model_validate(raw))
    assert result["monthly"][0]["incremental_ebitda"] == -160
    assert result["monthly"][0]["pre_tax_cash_proxy"] == -50
    assert result["monthly"][1]["pre_tax_cash_proxy"] == -220  # setup 100 + October's fee in arrears + November's
    assert result["total"]["incremental_ebitda"] == -100 - 60 * months
    assert result["total"]["pre_tax_cash_proxy"] == -150 - 60 * months


def test_recurring_cost_must_be_posted_every_month():
    """A single 'recurring' row would silently drop every later month's cost and overstate value."""
    raw = simplified(uplift="0", churn="0", **{"service-fee": "60"}).model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["costs"] = [
            {
                "cost_id": "recurring",
                "initiative_ids": ["service-automation"],
                "kind": "recurring",
                "amount": "service-fee",
                "recognized_on": "2026-10-15",
                "paid_on": "2026-10-15",
                "retained_if_excluded": False,
            }
        ]
    with pytest.raises(ValueError, match="must be posted every month"):
        UnderwritingCase.model_validate(raw)


def test_collection_timing_reverses_and_never_creates_earnings_or_ev():
    raw = simplified(uplift="0", churn="0", receivables="1000", accelerated=".20").model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["drivers"][2]["effective_on"] = "2026-10-05"
        scenario["drivers"][2]["counterfactual_collection_on"] = "2026-12-05"
    result = base(UnderwritingCase.model_validate(raw))
    assert result["monthly"][0]["pre_tax_cash_proxy"] == 200
    assert result["monthly"][2]["pre_tax_cash_proxy"] == -200
    assert result["total"]["pre_tax_cash_proxy"] == 0
    assert all(row["incremental_ebitda"] == 0 for row in result["monthly"])
    assert all(v["incremental_ev_sensitivity"] == 0 for v in result["valuation"])


def test_service_requires_cost_action_and_caps_removal_by_work_and_spend():
    no_action = simplified(uplift="0", churn="0", contacts="20000")
    result = base(no_action)
    assert result["monthly"][0]["capacity_hours"] == 840
    assert result["total"]["incremental_ebitda"] == 0
    bounded = simplified(
        uplift="0", churn="0", contacts="20000", **{"cost-action": "50000", "addressable-spend": "12000"}
    )
    assert base(bounded)["monthly"][0]["cost_removed"] == 12000
    work_limited = simplified(uplift="0", churn="0", contacts="20000", **{"cost-action": "50000"})
    assert base(work_limited)["monthly"][0]["cost_removed"] == 29400


def test_delay_preserves_incurred_fees_and_implementation_cost():
    original = example()
    raw = original.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        for driver in scenario["drivers"][:2]:
            driver["effective_on"] = "2027-06-01"
    delayed = UnderwritingCase.model_validate(raw)
    before, after = base(original), base(delayed)
    assert after["year_one"]["incremental_ebitda"] < before["year_one"]["incremental_ebitda"]
    for key in ("recurring_cost", "implementation_expense", "capex_cash"):
        assert before["year_one"][key] == after["year_one"][key]
    assert after["monthly"][0]["incremental_ebitda"] < 0


def test_exclusion_keeps_shared_commitment_once_and_changes_calculation_identity():
    case = example()
    selected = evaluate(case, frozenset())
    for scenario in selected["scenarios"]:
        assert scenario["total"]["incremental_ebitda"] == -25000
        assert scenario["total"]["pre_tax_cash_proxy"] == -25000
    assert selected["input_sha256"] == evaluate(case)["input_sha256"]
    assert selected["calculation_sha256"] != evaluate(case)["calculation_sha256"]
    with pytest.raises(ValueError, match="unknown initiative"):
        evaluate(case, frozenset({"typo"}))


def test_multiple_changes_only_valuation_not_operating_or_cash_schedule():
    case = example()
    raw = case.model_dump(mode="json")
    raw["multiples"] = ["12"]
    changed = evaluate(UnderwritingCase.model_validate(raw))
    original = evaluate(case)
    assert changed["input_sha256"] != original["input_sha256"]
    for before, after in zip(original["scenarios"], changed["scenarios"], strict=True):
        assert before["monthly"] == after["monthly"]
        assert before["day_100"] == after["day_100"]
        assert (
            after["valuation"][0]["incremental_ev_sensitivity"]
            == before["valuation"][0]["incremental_ev_sensitivity"] * 2
        )


def test_all_periods_cash_bridges_and_totals_reconcile_with_adverse_case_retained():
    report = evaluate(example())
    assert report["scenarios"][0]["total"]["incremental_ebitda"] < 0
    for scenario in report["scenarios"]:
        for row in scenario["monthly"]:
            assert (
                row["incremental_ebitda"]
                + row["operating_accrual_to_cash"]
                + row["working_capital_cash"]
                + row["capex_cash"]
                == row["pre_tax_cash_proxy"]
            )
        for key in ("incremental_ebitda", "pre_tax_cash_proxy", "implementation_expense"):
            assert sum(row[key] for row in scenario["monthly"]) == scenario["total"][key]
            assert scenario["year_one"][key] + scenario["year_two"][key] == scenario["total"][key]


def test_small_daily_amounts_cannot_create_negative_rounding_residuals():
    case = simplified(**{"eligible-revenue": "16", "uplift": ".01", "capture": "1", "churn": "0"})
    entries = ledger(case, case.scenarios[1], frozenset({"pricing-renewals"}))
    assert all(e.amount >= 0 for e in entries if e.component == "gross_price_benefit")
    assert totals(entries, date(2026, 10, 1), date(2026, 10, 31))["gross_price_benefit"] == Decimal(".16")


def test_cash_recovery_ignores_temporary_positive_balance_before_later_reversal():
    entries = tuple(
        Entry(
            day=date(2026, 10, day),
            initiative_id="x",
            component="operating_cash",
            amount=Decimal(value),
            reference="test",
        )
        for day, value in ((1, "-100"), (2, "200"), (3, "-150"), (4, "75"))
    )
    result = cash_profile(entries, date(2026, 10, 1), date(2026, 10, 31))
    assert result["maximum_dated_funding_need"] == 100
    assert result["cash_proxy_recovery_date"] == date(2026, 10, 4)
    assert cash_profile(entries[:-1], date(2026, 10, 1), date(2026, 10, 31))["cash_proxy_recovery_date"] is None
    assert cash_profile((), date(2026, 10, 1), date(2026, 10, 31))["cash_proxy_recovery_state"] == "no_modeled_deficit"


def test_midmonth_eligibility_does_not_earn_before_start_date():
    raw = simplified().model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["drivers"][0]["effective_on"] = "2026-10-17"
    case = UnderwritingCase.model_validate(raw)
    entries = ledger(case, case.scenarios[1], frozenset({"pricing-renewals"}))
    assert totals(entries, date(2026, 10, 1), date(2026, 10, 16))["incremental_ebitda"] == 0
    assert totals(entries, date(2026, 10, 1), date(2026, 10, 31))["incremental_ebitda"] == 54


def test_checked_in_constructed_case_reproduces_from_declared_generator():
    source = Path(__file__).resolve().parents[1] / "data/constructed/progress/underwriting.json"
    assert UnderwritingCase.model_validate_json(source.read_bytes()) == example()


def test_report_escapes_text_preserves_input_and_enforces_export_policy(tmp_path):
    raw = example().model_dump(mode="json")
    raw["company"] = "<script>alert('company')</script>"
    source = tmp_path / "input.json"
    source.write_text(UnderwritingCase.model_validate(raw).model_dump_json(), encoding="utf-8")
    output = build_underwriting_report(source, tmp_path / "report", frozenset({"service-automation"}))
    assert "<script>" not in output.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in output.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        build_underwriting_report(source, source)
    with pytest.raises(ValueError, match="unknown initiative"):
        build_underwriting_report(source, tmp_path / "other", frozenset({"unknown"}))
    raw["evidence"].append(
        {"evidence_id": "secret", "classification": "permissioned_private", "locator": "not-for-public"}
    )
    source.write_text(UnderwritingCase.model_validate(raw).model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="rejects private"):
        build_underwriting_report(source, tmp_path / "forbidden" / "report")
    assert not (tmp_path / "forbidden").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "overlap",
        "wrong_unit",
        "no_action",
        "unknown_evidence",
        "duplicate_cost",
        "private",
        "bad_reversal",
        "bad_multiple",
        "unstable_identity",
    ],
)
def test_invalid_economics_and_source_policy_are_rejected(mutation):
    raw = example().model_dump(mode="json")
    scenario = raw["scenarios"][1]
    if mutation == "overlap":
        scenario["drivers"][1]["benefit_pool"] = scenario["drivers"][0]["benefit_pool"]
    elif mutation == "wrong_unit":
        scenario["assumptions"][0]["unit"] = "hours"
    elif mutation == "no_action":
        scenario["drivers"][1]["cost_action"] = "none"
    elif mutation == "unknown_evidence":
        scenario["assumptions"][0]["evidence_ids"] = ["missing"]
    elif mutation == "duplicate_cost":
        scenario["costs"].append(scenario["costs"][0])
    elif mutation == "private":
        raw["evidence"].append(
            {"evidence_id": "private", "classification": "licensed_private", "locator": "private/source"}
        )
    elif mutation == "bad_reversal":
        scenario["drivers"][2]["counterfactual_collection_on"] = "2029-01-01"
    elif mutation == "bad_multiple":
        raw["multiples"] = ["NaN"]
    else:
        scenario["drivers"][0]["initiative_id"] = "changed"
    with pytest.raises(ValueError):
        evaluate(UnderwritingCase.model_validate(raw))
