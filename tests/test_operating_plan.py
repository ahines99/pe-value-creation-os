"""Independent schedule arithmetic, failure propagation and schedule-to-finance contracts."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.build_operating_plan_example import example
from scripts.build_underwriting_example import example as underwriting_example

from pe_value_os.cli import main
from pe_value_os.diligence.scheduling import OperatingPlan, evaluate_plan, fingerprint, schedule
from pe_value_os.diligence.scheduling_render import build_operating_report
from pe_value_os.diligence.underwriting import UnderwritingCase, evaluate


def worked():
    raw = underwriting_example().model_dump(mode="json")
    for scenario in raw["scenarios"]:
        for assumption in scenario["assumptions"]:
            overrides = {
                "eligible-revenue": "3100",
                "uplift": ".10",
                "capture": "1",
                "churn": "0",
                "contacts": "0",
                "cost-action": "0",
                "receivables": "1000",
                "accelerated": ".10",
                "setup": "100",
            }
            if assumption["assumption_id"] in overrides:
                assumption["value"] = overrides[assumption["assumption_id"]]
        for driver in scenario["drivers"]:
            driver["effective_on"] = raw["start"]
            if driver["kind"] == "service":
                driver["cost_action"] = "none"
            if driver["kind"] == "collections":
                driver["counterfactual_collection_on"] = "2026-11-10"
        scenario["costs"] = [
            {
                "cost_id": "setup",
                "initiative_ids": ["service-automation"],
                "kind": "implementation",
                "amount": "setup",
                "recognized_on": "2026-10-01",
                "paid_on": "2026-10-01",
                "retained_if_excluded": False,
            }
        ]
    case = UnderwritingCase.model_validate(raw)
    plan = example().model_dump(mode="json")
    plan["underwriting_sha256"] = fingerprint(case)
    plan["resources"] = [
        {
            "resource_id": "finance",
            "proposed_operator": "Proposed operator",
            "weekly_hours": ["10"] * 15,
            "basis": "Worked constructed capacity",
        }
    ]
    plan["tasks"] = []
    for key, initiative in (
        ("foundation", None),
        ("pricing-gate", "pricing-renewals"),
        ("service-gate", "service-automation"),
        ("collections-gate", "collections-timing"),
    ):
        plan["tasks"].append(
            {
                "task_id": key,
                "title": key,
                "initiative_id": initiative,
                "workstream_id": key,
                "accountable_resource": "finance",
                "earliest_start": case.start,
                "duration_weeks": 1,
                "prerequisites": [] if key == "foundation" else ["foundation"],
                "demands": [{"resource_id": "finance", "hours_per_week": "10"}],
                "deliverable": "Reviewed cohort",
                "acceptance_evidence": "Exact cohort and reconciled baseline",
                "acceptance_reviewer": "Proposed reviewer",
            }
        )
    plan["priority_order"] = [t["task_id"] for t in plan["tasks"]]
    return OperatingPlan.model_validate(plan), case


def test_hand_worked_sequential_capacity_and_financial_accrual():
    plan, case = worked()
    before = case.model_dump_json()
    report = evaluate_plan(plan, case)
    assert [t["scheduled_start"] for t in report["tasks"]] == [date(2026, 10, d) for d in (1, 8, 15, 22)]
    assert [t["scheduled_finish"] for t in report["tasks"]] == [date(2026, 10, d) for d in (7, 14, 21, 28)]
    assert report["tasks"][2]["candidate_rejections"][0]["conflicts"][0]["competing_tasks"] == ["pricing-gate"]
    original = report["original_financials"]["scenarios"][1]
    revised = report["scheduled_financials"]["scenarios"][1]
    # 3,100 * 10% * (1 - 20% variable cost) = 248/month.
    # Gate finishes Oct 14: 17/31 * 248 = 136; less unchanged 100 setup = 36.
    assert original["monthly"][0]["incremental_ebitda"] == Decimal("148.00")
    assert revised["monthly"][0]["incremental_ebitda"] == Decimal("36.00")
    assert revised["year_one"]["incremental_ebitda"] - original["year_one"]["incremental_ebitda"] == Decimal("-112.00")
    assert revised["costs"] == original["costs"]
    assert case.model_dump_json() == before  # No mutation of original dates or assumptions.
    assert sum(w["used_hours"] for w in report["capacity"][0]["weeks"]) == 40
    assert report == evaluate_plan(plan, case)


def test_authored_order_changes_schedule_and_forecast_with_new_fingerprint():
    plan, case = worked()
    raw = plan.model_dump(mode="json")
    raw["priority_order"] = list(reversed(raw["priority_order"]))
    raw["revision_id"] = "reordered-v2"
    reordered = evaluate_plan(OperatingPlan.model_validate(raw), case)
    baseline = evaluate_plan(plan, case)
    pricing = next(t for t in reordered["tasks"] if t["task_id"] == "pricing-gate")
    assert pricing["scheduled_start"] == date(2026, 10, 22)
    assert reordered["report_sha256"] != baseline["report_sha256"]
    assert reordered["original_underwriting_sha256"] == baseline["original_underwriting_sha256"]
    assert (
        reordered["scheduled_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"]
        < baseline["scheduled_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"]
    )


@pytest.mark.parametrize(("hours", "kind"), [(None, "unknown_capacity"), ("0", "resource_capacity")])
def test_missing_or_zero_capacity_blocks_dependents_without_canceling_costs(hours, kind):
    plan, case = worked()
    raw = plan.model_dump(mode="json")
    raw["resources"][0]["weekly_hours"] = [hours] * 15
    result = evaluate_plan(OperatingPlan.model_validate(raw), case)
    assert all(t["status"] == "blocked" for t in result["tasks"])
    assert result["tasks"][0]["candidate_rejections"][0]["conflicts"][0]["kind"] == kind
    assert result["tasks"][1]["blocked_by"] == ["foundation"]
    assert result["scheduled_financials"]["scenarios"][1]["total"]["incremental_ebitda"] == -100
    assert result["scheduled_financials"]["scenarios"][1]["total"]["pre_tax_cash_proxy"] == -100
    assert result["scheduled_financials"]["scenarios"][1]["valuation"][0]["incremental_ev_sensitivity"] == 0


def test_unknown_early_capacity_can_delay_until_explicit_later_budget():
    plan, _ = worked()
    raw = plan.model_dump(mode="json")
    raw["resources"][0]["weekly_hours"][0] = None
    result = schedule(OperatingPlan.model_validate(raw))
    assert result["tasks"][0]["scheduled_start"] == date(2026, 10, 8)
    assert result["tasks"][0]["candidate_rejections"][0]["conflicts"][0]["kind"] == "unknown_capacity"


def test_lost_collection_window_is_suppressed_instead_of_moving_counterfactual():
    plan, case = worked()
    raw = case.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["drivers"][2]["counterfactual_collection_on"] = "2026-10-20"
    case = UnderwritingCase.model_validate(raw)
    updated = plan.model_dump(mode="json")
    updated["underwriting_sha256"] = fingerprint(case)
    result = evaluate_plan(OperatingPlan.model_validate(updated), case)
    assert result["scheduled_financials"]["scenarios"][1]["suppressed_benefits"] == ["collections-timing"]
    assert result["scheduled_financials"]["scenarios"][1]["monthly"][0]["working_capital_cash"] == 0
    assert result["scheduled_case"]["scenarios"][1]["drivers"][2]["counterfactual_collection_on"] == "2026-10-20"
    assert "expired" in result["timing"][2]["reason"]


def test_concurrent_workstream_limit_even_when_resource_hours_fit():
    plan, _ = worked()
    raw = plan.model_dump(mode="json")
    raw["resources"][0]["weekly_hours"] = ["30"] * 15
    raw["maximum_active_workstreams"] = 2
    result = schedule(OperatingPlan.model_validate(raw))
    assert result["tasks"][1]["scheduled_start"] == result["tasks"][2]["scheduled_start"] == date(2026, 10, 8)
    assert result["tasks"][3]["scheduled_start"] == date(2026, 10, 15)
    assert result["tasks"][3]["candidate_rejections"][0]["conflicts"][0]["kind"] == "workstream_limit"


def test_no_full_week_slot_at_day_99_and_never_advance_original_benefit():
    plan, case = worked()
    raw = plan.model_dump(mode="json")
    raw["tasks"][1]["earliest_start"] = "2027-01-07"
    result = evaluate_plan(OperatingPlan.model_validate(raw), case)
    assert result["tasks"][1]["status"] == "blocked"
    assert "pricing-renewals" in result["scheduled_financials"]["scenarios"][1]["suppressed_benefits"]
    standard = evaluate_plan(example(), underwriting_example())
    for row in standard["timing"]:
        assert row["scheduled_effective_on"] is None or row["scheduled_effective_on"] >= row["original_effective_on"]


@pytest.mark.parametrize(
    "mutation",
    [
        "cycle",
        "orphan",
        "duplicate_priority",
        "missing_gate",
        "gate_bypass",
        "unknown_resource",
        "owner_without_demand",
        "negative_budget",
        "duplicate_demand",
        "private_class",
        "actual_assignment",
    ],
)
def test_invalid_contracts_rejected(mutation):
    plan, _ = worked()
    raw = plan.model_dump(mode="json")
    if mutation == "cycle":
        raw["tasks"][0]["prerequisites"] = ["pricing-gate"]
    elif mutation == "orphan":
        raw["tasks"][1]["prerequisites"] = ["missing"]
    elif mutation == "duplicate_priority":
        raw["priority_order"][0] = raw["priority_order"][1]
    elif mutation == "missing_gate":
        raw["benefit_gates"].pop()
    elif mutation == "gate_bypass":
        raw["tasks"][2]["initiative_id"] = "pricing-renewals"
        raw["benefit_gates"] = [g for g in raw["benefit_gates"] if g["initiative_id"] != "service-automation"]
    elif mutation == "unknown_resource":
        raw["tasks"][0]["demands"][0]["resource_id"] = "missing"
    elif mutation == "owner_without_demand":
        raw["resources"].append({**raw["resources"][0], "resource_id": "second"})
        raw["tasks"][0]["accountable_resource"] = "second"
    elif mutation == "negative_budget":
        raw["resources"][0]["weekly_hours"][0] = "-1"
    elif mutation == "duplicate_demand":
        raw["tasks"][0]["demands"] *= 2
    elif mutation == "private_class":
        raw["classification"] = "permissioned_private"
    else:
        raw["resources"][0]["assignment"] = "actual_assignment"
    with pytest.raises(ValueError):
        OperatingPlan.model_validate(raw)


def test_exact_binding_rejects_changed_case_and_private_evidence():
    plan, case = worked()
    raw = case.model_dump(mode="json")
    raw["multiples"] = ["7"]
    with pytest.raises(ValueError, match="exact underwriting"):
        evaluate_plan(plan, UnderwritingCase.model_validate(raw))
    raw = case.model_dump(mode="json")
    raw["evidence"][1]["classification"] = "licensed_private"
    with pytest.raises(ValueError, match="private"):
        evaluate_plan(plan, UnderwritingCase.model_validate(raw))


@pytest.mark.parametrize("change", ["shared_workstream", "different_operator", "split_workstream"])
def test_concurrency_and_accountability_cannot_be_bypassed(change):
    raw = example().model_dump(mode="json")
    if change == "shared_workstream":
        raw["tasks"][3]["workstream_id"] = raw["tasks"][1]["workstream_id"]
    elif change == "different_operator":
        raw["tasks"][4]["accountable_resource"] = "finance"
    else:
        raw["tasks"][4]["workstream_id"] = "extra-pricing"
    with pytest.raises(ValueError):
        OperatingPlan.model_validate(raw)


def test_masks_are_validated_and_change_calculation_not_costs():
    _, case = worked()
    with pytest.raises(ValueError, match="unknown"):
        evaluate(case, benefit_blocks={"base": frozenset({"wrong"})})
    with pytest.raises(ValueError, match="unknown"):
        evaluate(case, benefit_blocks={"wrong": frozenset()})
    masked = evaluate(case, benefit_blocks={"base": frozenset({"pricing-renewals"})})
    original = evaluate(case)
    assert masked["input_sha256"] == original["input_sha256"]
    assert masked["calculation_sha256"] != original["calculation_sha256"]
    assert masked["scenarios"][1]["costs"] == original["scenarios"][1]["costs"]


def test_sample_resource_conservation_and_real_delay():
    plan = example()
    result = evaluate_plan(plan, underwriting_example())
    assert all(t["status"] == "scheduled" for t in result["tasks"])
    assert any(t["candidate_rejections"] for t in result["tasks"])
    for resource in result["capacity"]:
        for week in resource["weeks"]:
            assert week["used_hours"] <= week["budget_hours"]
    base = result["scheduled_financials"]["scenarios"][1]
    original = result["original_financials"]["scenarios"][1]
    assert base["year_one"]["incremental_ebitda"] < original["year_one"]["incremental_ebitda"]
    assert base["costs"] == original["costs"]
    assert json.loads(Path("data/constructed/progress/operating-plan.json").read_text()) == plan.model_dump(mode="json")


def test_report_cli_escaping_and_input_protection(tmp_path, monkeypatch):
    plan, case = worked()
    raw = plan.model_dump(mode="json")
    raw["tasks"][0]["title"] = "<script>unsafe</script>"
    source, underwriting = tmp_path / "plan.json", tmp_path / "case.json"
    source.write_text(json.dumps(raw))
    underwriting.write_text(case.model_dump_json())
    output = tmp_path / "report"
    report = build_operating_report(source, underwriting, output)
    html = report.read_text(encoding="utf-8")
    assert "<script>unsafe</script>" not in html and "&lt;script&gt;" in html
    assert "Timing changes the forecast" in html and "Unknown capacity" in html
    assert "no actual assignments" in html
    with pytest.raises(ValueError, match="overwrite"):
        build_operating_report(source, underwriting, source)
    with pytest.raises(ValueError, match="overwrite"):
        build_operating_report(source, underwriting, underwriting)
    monkeypatch.setattr(
        "sys.argv",
        ["pvc", "operating-plan", "--input", str(source), "--underwriting", str(underwriting), "--output", str(output)],
    )
    assert main() == 0
