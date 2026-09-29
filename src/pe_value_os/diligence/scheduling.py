"""Deterministic, non-preemptive planning with explicit capacity and financial lineage.

Seven-day planning weeks start on the case start date, not necessarily Monday.
This is feasibility under authored assumptions, not an optimizer or authorization.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .interactions import InteractionCase
from .models import Record
from .underwriting import Collections, Scenario, evaluate
from .underwriting_models import UnderwritingModel, parse_underwriting

VERSION = "capacity-schedule/1"


def fingerprint(record: Record) -> str:
    return hashlib.sha256(record.model_dump_json().encode()).hexdigest()


class Resource(Record):
    resource_id: str = Field(min_length=1)
    proposed_operator: str = Field(min_length=1)
    assignment: Literal["proposed", "simulated_assignment"] = "proposed"
    # Net change capacity after business-as-usual work; None is unknown, never zero.
    weekly_hours: tuple[Decimal | None, ...] = Field(min_length=15, max_length=15)
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonnegative(self) -> Self:
        if any(hours is not None and (hours < 0 or hours > 168) for hours in self.weekly_hours):
            raise ValueError("weekly hours must be between zero and 168, or unknown")
        return self


class Demand(Record):
    resource_id: str = Field(min_length=1)
    hours_per_week: Decimal = Field(gt=0, le=168)


class WorkPackage(Record):
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    workstream_id: str = Field(min_length=1)
    initiative_id: str | None = None
    accountable_resource: str = Field(min_length=1)
    earliest_start: date
    duration_weeks: int = Field(ge=1, le=14)
    prerequisites: tuple[str, ...] = ()
    demands: tuple[Demand, ...] = Field(min_length=1)
    deliverable: str = Field(min_length=1)
    acceptance_evidence: str = Field(min_length=1)
    acceptance_reviewer: str = Field(min_length=1)


class BenefitGate(Record):
    initiative_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)


class _PlanningInputs(Record):
    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    underwriting_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: Literal["constructed_operating_exercise", "permissioned_private"]
    start: date
    days: Literal[100] = 100
    maximum_active_workstreams: int = Field(ge=1, le=10)
    sequencing_rationale: str = Field(min_length=1)
    resources: tuple[Resource, ...] = Field(min_length=1)
    tasks: tuple[WorkPackage, ...] = Field(min_length=1)
    priority_order: tuple[str, ...] = Field(min_length=1)
    benefit_gates: tuple[BenefitGate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        resources = {r.resource_id for r in self.resources}
        tasks = {t.task_id: t for t in self.tasks}
        if len(resources) != len(self.resources) or len(tasks) != len(self.tasks):
            raise ValueError("resource and task IDs must be unique")
        if set(self.priority_order) != set(tasks) or len(self.priority_order) != len(tasks):
            raise ValueError("priority order must contain each task exactly once")
        workstream_owners: dict[str, str | None] = {}
        initiative_owners: dict[str, tuple[str, str]] = {}
        for task in self.tasks:
            if task.workstream_id in workstream_owners and workstream_owners[task.workstream_id] != task.initiative_id:
                raise ValueError("distinct initiatives and enablers cannot share a workstream to bypass concurrency")
            workstream_owners[task.workstream_id] = task.initiative_id
            if task.initiative_id is not None:
                identity = (task.workstream_id, task.accountable_resource)
                if task.initiative_id in initiative_owners and initiative_owners[task.initiative_id] != identity:
                    raise ValueError("initiative requires one workstream and accountable operator")
                initiative_owners[task.initiative_id] = identity
            if task.earliest_start < self.start:
                raise ValueError("task earliest start cannot precede plan start")
            if task.accountable_resource not in resources:
                raise ValueError("task requires a registered accountable resource")
            demand_ids = {d.resource_id for d in task.demands}
            if len(demand_ids) != len(task.demands) or not demand_ids <= resources:
                raise ValueError("task demand must reference unique registered resources")
            if task.accountable_resource not in demand_ids:
                raise ValueError("accountable operator must have explicit capacity demand")
            if len(set(task.prerequisites)) != len(task.prerequisites) or not set(task.prerequisites) <= set(tasks):
                raise ValueError("duplicate or orphan prerequisite")
        # Kahn traversal also detects self-dependency without recursive depth assumptions.
        pending = set(tasks)
        completed: set[str] = set()
        while pending:
            ready = {key for key in pending if set(tasks[key].prerequisites) <= completed}
            if not ready:
                raise ValueError("cyclic task prerequisites")
            pending -= ready
            completed |= ready
        gates = {g.initiative_id: g.task_id for g in self.benefit_gates}
        if len(gates) != len(self.benefit_gates):
            raise ValueError("duplicate initiative benefit gate")
        task_initiatives = {t.initiative_id for t in self.tasks if t.initiative_id is not None}
        if set(gates) != task_initiatives:
            raise ValueError("every initiative requires exactly one benefit gate")
        for initiative, gate in gates.items():
            if gate not in tasks or tasks[gate].initiative_id != initiative:
                raise ValueError("benefit gate must belong to its initiative")
            ancestors, frontier = {gate}, {gate}
            while frontier:
                frontier = {p for key in frontier for p in tasks[key].prerequisites} - ancestors
                ancestors |= frontier
            if any(t.initiative_id == initiative and t.task_id not in ancestors for t in self.tasks):
                raise ValueError("benefit gate must depend on every work package for its initiative")
        return self


class OperatingPlan(_PlanningInputs):
    """Public constructed plan; field order and serialization remain stable."""

    classification: Literal["constructed_operating_exercise"]

    def bind(self, case: UnderwritingModel) -> None:
        case.require_public()
        if self.case_id != case.case_id or self.start != case.start or self.underwriting_sha256 != fingerprint(case):
            raise ValueError("plan must bind the exact underwriting case and start date")
        ids = {d.initiative_id for d in case.scenarios[0].drivers}
        if {g.initiative_id for g in self.benefit_gates} != ids:
            raise ValueError("benefit gates must cover the exact underwriting initiatives")


def schedule(plan: _PlanningInputs, selected: frozenset[str] | None = None) -> dict[str, Any]:
    tasks = {t.task_id: t for t in plan.tasks}
    excluded = []
    if selected is not None:
        if not selected <= {g.initiative_id for g in plan.benefit_gates}:
            raise ValueError("schedule selection references an unknown initiative")
        needed = {key for key, task in tasks.items() if task.initiative_id in selected}
        frontier = set(needed)
        while frontier:
            frontier = {p for key in frontier for p in tasks[key].prerequisites} - needed
            needed |= frontier
        if any(tasks[key].initiative_id is not None and tasks[key].initiative_id not in selected for key in needed):
            raise ValueError("selected work depends on an unselected initiative; resolve the choice explicitly")
        excluded = [t.model_dump(mode="json") for t in plan.tasks if t.task_id not in needed]
        tasks = {key: task for key, task in tasks.items() if key in needed}
    resources = {r.resource_id: r for r in plan.resources}
    used = {(resource, week): Decimal(0) for resource in resources for week in range(15)}
    occupants: dict[int, set[str]] = {week: set() for week in range(15)}
    allocations: dict[tuple[str, int], list[str]] = {key: [] for key in used}
    results: dict[str, dict[str, Any]] = {}
    pending = set(tasks)
    end = plan.start + timedelta(days=plan.days - 1)
    while pending:
        key = next(
            key for key in plan.priority_order if key in pending and set(tasks[key].prerequisites) <= results.keys()
        )
        task = tasks[key]
        pending.remove(key)
        blocked_by = [p for p in task.prerequisites if results[p]["status"] == "blocked"]
        row: dict[str, Any] = {
            **task.model_dump(mode="json"),
            "status": "blocked",
            "scheduled_start": None,
            "scheduled_finish": None,
            "benefit_ready_on": None,
            "blocked_by": blocked_by,
            "candidate_rejections": [],
        }
        results[key] = row
        if blocked_by:
            row["reason"] = "Prerequisite has no feasible slot; dependent work cannot proceed."
            continue
        earliest = max(
            [task.earliest_start, *(results[p]["scheduled_finish"] + timedelta(days=1) for p in task.prerequisites)]
        )
        first_week = ((earliest - plan.start).days + 6) // 7
        row["dependency_ready_on"] = earliest
        for first in range(first_week, 15):
            start = plan.start + timedelta(days=7 * first)
            finish = start + timedelta(days=7 * task.duration_weeks - 1)
            if finish > end:
                break
            conflicts = []
            for week in range(first, first + task.duration_weeks):
                if len(occupants[week] | {task.workstream_id}) > plan.maximum_active_workstreams:
                    conflicts.append(
                        {"week": week + 1, "kind": "workstream_limit", "workstreams": sorted(occupants[week])}
                    )
                for demand in task.demands:
                    budget = resources[demand.resource_id].weekly_hours[week]
                    if budget is None or used[demand.resource_id, week] + demand.hours_per_week > budget:
                        conflicts.append(
                            {
                                "week": week + 1,
                                "kind": "unknown_capacity" if budget is None else "resource_capacity",
                                "resource_id": demand.resource_id,
                                "available": None if budget is None else budget - used[demand.resource_id, week],
                                "required": demand.hours_per_week,
                                "competing_tasks": allocations[demand.resource_id, week].copy(),
                            }
                        )
            if conflicts:
                row["candidate_rejections"].append({"start": start, "conflicts": conflicts})
                continue
            for week in range(first, first + task.duration_weeks):
                occupants[week].add(task.workstream_id)
                for demand in task.demands:
                    used[demand.resource_id, week] += demand.hours_per_week
                    allocations[demand.resource_id, week].append(key)
            row.update(
                status="scheduled",
                scheduled_start=start,
                scheduled_finish=finish,
                benefit_ready_on=finish + timedelta(days=1),
            )
            row["reason"] = (
                "Delayed by recorded capacity conflicts."
                if row["candidate_rejections"]
                else "Earliest feasible full planning week after prerequisites and release date."
            )
            break
        if row["status"] == "blocked":
            row["reason"] = (
                "No feasible full-week slot within 100 days; benefit remains unavailable pending a revised plan."
            )
    return {
        "schedule_version": "capacity-schedule/2" if selected is not None else VERSION,
        "plan_sha256": fingerprint(plan),
        "start": plan.start,
        "end": end,
        "tasks": [results[key] for key in plan.priority_order if key in results],
        "capacity": [
            {
                "resource_id": resource.resource_id,
                "proposed_operator": resource.proposed_operator,
                "assignment": resource.assignment,
                "weeks": [
                    {
                        "week": week + 1,
                        "start": plan.start + timedelta(days=7 * week),
                        "end": min(end, plan.start + timedelta(days=7 * week + 6)),
                        "budget_hours": resource.weekly_hours[week],
                        "used_hours": used[resource.resource_id, week],
                        "tasks": allocations[resource.resource_id, week],
                    }
                    for week in range(15)
                ],
            }
            for resource in plan.resources
        ],
        "authority": "Constructed proposed plan; no actual assignments, accepted deliverables, management decisions or authorization to execute."
        if plan.classification == "constructed_operating_exercise"
        else "Private proposed plan; capacity and acceptance dates are authored assumptions, not committed assignments, accepted deliverables or operating authorization.",
        "method": "Authored priority among dependency-ready tasks; earliest feasible non-preemptive full planning weeks. Seven-day weeks start on the case date; the final two days cannot fit a full-week package. Capacity is net of normal duties. Feasibility is conditional on the inputs, not optimality or observed execution.",
        **(
            {
                "selected_initiatives": sorted(selected),
                "excluded_tasks": excluded,
                "selection_treatment": "Only selected initiatives and their required enablers consume modeled capacity. An unselected initiative cannot be an implicit prerequisite. Exclusion does not cancel retained financial commitments.",
            }
            if selected is not None
            else {}
        ),
    }


def apply_benefit_timing(
    scenarios: tuple[Scenario, ...],
    benefit_gates: tuple[BenefitGate, ...],
    result: dict[str, Any],
    selected: frozenset[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, frozenset[str]], list[dict[str, Any]]]:
    """Apply scheduled gates without changing costs, selection or counterfactual dates."""
    tasks = {t["task_id"]: t for t in result["tasks"]}
    gates = {g.initiative_id: tasks[g.task_id] for g in benefit_gates if g.task_id in tasks}
    raw = [scenario.model_dump(mode="json") for scenario in scenarios]
    blocks: dict[str, frozenset[str]] = {}
    timing = []
    for scenario, original in zip(raw, scenarios, strict=True):
        suppressed = set()
        for driver, original_driver in zip(scenario["drivers"], original.drivers, strict=True):
            if selected is not None and driver["initiative_id"] not in selected:
                timing.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "initiative_id": original_driver.initiative_id,
                        "original_effective_on": original_driver.effective_on,
                        "scheduled_effective_on": None,
                        "reason": "Excluded by the explicit selection; retained financial commitments remain.",
                    }
                )
                continue
            gate = gates[driver["initiative_id"]]
            effective = (
                None if gate["status"] == "blocked" else max(original_driver.effective_on, gate["benefit_ready_on"])
            )
            reason = "No feasible gate; no benefit assumed anywhere in the forecast until replanned."
            if (
                effective is not None
                and isinstance(original_driver, Collections)
                and effective >= original_driver.counterfactual_collection_on
            ):
                effective = None
                reason = "Gate misses the original collection date; acceleration opportunity has expired."
            if effective is None:
                suppressed.add(original_driver.initiative_id)
            else:
                driver["effective_on"] = effective.isoformat()
                reason = "Later of original economic assumption and day after scheduled acceptance gate."
            timing.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "initiative_id": original_driver.initiative_id,
                    "original_effective_on": original_driver.effective_on,
                    "scheduled_effective_on": effective,
                    "reason": reason,
                }
            )
        blocks[scenario["scenario_id"]] = frozenset(suppressed)
    return raw, blocks, timing


def evaluate_plan(
    plan: OperatingPlan, case: UnderwritingModel, *, selected: frozenset[str] | None = None
) -> dict[str, Any]:
    plan.bind(case)
    if isinstance(case, InteractionCase):
        selected = frozenset(case.interaction_policy.selected_initiatives) if selected is None else selected
        case.validate_selection(selected)
    result = schedule(plan, selected)
    raw = case.model_dump(mode="json")
    raw["scenarios"], blocks, timing = apply_benefit_timing(case.scenarios, plan.benefit_gates, result, selected)
    scheduled_case = parse_underwriting(raw)
    original_report = evaluate(case, selected)
    revised_report = evaluate(scheduled_case, selected, benefit_blocks=blocks)
    return {
        **result,
        "case_id": case.case_id,
        "plan_id": plan.plan_id,
        "revision_id": plan.revision_id,
        "classification": plan.classification,
        "original_underwriting_sha256": fingerprint(case),
        "timing": timing,
        "original_financials": original_report,
        "scheduled_financials": revised_report,
        "scheduled_case": scheduled_case.model_dump(mode="json"),
        "cost_treatment": "All original dated expenses, fees and capex remain unchanged. Benefit suppression is not initiative rejection or cost cancellation. Avoiding or rescheduling a cost requires an explicit separate case revision."
        if selected is None
        else "Selected initiatives retain all their dated costs. Explicitly avoidable costs of unselected initiatives are excluded; retained commitments remain once. A blocked selected initiative keeps its costs. No cost is rescheduled by the capacity solver.",
        "report_sha256": hashlib.sha256(
            json.dumps(
                {
                    "plan": fingerprint(plan),
                    "original": original_report["calculation_sha256"],
                    "scheduled": revised_report["calculation_sha256"],
                    "version": result["schedule_version"],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
