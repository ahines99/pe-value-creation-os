"""Splitting source ownership cannot manufacture a second copy of the same benefit."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.diligence.operating_sources import (
    OperatingSourceBook,
    PartitionedSourceBook,
    operating_records,
    source_forecast,
)
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.underwriting import UnderwritingCase

DATA = Path(__file__).resolve().parents[1] / "data/constructed/progress"
PARENT = "pricing-renewals"
CHILDREN = ("pricing-spring", "pricing-other")


def inputs():
    return (
        UnderwritingCase.model_validate_json((DATA / "underwriting.json").read_bytes()),
        OperatingPlan.model_validate_json((DATA / "operating-plan.json").read_bytes()),
        OperatingSourceBook.model_validate_json((DATA / "operating-sources.json").read_bytes()),
    )


def split_inputs():
    case, plan, book = inputs()
    raw = case.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        driver = next(d for d in scenario["drivers"] if d["initiative_id"] == PARENT)
        amount = next(a for a in scenario["assumptions"] if a["assumption_id"] == driver["monthly_eligible_revenue"])
        scenario["drivers"].remove(driver)
        for child, revenue in zip(CHILDREN, (250000, 750000), strict=True):
            scenario["assumptions"].append({**amount, "assumption_id": child + "-revenue", "value": str(revenue)})
            scenario["drivers"].append(
                {
                    **driver,
                    "initiative_id": child,
                    "benefit_pool": child,
                    "monthly_eligible_revenue": child + "-revenue",
                }
            )
        for cost in scenario["costs"]:
            cost["initiative_ids"] = [
                new for old in cost["initiative_ids"] for new in (CHILDREN if old == PARENT else [old])
            ]
    case = UnderwritingCase.model_validate(raw)
    raw_plan = plan.model_dump(mode="json")
    raw_plan["underwriting_sha256"] = fingerprint(case)
    # This conservation fixture splits the same effort, allowing both substreams
    # concurrently. A separate challenge delays one of their independent gates.
    raw_plan["maximum_active_workstreams"] += 1
    tasks = {t["task_id"]: t for t in raw_plan["tasks"]}
    pricing_tasks = {k for k, t in tasks.items() if t["initiative_id"] == PARENT}
    revised_tasks, order = [], []
    for task_id in raw_plan["priority_order"]:
        task = tasks[task_id]
        if task_id not in pricing_tasks:
            revised_tasks.append(task)
            order.append(task_id)
            continue
        for child in CHILDREN:
            new = deepcopy(task)
            new.update(task_id=task_id + ":" + child, initiative_id=child, workstream_id=child)
            new["prerequisites"] = [p + ":" + child if p in pricing_tasks else p for p in task["prerequisites"]]
            for demand in new["demands"]:
                demand["hours_per_week"] = str(Decimal(demand["hours_per_week"]) / 2)
            revised_tasks.append(new)
            order.append(new["task_id"])
    raw_plan["tasks"], raw_plan["priority_order"] = revised_tasks, order
    raw_plan["benefit_gates"] = [
        {"initiative_id": child, "task_id": gate["task_id"] + ":" + child} if gate["initiative_id"] == PARENT else gate
        for gate in raw_plan["benefit_gates"]
        for child in (CHILDREN if gate["initiative_id"] == PARENT else [gate["initiative_id"]])
    ]
    plan = OperatingPlan.model_validate(raw_plan)
    records = OperatingSourceBook.model_validate(
        {**book.model_dump(mode="json"), "underwriting_sha256": fingerprint(case), "plan_sha256": fingerprint(plan)}
    )
    assignments = []
    for (kind, identity), record in operating_records(records).items():
        owner = (
            "service-automation"
            if kind == "service_month"
            else "collections-timing"
            if kind == "invoice"
            else CHILDREN[0]
            if identity == "spring-capped"
            else CHILDREN[1]
        )
        assignments.append(
            {"kind": kind, "record_id": identity, "record_sha256": fingerprint(record), "initiative_id": owner}
        )
    partition = PartitionedSourceBook(
        schema_version=2,
        records=records,
        assignments=assignments,
        partition_rationale="Constructed spring contract cohort versus all other contracts; shared costs retained once.",
    )
    return case, plan, partition


def test_disjoint_pricing_split_conserves_source_economics_and_shared_costs():
    original, plan, book = inputs()
    before = source_forecast(book, original, plan)
    case, revised, partition = split_inputs()
    after = source_forecast(partition, case, revised)
    assert after["version"] == "operating-source-forecast/2"
    for a, b in zip(before["scenarios"], after["scenarios"], strict=True):
        for period in ("day_100", "year_one", "year_two", "total"):
            assert a[period] == b[period]
        assert len([d for d in b["decisions"] if d["kind"] == "renewal"]) == len(book.renewals)
        assert all("initiative_id" in d for d in b["decisions"])
        if b["scenario_id"] == "base":
            assert b["year_one"]["implementation_expense"] == Decimal("-85000")
    assert partition.records.renewals == book.renewals
    assert partition.records.service_months == book.service_months
    assert partition.records.invoices == book.invoices


def test_independent_child_delay_changes_its_source_eligibility():
    case, plan, partition = split_inputs()
    before = source_forecast(partition, case, plan)
    raw = plan.model_dump(mode="json")
    for task in raw["tasks"]:
        if task["initiative_id"] == CHILDREN[0]:
            task["earliest_start"] = "2027-01-08"
    delayed = OperatingPlan.model_validate(raw)
    raw_book = partition.model_dump(mode="json")
    raw_book["records"]["plan_sha256"] = fingerprint(delayed)
    changed = source_forecast(PartitionedSourceBook.model_validate(raw_book), case, delayed)
    for a, b in zip(before["scenarios"], changed["scenarios"], strict=True):
        assert next(d for d in a["decisions"] if d.get("record_id") == "spring-capped")["eligible"]
        assert not next(d for d in b["decisions"] if d.get("record_id") == "spring-capped")["eligible"]
        assert b["year_one"]["incremental_ebitda"] != a["year_one"]["incremental_ebitda"]
        if b["scenario_id"] == "base":
            assert b["year_one"]["incremental_ebitda"] < a["year_one"]["incremental_ebitda"]
        elif b["scenario_id"] == "downside":
            # Preventing a loss-making repricing action can improve the downside.
            assert b["year_one"]["incremental_ebitda"] > a["year_one"]["incremental_ebitda"]
        assert b["year_one"]["implementation_expense"] == a["year_one"]["implementation_expense"]
        assert [e for e in b["entries"] if e["initiative_id"] == CHILDREN[1]] == [
            e for e in a["entries"] if e["initiative_id"] == CHILDREN[1]
        ]


@pytest.mark.parametrize(
    "change",
    ["duplicate", "missing", "unknown_record", "changed_record", "wrong_mechanism", "unknown_owner", "unowned_child"],
)
def test_partition_cannot_duplicate_drop_or_misassign_source_records(change):
    case, plan, book = split_inputs()
    raw = book.model_dump(mode="json")
    if change == "duplicate":
        raw["assignments"].append(raw["assignments"][0])
    elif change == "missing":
        raw["assignments"].pop()
    elif change == "unknown_record":
        raw["assignments"][0]["record_id"] = "outside"
    elif change == "changed_record":
        raw["records"]["renewals"][0]["notice_days"] = 1
    elif change == "wrong_mechanism":
        raw["assignments"][0]["initiative_id"] = "service-automation"
    elif change == "unknown_owner":
        raw["assignments"][0]["initiative_id"] = "outsider"
    else:
        for row in raw["assignments"]:
            if row["initiative_id"] == CHILDREN[0]:
                row["initiative_id"] = CHILDREN[1]
    with pytest.raises(ValueError, match="partition"):
        PartitionedSourceBook.model_validate(raw).bind(case, plan)
