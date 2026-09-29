"""Authored Progress lineage exercise; no actual company observations or decisions."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

from .cases import CaseRevision, RevisionDraft, digest
from .lineage import LineageCasePayload, LineageEvent
from .lineage_kpis import LineageKpiBook, LineageKpiDefinition, LineageKpiReading
from .operating_sources import OperatingSourceBook, PartitionedSourceBook, operating_records, source_records
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import SourceCasePayload, source_payload
from .underwriting import EXPECTED_UNITS, UnderwritingCase, month_end

PARENT = "pricing-renewals"
CHILDREN = ("pricing-spring", "pricing-other")
MERGED = "pricing-combined"


def partition_book(source: SourceCasePayload) -> PartitionedSourceBook:
    if isinstance(source.operating_sources, PartitionedSourceBook):
        return source.operating_sources
    records = source.operating_sources
    if not isinstance(records, OperatingSourceBook):
        raise ValueError("alternative pool shares cannot be converted to physical source ownership")
    drivers: dict[str, str] = {d.kind: d.initiative_id for d in source.underwriting.scenarios[0].drivers}
    kinds = {"renewal": "pricing", "service_month": "service", "invoice": "collections"}
    return PartitionedSourceBook.model_validate(
        {
            "schema_version": 2,
            "records": records.model_dump(mode="json"),
            "assignments": [
                {
                    "kind": kind,
                    "record_id": key,
                    "record_sha256": fingerprint(row),
                    "initiative_id": drivers[kinds[kind]],
                }
                for (kind, key), row in operating_records(records).items()
            ],
            "partition_rationale": "Authored complete source ownership; subsequent splits retain one owner per record.",
        }
    )


def definition(
    book: PartitionedSourceBook,
    identity: str,
    key: str,
    metric: str,
    denominator: Decimal,
    *,
    numerator: Decimal = Decimal(0),
    baseline: date = date(2027, 2, 1),
    predecessors: tuple[str, ...] = (),
) -> LineageKpiDefinition:
    return LineageKpiDefinition.model_validate(
        {
            "definition_id": key,
            "initiative_id": identity,
            "metric": metric,
            "population": [
                {k: v for k, v in a.model_dump(mode="json").items() if k != "initiative_id"}
                for a in book.assignments
                if a.initiative_id == identity
            ],
            "baseline_start": baseline,
            "baseline_end": month_end(baseline),
            "baseline_numerator": numerator,
            "baseline_denominator": denominator,
            "target": "0.025"
            if metric == "net_price_uplift"
            else "0.90"
            if metric == "service_quality_pass_rate"
            else "0.70",
            "target_on": date(2027, 9, 30),
            "predecessor_definition_ids": predecessors,
            "rationale": "Authored constructed KPI reference and target. Population is explicit; no company baseline, approval or observed financial impact is asserted.",
        }
    )


def reading(
    key: str, definition_id: str, start: date, numerator: str, denominator: str, *, previous: str | None = None
) -> LineageKpiReading:
    text = f"Constructed exercise observation {key}: numerator {numerator}, denominator {denominator}, definition {definition_id}. Authored for lineage validation; not an extraction from a company system or a causal financial claim."
    return LineageKpiReading(
        observation_id=key,
        definition_id=definition_id,
        start=start,
        end=month_end(start),
        numerator=Decimal(numerator),
        denominator=Decimal(denominator),
        evidence=text,
        evidence_sha256=digest(text),
        supersedes_observation_id=previous,
    )


def source_basis(
    parent: CaseRevision, case: UnderwritingCase, plan: OperatingPlan, book: PartitionedSourceBook
) -> SourceCasePayload:
    prior = source_payload(parent.draft.payload)
    if prior is None:
        raise ValueError("lineage exercise requires a source-backed parent")
    if not isinstance(prior.underwriting, UnderwritingCase):
        raise ValueError("lineage exercise requires the legacy disjoint-population case")
    previous_book = partition_book(prior)
    current_rows = operating_records(book.records)
    lessons = []
    for driver in next(s for s in prior.underwriting.scenarios if s.scenario_id == "base").drivers:
        references = [
            (a.kind, a.record_id) for a in previous_book.assignments if a.initiative_id == driver.initiative_id
        ]
        lessons.append(
            {
                "lesson_id": "lineage:" + driver.initiative_id,
                "initiative_id": driver.initiative_id,
                "scenario_id": "base",
                "assumption_ids": list(dict.fromkeys(getattr(driver, f) for f in EXPECTED_UNITS if hasattr(driver, f))),
                "source_records": [
                    {"kind": kind, "record_id": key, "record_sha256": fingerprint(current_rows[(kind, key)])}
                    for kind, key in references
                ],
                "finding": "These authored records retain the predecessor's economic scope during the identity/KPI review. This is not a new causal finding.",
                "response": "Preserve prior lessons in their signed revisions; bind this review to the immediate predecessor's definitions and source records.",
                "follow_up_evidence": "A permissioned operator and finance reviewer must validate actual populations, KPI definitions and attribution separately.",
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
            "decision_question": "Does the explicitly mapped initiative and KPI history preserve scope, costs and decision authority?",
        }
    )


def seed_lineage(parent: CaseRevision) -> RevisionDraft:
    prior = source_payload(parent.draft.payload)
    if prior is None:
        raise ValueError("lineage exercise requires a source-backed parent")
    if not isinstance(prior.underwriting, UnderwritingCase):
        raise ValueError("lineage exercise requires the legacy disjoint-population case")
    book = partition_book(prior)
    definitions = (
        definition(book, PARENT, "pricing-kpi-v1", "net_price_uplift", Decimal(1000000), numerator=Decimal(10000)),
        definition(
            book,
            "service-automation",
            "service-kpi-v1",
            "service_quality_pass_rate",
            Decimal(100),
            numerator=Decimal(80),
        ),
        definition(
            book, "collections-timing", "collections-kpi-v1", "collection_rate", Decimal(100), numerator=Decimal(50)
        ),
    )
    observations = (
        reading("pricing-march", "pricing-kpi-v1", date(2027, 3, 1), "20000", "1000000"),
        reading("service-march", "service-kpi-v1", date(2027, 3, 1), "85", "100"),
        reading("collections-march", "collections-kpi-v1", date(2027, 3, 1), "60", "100"),
    )
    return RevisionDraft(
        stage="ownership_review",
        effective_on=date(2027, 3, 31),
        reason="Introduce constructed KPI baselines and March readings without altering the financial case.",
        payload=LineageCasePayload(
            schema_version=4,
            basis=source_basis(parent, prior.underwriting, prior.operating_plan, book),
            lineage_events=(),
            kpis=LineageKpiBook(definitions=definitions, observations=observations),
        ),
    )


def split_lineage(parent: CaseRevision) -> RevisionDraft:
    prior = parent.draft.payload
    if not isinstance(prior, LineageCasePayload):
        raise ValueError("seed lineage and KPI history before splitting the initiative")
    case, plan, book = split_pricing_inputs(
        prior.underwriting, prior.operating_plan, source_records(prior.source_basis.operating_sources)
    )
    event = LineageEvent.model_validate(
        {
            "parent_revision_id": parent.revision_id,
            "parent_revision_sha256": parent.content_sha256,
            "prior_underwriting_sha256": fingerprint(prior.underwriting),
            "revised_underwriting_sha256": fingerprint(case),
            "effective_on": "2027-04-30",
            "edges": [
                {"predecessor_id": PARENT, "successor_id": child, "reference_allocation": share}
                for child, share in zip(CHILDREN, ("0.25", "0.75"), strict=True)
            ],
            "task_edges": [
                {"predecessor_id": name, "successor_id": name + ":" + child}
                for name in ("pricing-review", "pricing-gate")
                for child in CHILDREN
            ],
            "rationale": "Separate the spring-capped renewal from the remaining contracts for explicit operating review. Management concurrency and resource budgets are unchanged.",
            "allocation_basis": "Reference revenue populations 250,000 / 750,000; every source contract has one owner. Shared commitments remain once. Historical parent observations are not allocated to children.",
        }
    )
    definitions = tuple(
        definition(
            book,
            child,
            child + "-kpi-v1",
            "net_price_uplift",
            Decimal(amount),
            baseline=date(2027, 3, 1),
            predecessors=("pricing-kpi-v1",),
        )
        for child, amount in zip(CHILDREN, (250000, 750000), strict=True)
    )
    observations = (
        reading("spring-april", CHILDREN[0] + "-kpi-v1", date(2027, 4, 1), "10000", "250000"),
        reading("other-april", CHILDREN[1] + "-kpi-v1", date(2027, 4, 1), "7500", "750000"),
        reading("service-april", "service-kpi-v1", date(2027, 4, 1), "86", "100"),
        reading("collections-april", "collections-kpi-v1", date(2027, 4, 1), "65", "100"),
    )
    return RevisionDraft(
        stage="ownership_review",
        effective_on=date(2027, 4, 30),
        reason="Split pricing into disjoint source cohorts and preserve predecessor KPI definitions.",
        payload=LineageCasePayload(
            schema_version=4,
            basis=source_basis(parent, case, plan, book),
            lineage_events=(*prior.lineage_events, event),
            kpis=LineageKpiBook(
                definitions=(*prior.kpis.definitions, *definitions),
                observations=(*prior.kpis.observations, *observations),
            ),
        ),
    )


def revise_kpi_target(parent: CaseRevision) -> RevisionDraft:
    prior = parent.draft.payload
    if not isinstance(prior, LineageCasePayload):
        raise ValueError("target revision requires existing lineage history")
    old = next(d for d in prior.kpis.definitions if d.definition_id == CHILDREN[0] + "-kpi-v1")
    target = LineageKpiDefinition.model_validate(
        {
            **old.model_dump(mode="json"),
            "definition_id": CHILDREN[0] + "-kpi-v2",
            "target": "0.04",
            "revision_kind": "target_change",
            "supersedes_definition_id": old.definition_id,
            "predecessor_definition_ids": [],
            "rationale": "Authored target challenge from 2.5% to 4%. Earlier observations retain the earlier definition and target.",
        }
    )
    observations = (
        reading(
            "spring-april-corrected", old.definition_id, date(2027, 4, 1), "7500", "250000", previous="spring-april"
        ),
        reading("spring-may", target.definition_id, date(2027, 5, 1), "8750", "250000"),
        reading("other-may", CHILDREN[1] + "-kpi-v1", date(2027, 5, 1), "7500", "750000"),
        reading("service-may", "service-kpi-v1", date(2027, 5, 1), "88", "100"),
        reading("collections-may", "collections-kpi-v1", date(2027, 5, 1), "68", "100"),
    )
    return RevisionDraft(
        stage="ownership_review",
        effective_on=date(2027, 5, 31),
        reason="Revise a KPI target and append a correction to the earlier reading; no financial attribution is changed.",
        payload=LineageCasePayload(
            schema_version=4,
            basis=source_basis(parent, prior.underwriting, prior.operating_plan, partition_book(prior.source_basis)),
            lineage_events=prior.lineage_events,
            kpis=LineageKpiBook(
                definitions=(*prior.kpis.definitions, target), observations=(*prior.kpis.observations, *observations)
            ),
        ),
    )


def merge_lineage(parent: CaseRevision) -> RevisionDraft:
    prior = parent.draft.payload
    if not isinstance(prior, LineageCasePayload):
        raise ValueError("merge requires existing lineage history")
    raw = prior.underwriting.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        old = [d for d in scenario["drivers"] if d["initiative_id"] in CHILDREN]
        values = {a["assumption_id"]: a for a in scenario["assumptions"]}
        amount = sum((Decimal(values[d["monthly_eligible_revenue"]]["value"]) for d in old), Decimal(0))
        scenario["assumptions"].append(
            {**values[old[0]["monthly_eligible_revenue"]], "assumption_id": MERGED + "-revenue", "value": str(amount)}
        )
        scenario["drivers"] = [d for d in scenario["drivers"] if d["initiative_id"] not in CHILDREN]
        scenario["drivers"].append(
            {
                **old[0],
                "initiative_id": MERGED,
                "title": "Consolidated renewal pricing",
                "benefit_pool": MERGED,
                "monthly_eligible_revenue": MERGED + "-revenue",
            }
        )
        for cost in scenario["costs"]:
            cost["initiative_ids"] = list(dict.fromkeys(MERGED if i in CHILDREN else i for i in cost["initiative_ids"]))
    case = UnderwritingCase.model_validate(raw)
    raw_plan = prior.operating_plan.model_dump(mode="json")
    task_map = {
        phase + ":" + child: phase + ":combined" for phase in ("pricing-review", "pricing-gate") for child in CHILDREN
    }
    tasks = {t["task_id"]: t for t in raw_plan["tasks"]}
    revised = [t for t in raw_plan["tasks"] if t["initiative_id"] not in CHILDREN]
    for phase in ("pricing-review", "pricing-gate"):
        old_tasks = [tasks[phase + ":" + child] for child in CHILDREN]
        new_task = deepcopy(old_tasks[0])
        new_task.update(task_id=phase + ":combined", initiative_id=MERGED, workstream_id=MERGED)
        new_task["title"] = old_tasks[0]["title"].removesuffix(" / spring cohort") + " / consolidated renewals"
        new_task["prerequisites"] = list(
            dict.fromkeys(task_map.get(p, p) for task in old_tasks for p in task["prerequisites"])
        )
        demands: dict[str, Decimal] = {}
        for task in old_tasks:
            for demand in task["demands"]:
                demands[demand["resource_id"]] = demands.get(demand["resource_id"], Decimal(0)) + Decimal(
                    demand["hours_per_week"]
                )
        new_task["demands"] = [
            {"resource_id": resource, "hours_per_week": str(hours)} for resource, hours in demands.items()
        ]
        revised.append(new_task)
    raw_plan.update(
        revision_id=raw_plan["revision_id"] + ":merge",
        underwriting_sha256=fingerprint(case),
        tasks=revised,
        priority_order=list(dict.fromkeys(task_map.get(t, t) for t in raw_plan["priority_order"])),
        benefit_gates=[g for g in raw_plan["benefit_gates"] if g["initiative_id"] not in CHILDREN]
        + [{"initiative_id": MERGED, "task_id": "pricing-gate:combined"}],
    )
    plan = OperatingPlan.model_validate(raw_plan)
    raw_book = partition_book(prior.source_basis).model_dump(mode="json")
    raw_book["records"].update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    for assignment in raw_book["assignments"]:
        if assignment["initiative_id"] in CHILDREN:
            assignment["initiative_id"] = MERGED
    raw_book["partition_rationale"] = (
        "Authored consolidation of the same disjoint pricing cohorts under one new identity; no added source record, cost removal or retrospective child actuals."
    )
    book = PartitionedSourceBook.model_validate(raw_book)
    event = LineageEvent.model_validate(
        {
            "parent_revision_id": parent.revision_id,
            "parent_revision_sha256": parent.content_sha256,
            "prior_underwriting_sha256": fingerprint(prior.underwriting),
            "revised_underwriting_sha256": fingerprint(case),
            "effective_on": "2027-06-30",
            "edges": [
                {"predecessor_id": child, "successor_id": MERGED, "reference_allocation": "1"} for child in CHILDREN
            ],
            "task_edges": [{"predecessor_id": a, "successor_id": b} for a, b in task_map.items()],
            "rationale": "Consolidate the two constructed pricing workstreams after reviewing the separate KPI histories.",
            "allocation_basis": "Both predecessor populations map in full to the new initiative. Costs retain their IDs, amounts and timing once; prior readings remain on their exact definitions.",
        }
    )
    merged_kpi = definition(
        book,
        MERGED,
        "pricing-combined-kpi-v1",
        "net_price_uplift",
        Decimal(1000000),
        numerator=Decimal(16250),
        baseline=date(2027, 5, 1),
        predecessors=(CHILDREN[0] + "-kpi-v2", CHILDREN[1] + "-kpi-v1"),
    )
    observations = (
        reading("combined-june", merged_kpi.definition_id, date(2027, 6, 1), "18000", "1000000"),
        reading("service-june", "service-kpi-v1", date(2027, 6, 1), "90", "100"),
        reading("collections-june", "collections-kpi-v1", date(2027, 6, 1), "70", "100"),
    )
    return RevisionDraft(
        stage="ownership_review",
        effective_on=date(2027, 6, 30),
        reason="Consolidate the pricing initiatives with explicit predecessor mappings and preserved target/observation history.",
        payload=LineageCasePayload(
            schema_version=4,
            basis=source_basis(parent, case, plan, book),
            lineage_events=(*prior.lineage_events, event),
            kpis=LineageKpiBook(
                definitions=(*prior.kpis.definitions, merged_kpi),
                observations=(*prior.kpis.observations, *observations),
            ),
        ),
    )


def split_pricing_inputs(
    case: UnderwritingCase, plan: OperatingPlan, book: OperatingSourceBook
) -> tuple[UnderwritingCase, OperatingPlan, PartitionedSourceBook]:
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
                    "title": "Spring-capped renewal pricing" if child == CHILDREN[0] else "Other renewal pricing",
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
    raw_plan["revision_id"] += ":lineage-split"
    # Preserve the management concurrency limit; splitting the effort does not
    # create more management capacity. The shared scheduler may delay work.
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
            new["title"] += " / " + ("spring cohort" if child == CHILDREN[0] else "other contracts")
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
