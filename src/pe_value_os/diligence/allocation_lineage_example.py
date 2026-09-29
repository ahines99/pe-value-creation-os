"""Authored shared-pool lifecycle. No source record is cloned into a fake cohort."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any

from .allocation_demo import bind_sources
from .allocation_kpis import AllocatedKpiBook, AllocatedKpiDefinition
from .cases import CaseRevision, RevisionDraft
from .interactions import InteractionCase, population_shares
from .lineage import AllocatedLineageCasePayload, LineageEvent
from .lineage_example import reading
from .lineage_kpis import METRIC_KIND, LineageKpiReading
from .operating_sources import AllocatedSourceBook, source_records
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import SourceCasePayload, source_payload
from .underwriting import EXPECTED_UNITS

PARENT = "pricing-targeted"
CHILDREN = ("pricing-wave-a", "pricing-wave-b")
MERGED = "pricing-recombined"


def basis(parent: CaseRevision, case: InteractionCase, plan: OperatingPlan) -> SourceCasePayload:
    prior = source_payload(parent.draft.payload)
    if prior is None:
        raise ValueError("allocated lifecycle requires a source-backed parent")
    book = bind_sources(source_records(prior.operating_sources), case, plan)
    lessons = []
    for driver in next(s for s in prior.underwriting.scenarios if s.scenario_id == "base").drivers:
        lessons.append(
            {
                "lesson_id": "allocated-lineage:" + driver.initiative_id,
                "initiative_id": driver.initiative_id,
                "scenario_id": "base",
                "assumption_ids": list(dict.fromkeys(getattr(driver, f) for f in EXPECTED_UNITS if hasattr(driver, f))),
                "source_records": [
                    {k: v for k, v in a.model_dump(mode="json").items() if k != "pool_id"}
                    for a in book.assignments
                    if a.pool_id == driver.benefit_pool
                ],
                "finding": "Authored measurement and work scope; complete source records remain assigned once to the same pool.",
                "response": "Recompute the selected scope, retain prior definitions and preserve frozen financial claims.",
                "follow_up_evidence": "A sponsor and finance reviewer must validate actual populations and measurements before a pilot.",
            }
        )
    return SourceCasePayload.model_validate(
        {
            **prior.model_dump(mode="json"),
            "underwriting": case.model_dump(mode="json"),
            "operating_plan": plan.model_dump(mode="json"),
            "operating_sources": book.model_dump(mode="json"),
            "challenged_revision_id": parent.revision_id,
            "challenged_revision_sha256": parent.content_sha256,
            "lessons": lessons,
        }
    )


def definition(
    source: SourceCasePayload, identity: str, key: str, *, predecessors: tuple[str, ...] = ()
) -> AllocatedKpiDefinition:
    case, book = source.underwriting, source.operating_sources
    assert isinstance(case, InteractionCase) and isinstance(book, AllocatedSourceBook)
    driver = next(d for d in case.scenarios[0].drivers if d.initiative_id == identity)
    pool = next(p for p in case.interaction_policy.pools if p.pool_id == driver.benefit_pool)
    return AllocatedKpiDefinition.model_validate(
        {
            "definition_id": key,
            "initiative_id": identity,
            "metric": next(metric for metric, kind in METRIC_KIND.items() if kind == driver.kind),
            "population": [
                {k: v for k, v in a.model_dump(mode="json").items() if k != "pool_id"}
                for a in book.assignments
                if a.pool_id == driver.benefit_pool
            ],
            "allocation_scope": {
                "pool_id": pool.pool_id,
                "mode": pool.mode,
                "population_share": population_shares(case)[identity],
            },
            "baseline_start": "2026-12-01",
            "baseline_end": "2026-12-31",
            "baseline_numerator": "0",
            "baseline_denominator": "100",
            "target": ".025" if driver.kind == "pricing" else ".90",
            "target_on": "2027-09-30",
            "predecessor_definition_ids": predecessors,
            "rationale": "Constructed scoped measurement contract. Baseline and target are authored, not company observations; shares do not distribute historical readings.",
        }
    )


def draft(
    parent: CaseRevision,
    source: SourceCasePayload,
    kpis: AllocatedKpiBook,
    when: date,
    reason: str,
    event: LineageEvent | None = None,
) -> RevisionDraft:
    prior = parent.draft.payload
    events = prior.lineage_events if isinstance(prior, AllocatedLineageCasePayload) else ()
    return RevisionDraft(
        stage="ownership_review",
        effective_on=when,
        reason=reason,
        payload=AllocatedLineageCasePayload(
            schema_version=5, basis=source, kpis=kpis, lineage_events=(*events, event) if event else events
        ),
    )


def seed_allocated_lineage(parent: CaseRevision) -> RevisionDraft:
    prior = source_payload(parent.draft.payload)
    if prior is None or not isinstance(prior.underwriting, InteractionCase):
        raise ValueError("allocated lifecycle requires its native allocation case")
    source = basis(parent, prior.underwriting, prior.operating_plan)
    definitions = tuple(
        definition(source, d.initiative_id, d.initiative_id + "-full-v1")
        for d in prior.underwriting.scenarios[0].drivers
    )
    observations = tuple(
        reading(d.initiative_id + "-jan", d.definition_id, date(2027, 1, 1), "2", "100") for d in definitions
    )
    return draft(
        parent,
        source,
        AllocatedKpiBook(definitions=definitions, observations=observations),
        date(2027, 1, 31),
        "Register exact full-pool KPI scopes and constructed January readings; aggregate only selected candidates.",
    )


def partition_allocated_lineage(parent: CaseRevision) -> RevisionDraft:
    prior = parent.draft.payload
    assert isinstance(prior, AllocatedLineageCasePayload)
    raw = prior.underwriting.model_dump(mode="json")
    pool = next(p for p in raw["interaction_policy"]["pools"] if PARENT in p["initiative_ids"])
    pool.update(
        mode="partition",
        shares=[{"initiative_id": i, "share": ".6" if i == PARENT else ".4"} for i in pool["initiative_ids"]],
        rationale="Authored bounded rollout: 60% targeted scope, 40% competing approach deferred. This is a new policy, not a physical record split.",
    )
    case = InteractionCase.model_validate(raw)
    plan = OperatingPlan.model_validate(
        {**prior.operating_plan.model_dump(mode="json"), "underwriting_sha256": fingerprint(case)}
    )
    source = basis(parent, case, plan)
    definitions = []
    for old in prior.kpis.definitions:
        if old.initiative_id in pool["initiative_ids"]:
            new = definition(source, old.initiative_id, old.initiative_id + "-partition-v1").model_dump(mode="json")
            new.update(revision_kind="scope_correction", supersedes_definition_id=old.definition_id)
            definitions.append(AllocatedKpiDefinition.model_validate(new))
    return draft(
        parent,
        source,
        AllocatedKpiBook(definitions=(*prior.kpis.definitions, *definitions), observations=prior.kpis.observations),
        date(2027, 2, 1),
        "Explicitly revise pricing policy and KPI scopes to a 60% selected / 40% deferred partition; retain earlier full-pool observations.",
    )


def remap_inputs(
    prior: AllocatedLineageCasePayload, mapping: dict[str, dict[str, Decimal]]
) -> tuple[InteractionCase, OperatingPlan, list[dict[str, str]]]:
    """Authored identity transition with proportional work effort and fixed budgets."""
    raw = prior.underwriting.model_dump(mode="json")

    def mapped(identity: str) -> dict[str, Decimal]:
        return mapping.get(identity, {identity: Decimal(1)})

    def shares(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: dict[str, Decimal] = {}
        for item in items:
            for successor, fraction in mapped(item["initiative_id"]).items():
                result[successor] = result.get(successor, Decimal(0)) + Decimal(item["share"]) * fraction
        return [{"initiative_id": i, "share": str(s)} for i, s in result.items()]

    for scenario in raw["scenarios"]:
        drivers = {}
        for driver in scenario["drivers"]:
            for successor in mapped(driver["initiative_id"]):
                drivers[successor] = {**driver, "initiative_id": successor}
        scenario["drivers"] = list(drivers.values())
        for cost in scenario["costs"]:
            cost["initiative_ids"] = list(dict.fromkeys(n for i in cost["initiative_ids"] for n in mapped(i)))
    policy = raw["interaction_policy"]
    policy["selected_initiatives"] = list(dict.fromkeys(n for i in policy["selected_initiatives"] for n in mapped(i)))
    for pool in policy["pools"]:
        pool["initiative_ids"] = list(dict.fromkeys(n for i in pool["initiative_ids"] for n in mapped(i)))
        pool["shares"] = shares(pool["shares"])
    for cost in policy["cost_allocations"]:
        cost["shares"] = shares(cost["shares"])
    case = InteractionCase.model_validate(raw)
    plan = prior.operating_plan.model_dump(mode="json")
    task_map = {
        t["task_id"]: {i: t["task_id"].split(":")[0] + ":" + i for i in mapping[t["initiative_id"]]}
        for t in plan["tasks"]
        if t["initiative_id"] in mapping
    }
    task_edges = [
        {"predecessor_id": key, "successor_id": target}
        for key, targets in task_map.items()
        for target in targets.values()
    ]
    tasks: dict[str, dict[str, Any]] = {}
    for original in plan["tasks"]:
        identity = original["initiative_id"]
        for successor, fraction in mapped(identity).items():
            task = deepcopy(original)
            if identity in mapping:
                task.update(
                    task_id=task_map[original["task_id"]][successor], initiative_id=successor, workstream_id=successor
                )
                for demand in task["demands"]:
                    demand["hours_per_week"] = str(Decimal(demand["hours_per_week"]) * fraction)
            task["prerequisites"] = list(
                dict.fromkeys(
                    new
                    for p in original["prerequisites"]
                    for new in (
                        [task_map[p][successor]]
                        if p in task_map and successor in task_map[p]
                        else list(task_map.get(p, {"same": p}).values())
                    )
                )
            )
            if task["task_id"] in tasks:
                existing = tasks[task["task_id"]]
                for demand in existing["demands"]:
                    demand["hours_per_week"] = str(
                        Decimal(demand["hours_per_week"])
                        + next(
                            Decimal(d["hours_per_week"])
                            for d in task["demands"]
                            if d["resource_id"] == demand["resource_id"]
                        )
                    )
                existing["prerequisites"] = list(dict.fromkeys([*existing["prerequisites"], *task["prerequisites"]]))
            else:
                tasks[task["task_id"]] = task
    gates = {
        n: task_map.get(g["task_id"], {}).get(n, g["task_id"])
        for g in plan["benefit_gates"]
        for n in mapped(g["initiative_id"])
    }
    plan.update(
        underwriting_sha256=fingerprint(case),
        tasks=list(tasks.values()),
        priority_order=list(
            dict.fromkeys(n for key in plan["priority_order"] for n in task_map.get(key, {"same": key}).values())
        ),
        benefit_gates=[{"initiative_id": i, "task_id": t} for i, t in gates.items()],
        revision_id=plan["revision_id"] + ":lineage",
        sequencing_rationale="Authored proportional task effort through explicit lineage. Total resource budgets and concurrency are unchanged; split workstreams may delay benefit gates.",
    )
    return case, OperatingPlan.model_validate(plan), task_edges


def transition(parent: CaseRevision, mapping: dict[str, dict[str, Decimal]], when: date) -> RevisionDraft:
    prior = parent.draft.payload
    assert isinstance(prior, AllocatedLineageCasePayload)
    case, plan, task_edges = remap_inputs(prior, mapping)
    source = basis(parent, case, plan)
    retired = {d.supersedes_definition_id for d in prior.kpis.definitions}
    heads = {d.initiative_id: d for d in prior.kpis.definitions if d.definition_id not in retired}
    definitions = tuple(
        definition(
            source,
            successor,
            successor + "-v1",
            predecessors=tuple(heads[i].definition_id for i, targets in mapping.items() if successor in targets),
        )
        for successor in sorted({n for targets in mapping.values() for n in targets})
    )
    event = LineageEvent.model_validate(
        {
            "parent_revision_id": parent.revision_id,
            "parent_revision_sha256": parent.content_sha256,
            "prior_underwriting_sha256": fingerprint(prior.underwriting),
            "revised_underwriting_sha256": fingerprint(case),
            "effective_on": when,
            "edges": [
                {"predecessor_id": i, "successor_id": n, "reference_allocation": s}
                for i, targets in mapping.items()
                for n, s in targets.items()
            ],
            "task_edges": task_edges,
            "rationale": "Authored split or consolidation of allocated pricing work; no change to full reference populations, unit economics or source records.",
            "allocation_basis": "Conserve pool shares and cost explanations; distribute task effort explicitly. Historical readings and financial claims stay on their exact original definitions.",
        }
    )
    return draft(
        parent,
        source,
        AllocatedKpiBook(definitions=(*prior.kpis.definitions, *definitions), observations=prior.kpis.observations),
        when,
        "Change initiative identities with conserved pool shares and explicit task ancestry; require new scoped measurements.",
        event,
    )


def split_allocated_lineage(parent: CaseRevision) -> RevisionDraft:
    return transition(parent, {PARENT: {CHILDREN[0]: Decimal(".4"), CHILDREN[1]: Decimal(".6")}}, date(2027, 2, 28))


def measure_allocated_lineage(parent: CaseRevision, *, complete: bool = False) -> RevisionDraft:
    prior = parent.draft.payload
    assert isinstance(prior, AllocatedLineageCasePayload)
    definitions = prior.kpis.definitions
    observations: tuple[LineageKpiReading, ...]
    if complete:
        old = next(d for d in definitions if d.definition_id == CHILDREN[0] + "-v1")
        revised = AllocatedKpiDefinition.model_validate(
            {
                **old.model_dump(mode="json"),
                "definition_id": CHILDREN[0] + "-v2",
                "target": ".04",
                "revision_kind": "target_change",
                "supersedes_definition_id": old.definition_id,
                "predecessor_definition_ids": [],
            }
        )
        definitions = (*definitions, revised)
        observations = (
            reading(
                "wave-a-march-correction",
                old.definition_id,
                date(2027, 3, 1),
                "8000",
                "200000",
                previous="wave-a-march",
            ),
            reading("wave-a-current-target", revised.definition_id, date(2027, 3, 1), "8000", "200000"),
            reading("wave-b-march", CHILDREN[1] + "-v1", date(2027, 3, 1), "9000", "300000"),
        )
    else:
        observations = (reading("wave-a-march", CHILDREN[0] + "-v1", date(2027, 3, 1), "6000", "200000"),)
    return draft(
        parent,
        basis(parent, prior.underwriting, prior.operating_plan),
        AllocatedKpiBook(definitions=definitions, observations=(*prior.kpis.observations, *observations)),
        date(2027, 3, 31),
        "Correct a prior reading, retain its old target and add independently authored current scoped measurements."
        if complete
        else "Record one child measurement; withhold the aggregate while the other child is unmeasured.",
    )


def merge_allocated_lineage(parent: CaseRevision) -> RevisionDraft:
    return transition(parent, {i: {MERGED: Decimal(1)} for i in CHILDREN}, date(2027, 4, 30))
