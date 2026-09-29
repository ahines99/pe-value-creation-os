"""Explicit split/merge lineage with conserved source ownership and immutable KPI history."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from .allocation_kpis import AllocatedKpiBook, AllocatedKpiDefinition, allocated_kpi_report
from .exit_review import ExitReviewPayload
from .interactions import InteractionCase, population_shares
from .lineage_kpis import METRIC_KIND, LineageKpiBook, kpi_report
from .models import Record
from .operating_sources import (
    AllocatedSourceBook,
    PartitionedSourceBook,
    operating_records,
    source_forecast,
    source_records,
)
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import SHA, UUID, SourceCasePayload, source_payload
from .underwriting import EXPECTED_UNITS, Entry, UnderwritingCase, month_end, month_start, totals
from .underwriting_models import UnderwritingModel

if TYPE_CHECKING:
    from .cases import CaseRevision

EXTENTS = {
    "pricing": {"monthly_eligible_revenue"},
    "service": {"monthly_contacts", "monthly_cost_action", "monthly_addressable_spend"},
    "collections": {"receivables_balance"},
}


class LineageEdge(Record):
    predecessor_id: str = Field(min_length=1)
    successor_id: str = Field(min_length=1)
    reference_allocation: Decimal = Field(gt=0, le=1)


class TaskLineageEdge(Record):
    predecessor_id: str = Field(min_length=1)
    successor_id: str = Field(min_length=1)


class LineageEvent(Record):
    parent_revision_id: str = Field(pattern=UUID)
    parent_revision_sha256: str = Field(pattern=SHA)
    prior_underwriting_sha256: str = Field(pattern=SHA)
    revised_underwriting_sha256: str = Field(pattern=SHA)
    effective_on: date
    edges: tuple[LineageEdge, ...] = Field(min_length=1)
    task_edges: tuple[TaskLineageEdge, ...]
    rationale: str = Field(min_length=1)
    allocation_basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def shares(self) -> Self:
        keys = [(e.predecessor_id, e.successor_id) for e in self.edges]
        before, after = {a for a, _ in keys}, {b for _, b in keys}
        if len(set(keys)) != len(keys) or before & after or "shared" in before | after:
            raise ValueError("lineage edges require distinct retired/new identities and no duplicate edge")
        for predecessor in before:
            if sum((e.reference_allocation for e in self.edges if e.predecessor_id == predecessor), Decimal(0)) != 1:
                raise ValueError("lineage reference allocations must conserve each predecessor exactly")
        for successor in after:
            incoming = [e for e in self.edges if e.successor_id == successor]
            if len(incoming) > 1 and any(
                sum(e.predecessor_id == edge.predecessor_id for edge in self.edges) > 1 for e in incoming
            ):
                raise ValueError("many-to-many remapping requires separate explicit split and merge revisions")
        task_keys = [(e.predecessor_id, e.successor_id) for e in self.task_edges]
        if len(set(task_keys)) != len(task_keys) or {a for a, _ in task_keys} & {b for _, b in task_keys}:
            raise ValueError("task lineage requires distinct retired/new identities and no duplicate edge")
        return self


class _LineagePayload(Record):
    schema_version: Literal[4, 5]
    basis: SourceCasePayload | ExitReviewPayload
    lineage_events: tuple[LineageEvent, ...]
    kpis: LineageKpiBook | AllocatedKpiBook

    @property
    def source_basis(self) -> SourceCasePayload:
        return self.basis.source_basis if isinstance(self.basis, ExitReviewPayload) else self.basis

    @property
    def exit_basis(self) -> ExitReviewPayload | None:
        return self.basis if isinstance(self.basis, ExitReviewPayload) else None

    @property
    def underwriting(self) -> UnderwritingModel:
        if self.schema_version == 4 and not isinstance(self.source_basis.underwriting, UnderwritingCase):
            raise ValueError(
                "physical split/merge lineage requires disjoint source ownership, not alternative pool shares"
            )
        return self.source_basis.underwriting

    @property
    def operating_plan(self) -> OperatingPlan:
        return self.source_basis.operating_plan

    @model_validator(mode="after")
    def scope(self) -> Self:
        allocated = self.schema_version == 5
        if allocated and (
            not isinstance(self.source_basis.operating_sources, AllocatedSourceBook)
            or not isinstance(self.underwriting, InteractionCase)
            or not isinstance(self.kpis, AllocatedKpiBook)
        ):
            raise ValueError("allocated lineage requires a native allocation case, source book and KPI scopes")
        if not allocated and not isinstance(self.source_basis.operating_sources, PartitionedSourceBook):
            raise ValueError("lineage requires explicit source-record ownership")
        seen: set[str] = set()
        seen_tasks: set[str] = set()
        for event in self.lineage_events:
            successors = {e.successor_id for e in event.edges}
            if successors & seen:
                raise ValueError("retired or previously used initiative identities cannot be reused")
            seen |= successors | {e.predecessor_id for e in event.edges}
            new_tasks = {e.successor_id for e in event.task_edges}
            if new_tasks & seen_tasks:
                raise ValueError("retired or previously used task identities cannot be reused")
            seen_tasks |= new_tasks | {e.predecessor_id for e in event.task_edges}
        drivers = {d.initiative_id: d for d in self.underwriting.scenarios[0].drivers}
        replaced = {d.supersedes_definition_id for d in self.kpis.definitions}
        active = [d for d in self.kpis.definitions if d.definition_id not in replaced and d.initiative_id in drivers]
        if len(active) != len(drivers) or {d.initiative_id for d in active} != set(drivers):
            raise ValueError("each current initiative requires one active KPI definition")
        book = self.source_basis.operating_sources
        end = month_end(self.underwriting.start, self.underwriting.months - 1)
        if any(d.target_on > end for d in self.kpis.definitions) or any(
            o.start < self.underwriting.start or o.end > end for o in self.kpis.observations
        ):
            raise ValueError("KPI targets and observations must remain within the case calendar")
        assert isinstance(book, (AllocatedSourceBook, PartitionedSourceBook))
        owners = (
            {(a.kind, a.record_id): (a.pool_id, a.record_sha256) for a in book.assignments}
            if isinstance(book, AllocatedSourceBook)
            else {(a.kind, a.record_id): (a.initiative_id, a.record_sha256) for a in book.assignments}
        )
        for definition in active:
            owner = drivers[definition.initiative_id].benefit_pool if allocated else definition.initiative_id
            owned = {key for key, value in owners.items() if value[0] == owner}
            if {(r.kind, r.record_id) for r in definition.population} != owned or any(
                owners[(r.kind, r.record_id)][1] != r.record_sha256 for r in definition.population
            ):
                raise ValueError("current KPI population must bind every exact source record owned by its initiative")
            if METRIC_KIND[definition.metric] != drivers[definition.initiative_id].kind:
                raise ValueError("KPI metric must match its initiative mechanism")
            if allocated:
                assert isinstance(self.underwriting, InteractionCase)
                assert isinstance(definition, AllocatedKpiDefinition)
                rule = next(p for p in self.underwriting.interaction_policy.pools if p.pool_id == owner)
                scope = definition.allocation_scope
                if (scope.pool_id, scope.mode, scope.population_share) != (
                    owner,
                    rule.mode,
                    population_shares(self.underwriting)[definition.initiative_id],
                ):
                    raise ValueError("current KPI allocation scope must match its exact pool, mode and share")
        return self

    def bind_parent(self, parent: CaseRevision, effective_on: date) -> None:
        self.source_basis.bind_parent(parent)
        prior_source = source_payload(parent.draft.payload)
        if prior_source is None:
            raise ValueError("lineage requires a source-backed parent")
        prior = parent.draft.payload
        if isinstance(prior, _LineagePayload) and prior.schema_version != self.schema_version:
            raise ValueError("physical and allocated KPI histories require separate measurement contracts")
        events = prior.lineage_events if isinstance(prior, _LineagePayload) else ()
        previous_kpis = prior.kpis if isinstance(prior, _LineagePayload) else LineageKpiBook()
        self.kpis.retain(previous_kpis)
        if self.lineage_events[: len(events)] != events:
            raise ValueError("lineage history cannot be discarded or rewritten")
        old = {d.initiative_id: d for d in prior.underwriting.scenarios[0].drivers}
        new = {d.initiative_id: d for d in self.underwriting.scenarios[0].drivers}
        old_tasks = {t.task_id: t for t in prior_source.operating_plan.tasks}
        new_tasks = {t.task_id: t for t in self.operating_plan.tasks}
        if any(
            old_tasks[key].initiative_id != new_tasks[key].initiative_id for key in old_tasks.keys() & new_tasks.keys()
        ):
            raise ValueError("unchanged task identity must retain initiative ownership; use explicit task lineage")
        before, after = set(old) - set(new), set(new) - set(old)
        if bool(before) != bool(after):
            raise ValueError("lineage cannot silently add or remove an economic initiative")
        event = None
        if before:
            if len(self.lineage_events) != len(events) + 1:
                raise ValueError("identity changes require one new explicit lineage event")
            event = self.lineage_events[-1]
            if (
                event.parent_revision_id,
                event.parent_revision_sha256,
                event.prior_underwriting_sha256,
                event.revised_underwriting_sha256,
                event.effective_on,
            ) != (
                parent.revision_id,
                parent.content_sha256,
                fingerprint(prior.underwriting),
                fingerprint(self.underwriting),
                effective_on,
            ):
                raise ValueError("lineage event must bind the exact prior/revised inputs and effective date")
            if {e.predecessor_id for e in event.edges} != before or {e.successor_id for e in event.edges} != after:
                raise ValueError("lineage must map every retired identity to the complete successor set")
            validate_partition_transition(prior_source, self.source_basis, event)
        elif self.lineage_events != events:
            raise ValueError("lineage event requires an actual identity change")
        elif {t.task_id for t in prior_source.operating_plan.tasks} != {t.task_id for t in self.operating_plan.tasks}:
            raise ValueError("task identity changes require an explicit lineage transition")
        for identity in set(old) & set(new):
            if (old[identity].kind, old[identity].benefit_pool) != (new[identity].kind, new[identity].benefit_pool):
                raise ValueError("unchanged initiative identity must retain its mechanism and pool")
        definitions = {d.definition_id: d for d in self.kpis.definitions}
        prior_definitions = {d.definition_id: d for d in previous_kpis.definitions}
        for definition in self.kpis.definitions[len(previous_kpis.definitions) :]:
            if definition.initiative_id not in new:
                raise ValueError("new KPI definitions require a current initiative")
            if definition.baseline_end > effective_on:
                raise ValueError("KPI baseline cannot be future evidence at the authored revision date")
            if definition.initiative_id in after:
                required = (
                    {e.predecessor_id for e in event.edges if e.successor_id == definition.initiative_id}
                    if event
                    else set()
                )
                predecessors = definition.predecessor_definition_ids
                if (
                    any(p not in prior_definitions for p in predecessors)
                    or {definitions[p].initiative_id for p in predecessors} != required
                ):
                    raise ValueError("split/merge KPI must retain the exact predecessor initiative definitions")
                retired = {d.supersedes_definition_id for d in previous_kpis.definitions}
                if any(p in retired for p in predecessors):
                    raise ValueError("split/merge KPI requires the current predecessor target revision")
            elif definition.predecessor_definition_ids:
                raise ValueError("KPI population predecessor requires a matching initiative transition")
        replaced = {d.supersedes_definition_id for d in self.kpis.definitions}
        active_definitions = {
            d.definition_id for d in self.kpis.definitions if d.initiative_id in new and d.definition_id not in replaced
        }
        for observation in self.kpis.observations[len(previous_kpis.observations) :]:
            if observation.supersedes_observation_id is None and observation.definition_id not in active_definitions:
                raise ValueError(
                    "new KPI readings require a current definition; earlier readings require explicit corrections"
                )
            if observation.end > effective_on:
                raise ValueError("KPI observation cannot be future evidence at the authored revision date")


class LineageCasePayload(_LineagePayload):
    schema_version: Literal[4]
    kpis: LineageKpiBook

    @property
    def underwriting(self) -> UnderwritingCase:
        case = super().underwriting
        if not isinstance(case, UnderwritingCase):
            raise ValueError("physical lineage requires disjoint source ownership")
        return case


class AllocatedLineageCasePayload(_LineagePayload):
    schema_version: Literal[5]
    kpis: AllocatedKpiBook

    @property
    def underwriting(self) -> InteractionCase:
        case = super().underwriting
        if not isinstance(case, InteractionCase):
            raise ValueError("allocated lineage requires a native allocation case")
        return case


LineagePayload = LineageCasePayload | AllocatedLineageCasePayload
LINEAGE_PAYLOAD_TYPES = (LineageCasePayload, AllocatedLineageCasePayload)


def validate_partition_transition(prior: SourceCasePayload, current: SourceCasePayload, event: LineageEvent) -> None:
    before_book, after_book = prior.operating_sources, current.operating_sources
    assert isinstance(after_book, (PartitionedSourceBook, AllocatedSourceBook))
    allocated = isinstance(after_book, AllocatedSourceBook)
    before_rows, after_rows = operating_records(source_records(before_book)), operating_records(after_book.records)
    if before_rows != after_rows:
        raise ValueError(
            "identity-only transition must preserve source records; append evidence corrections separately"
        )
    kind = {"renewal": "pricing", "service_month": "service", "invoice": "collections"}
    old_drivers: dict[str, str] = {d.kind: d.initiative_id for d in prior.underwriting.scenarios[0].drivers}
    owners = (
        {(a.kind, a.record_id): a.initiative_id for a in before_book.assignments}
        if isinstance(before_book, PartitionedSourceBook)
        else {key: old_drivers[kind[key[0]]] for key in before_rows}
    )
    allowed = {(e.predecessor_id, e.successor_id) for e in event.edges}
    allowed |= {(d.initiative_id, d.initiative_id) for d in prior.underwriting.scenarios[0].drivers}
    if allocated:
        validate_allocation_transition(prior, current, event)
    else:
        assert isinstance(after_book, PartitionedSourceBook)
        if any((owners[(a.kind, a.record_id)], a.initiative_id) not in allowed for a in after_book.assignments):
            raise ValueError("source ownership cannot cross undeclared initiative lineage")
    old_tasks, new_tasks = (
        {t.task_id: t for t in prior.operating_plan.tasks},
        {t.task_id: t for t in current.operating_plan.tasks},
    )
    if {e.predecessor_id for e in event.task_edges} != old_tasks.keys() - new_tasks.keys() or {
        e.successor_id for e in event.task_edges
    } != new_tasks.keys() - old_tasks.keys():
        raise ValueError("task lineage must map every retired package to the complete successor set")
    for task_edge in event.task_edges:
        old_task, new_task = old_tasks[task_edge.predecessor_id], new_tasks[task_edge.successor_id]
        if (old_task.initiative_id, new_task.initiative_id) not in allowed:
            raise ValueError("task lineage must retain its declared initiative ownership")
    for previous, revised in zip(prior.underwriting.scenarios, current.underwriting.scenarios, strict=True):
        if previous.scenario_id != revised.scenario_id:
            raise ValueError("lineage retains scenario order and identity")
        old = {d.initiative_id: d for d in previous.drivers}
        new = {d.initiative_id: d for d in revised.drivers}
        old_values, new_values = (
            {a.assumption_id: a.value for a in previous.assumptions},
            {a.assumption_id: a.value for a in revised.assumptions},
        )
        for identity in old.keys() & new.keys():
            if old[identity] != new[identity] or any(
                old_values[getattr(old[identity], f)] != new_values[getattr(new[identity], f)]
                for f in EXPECTED_UNITS
                if hasattr(old[identity], f)
            ):
                raise ValueError("identity-only transition cannot change an unrelated driver")
        for edge in event.edges:
            a, b = old[edge.predecessor_id], new[edge.successor_id]
            if a.kind != b.kind or (allocated and a.benefit_pool != b.benefit_pool):
                raise ValueError("lineage cannot change an initiative's economic mechanism")
            for field in EXPECTED_UNITS.keys() - (set() if allocated else EXTENTS[a.kind]):
                if hasattr(a, field) and old_values[getattr(a, field)] != new_values[getattr(b, field)]:
                    raise ValueError(
                        "identity-only transition must retain unit economics; revise assumptions separately"
                    )
            for field in (
                "effective_on",
                "collection_lag_months",
                "variable_cost_payment_lag_months",
                "payment_lag_months",
                "cost_action",
                "counterfactual_collection_on",
            ):
                if getattr(a, field, None) != getattr(b, field, None):
                    raise ValueError("identity-only transition must retain driver timing and cost action")
        for successor in {e.successor_id for e in event.edges} if not allocated else set():
            b = new[successor]
            for field in EXTENTS[b.kind]:
                expected = sum(
                    (
                        old_values[getattr(old[e.predecessor_id], field)] * e.reference_allocation
                        for e in event.edges
                        if e.successor_id == successor
                    ),
                    Decimal(0),
                )
                if new_values[getattr(b, field)] != expected:
                    raise ValueError("lineage must conserve and explicitly allocate the reference population and spend")
        old_costs = {c.cost_id: c for c in previous.costs}
        if {c.cost_id for c in revised.costs} != set(old_costs):
            raise ValueError("identity-only transition must retain every cost exactly once")
        successors = {i: {e.successor_id for e in event.edges if e.predecessor_id == i} for i in old}
        for cost in revised.costs:
            before = old_costs[cost.cost_id]
            expected_owners = set().union(*(successors[i] or {i} for i in before.initiative_ids))
            if (
                set(cost.initiative_ids) != expected_owners
                or any(
                    getattr(cost, k) != getattr(before, k)
                    for k in ("kind", "recognized_on", "paid_on", "retained_if_excluded")
                )
                or new_values[cost.amount] != old_values[before.amount]
            ):
                raise ValueError("lineage must preserve cost amount, timing, retention and complete owner mapping")


def validate_allocation_transition(prior: SourceCasePayload, current: SourceCasePayload, event: LineageEvent) -> None:
    """Conserve pool exposure and fixed cost explanations through an identity change."""
    a, b = prior.underwriting, current.underwriting
    before, after = prior.operating_sources, current.operating_sources
    if not isinstance(a, InteractionCase) or not isinstance(b, InteractionCase):
        raise ValueError("allocated lineage requires a native allocation parent")
    if not isinstance(before, AllocatedSourceBook) or not isinstance(after, AllocatedSourceBook):
        raise ValueError("allocated lineage requires unchanged pool ownership")
    if before.assignments != after.assignments or before.pool_ids != after.pool_ids:
        raise ValueError("identity-only transition must preserve exact source-to-pool assignments")
    if (
        prior.operating_plan.resources != current.operating_plan.resources
        or prior.operating_plan.maximum_active_workstreams != current.operating_plan.maximum_active_workstreams
    ):
        raise ValueError("identity-only transition cannot create resource capacity or change concurrency")
    old_tasks = {t.task_id: t for t in prior.operating_plan.tasks}
    new_tasks = {t.task_id: t for t in current.operating_plan.tasks}
    for identity in old_tasks.keys() & new_tasks.keys():
        if old_tasks[identity] != new_tasks[identity]:
            raise ValueError("identity-only transition cannot change an unrelated work package")
    # Effort is a separately authored operating assumption. It is conserved per
    # resource, not inferred to fall simply because an initiative has split.
    for resource in prior.operating_plan.resources:

        def effort(tasks: dict[str, Any], resource_id: str = resource.resource_id) -> Decimal:
            return sum(
                (
                    t.duration_weeks * d.hours_per_week
                    for t in tasks.values()
                    for d in t.demands
                    if d.resource_id == resource_id
                ),
                Decimal(0),
            )

        if effort(old_tasks) != effort(new_tasks):
            raise ValueError("identity-only transition must conserve authored resource effort")
    successors = {
        d.initiative_id: {
            e.successor_id: e.reference_allocation for e in event.edges if e.predecessor_id == d.initiative_id
        }
        or {d.initiative_id: Decimal(1)}
        for d in a.scenarios[0].drivers
    }

    def mapped(shares: dict[str, Decimal]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for identity, share in shares.items():
            for successor, fraction in successors[identity].items():
                result[successor] = result.get(successor, Decimal(0)) + share * fraction
        return result

    old_policy, new_policy = a.interaction_policy, b.interaction_policy
    rules = {p.pool_id: p for p in new_policy.pools}
    if set(rules) != {p.pool_id for p in old_policy.pools}:
        raise ValueError("identity-only transition cannot add or remove an economic pool")
    old_selected, new_selected = set(old_policy.selected_initiatives), set(new_policy.selected_initiatives)
    if new_selected != set().union(*(set(successors[i]) for i in old_selected)):
        raise ValueError("identity-only transition must preserve selection through lineage")
    for successor in {e.successor_id for e in event.edges}:
        incoming = {e.predecessor_id in old_selected for e in event.edges if e.successor_id == successor}
        if len(incoming) > 1:
            raise ValueError("cannot merge selected and deferred populations in an identity-only transition")
    old_shares, new_shares = population_shares(a), population_shares(b)
    for rule in old_policy.pools:
        revised = rules[rule.pool_id]
        if rule.mode != revised.mode:
            raise ValueError("identity-only transition cannot change pool mode; record policy changes separately")
        expected_members = set().union(*(set(successors[i]) for i in rule.initiative_ids))
        if set(revised.initiative_ids) != expected_members:
            raise ValueError("lineage must preserve complete pool membership")
        if rule.mode == "exclusive" and any(len(successors[i]) != 1 for i in rule.initiative_ids):
            raise ValueError("exclusive candidate splits require an explicitly grouped alternative contract")
        expected = mapped({i: old_shares[i] for i in rule.initiative_ids})
        if expected != {i: new_shares[i] for i in revised.initiative_ids}:
            raise ValueError(
                "lineage must conserve each allocated population share without scaling the full reference twice"
            )
    costs = {c.cost_id: c for c in new_policy.cost_allocations}
    if set(costs) != {c.cost_id for c in old_policy.cost_allocations}:
        raise ValueError("identity-only transition must preserve cost allocation rules")
    for cost in old_policy.cost_allocations:
        expected = mapped({s.initiative_id: s.share for s in cost.shares})
        if expected != {s.initiative_id: s.share for s in costs[cost.cost_id].shares}:
            raise ValueError("lineage must conserve explicit cost shares and their unassigned residual")


def mapped_priority(payload: LineagePayload, original_order: list[str]) -> list[str]:
    """Map an original first-wave ordering through explicitly authored task ancestry."""
    ancestors: dict[str, set[str]] = {}
    for event in payload.lineage_events:
        for edge in event.task_edges:
            ancestors.setdefault(edge.successor_id, set()).update(
                ancestors.get(edge.predecessor_id, {edge.predecessor_id})
            )
    rank = {identity: index for index, identity in enumerate(original_order)}
    current = list(payload.operating_plan.priority_order)
    if any(not ancestors.get(identity, {identity}) <= rank.keys() for identity in current):
        raise ValueError("first-wave alternative requires complete task ancestry to its original priority order")
    return sorted(
        current,
        key=lambda identity: (min(rank[p] for p in ancestors.get(identity, {identity})), current.index(identity)),
    )


def lineage_families(payload: LineagePayload) -> list[dict[str, Any]]:
    current = {d.initiative_id for d in payload.underwriting.scenarios[0].drivers}
    components = [{i} for i in current]
    successors: set[str] = set()
    for event in payload.lineage_events:
        for edge in event.edges:
            group = {edge.predecessor_id, edge.successor_id}
            overlapping = [c for c in components if c & group]
            for component in overlapping:
                group |= component
                components.remove(component)
            components.append(group)
            successors.add(edge.successor_id)
    return [
        {
            "family_id": "family:" + hashlib.sha256(json.dumps(sorted(c - successors)).encode()).hexdigest(),
            "original_ids": sorted(c - successors),
            "all_identities": sorted(c),
            "current_ids": sorted(c & current),
        }
        for c in sorted(components, key=lambda c: sorted(c))
    ]


def evaluate_lineage(payload: LineagePayload, parent: CaseRevision, financial: dict[str, Any]) -> dict[str, Any]:
    prior = source_payload(parent.draft.payload)
    assert prior is not None
    families = lineage_families(payload)
    before = source_forecast(prior.operating_sources, prior.underwriting, prior.operating_plan)
    after = source_forecast(payload.source_basis.operating_sources, payload.underwriting, payload.operating_plan)
    saved = json.loads(parent.financial_result_json)
    scenarios = []
    for previous, current, stored in zip(before["scenarios"], after["scenarios"], saved["scenarios"], strict=True):
        if json.loads(json.dumps(previous["monthly"], default=str)) != stored["monthly"]:
            raise ValueError("prior source forecast must reproduce before a lineage comparison is emitted")
        groups = []
        memberships = {identity: f["family_id"] for f in families for identity in f["all_identities"]}
        prior_costs = next(s.costs for s in prior.underwriting.scenarios if s.scenario_id == previous["scenario_id"])
        current_costs = next(s.costs for s in payload.underwriting.scenarios if s.scenario_id == current["scenario_id"])
        scoped_entries: dict[str, list[tuple[str, Entry]]] = {}
        for label, report, costs in (("prior", previous, prior_costs), ("current", current, current_costs)):
            cost_families = {cost.cost_id: {memberships[i] for i in cost.initiative_ids} for cost in costs}
            scoped_entries[label] = []
            for raw_entry in report["entries"]:
                entry = Entry.model_validate(raw_entry)
                if entry.initiative_id == "shared":
                    owners = cost_families[entry.reference]
                    owner = next(iter(owners)) if len(owners) == 1 else "shared"
                else:
                    owner = memberships[entry.initiative_id]
                scoped_entries[label].append((owner, entry))
        for family in [
            *families,
            {"family_id": "shared", "all_identities": ["shared"], "original_ids": [], "current_ids": []},
        ]:
            comparison: dict[str, Any] = dict(family)
            for label in ("prior", "current"):
                entries = tuple(entry for owner, entry in scoped_entries[label] if owner == family["family_id"])
                comparison[label] = {
                    "monthly": [
                        {
                            "start": month_start(payload.underwriting.start, m),
                            "end": month_end(payload.underwriting.start, m),
                            **totals(
                                entries,
                                month_start(payload.underwriting.start, m),
                                month_end(payload.underwriting.start, m),
                            ),
                        }
                        for m in range(payload.underwriting.months)
                    ],
                    "day_100": totals(
                        entries, payload.underwriting.start, payload.underwriting.start + timedelta(days=99)
                    ),
                    "year_one": totals(entries, payload.underwriting.start, month_end(payload.underwriting.start, 11)),
                }
            groups.append(comparison)
        for label, report in (("prior", previous), ("current", current)):
            for period in ("day_100", "year_one"):
                for field in report[period]:
                    if sum((g[label][period][field] for g in groups), Decimal(0)) != report[period][field]:
                        raise ValueError("lineage families and shared costs must reconcile to the complete forecast")
            for index, month in enumerate(report["monthly"]):
                for field in month.keys() - {"start", "end"}:
                    if sum((g[label]["monthly"][index][field] for g in groups), Decimal(0)) != month[field]:
                        raise ValueError("lineage families and shared costs must reconcile for every month")
        scenarios.append({"scenario_id": current["scenario_id"], "families": groups})
    return {
        "version": "initiative-lineage/2"
        if isinstance(payload, AllocatedLineageCasePayload)
        else "initiative-lineage/1",
        "payload_sha256": fingerprint(payload),
        "parent_revision_id": parent.revision_id,
        "parent_revision_sha256": parent.content_sha256,
        "families": families,
        "cost_treatment": "A cost shared only among descendants of one family rolls up once to that family. Cross-family costs remain shared. Raw ledger owners, amounts and historical accounting are unchanged.",
        "scenarios": scenarios,
        "kpis": (
            allocated_kpi_report(payload.kpis, set(financial["selected_initiatives"]))
            if isinstance(payload, AllocatedLineageCasePayload)
            else kpi_report(payload.kpis, set(financial["selected_initiatives"]))
        ),
        "authority": "Constructed initiative and KPI lineage. Family comparisons conserve scope; shared costs remain separate. Prior accounting and attribution retain frozen initiative IDs. Reference allocation shares never manufacture historical child observations or financial attribution.",
    }
