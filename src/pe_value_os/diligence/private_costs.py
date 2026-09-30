"""Private delivery-to-ledger matching; never an additional financial posting.

The repository must resolve these source contexts and call the calculator under
its company transaction. This module alone does not persist a review or reserve
ledger rows against other reconciliation streams.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from .models import Record
from .private_baselines import PrivateBaseline
from .private_capacity import PrivateCapacityRevision
from .private_execution import DeliveryReport, EventBinding, EvidenceBinding, PrivateExecutionEvent, replay
from .private_grants import GrantEvent, require_processing_permission
from .private_intake import SHA, Amount, Control, Ledger, parse_private
from .private_records import KEY, UUID, FinanceReview, PrivateIntake, authorize_source, require_intake_writer

COST_COMPONENTS = frozenset({"operating_expense", "implementation_expense", "capex_cash"})


class CostSourceBinding(Record):
    intake_id: str = Field(pattern=UUID)
    intake_sha256: SHA
    finance_review_sha256: SHA
    grant_sha256: SHA


class CostAllocation(Record):
    delivery: EventBinding
    intake_id: str = Field(pattern=UUID)
    source_row_id: str = Field(min_length=1)
    cost_amount: Amount
    scope_and_timing_assessment: str = Field(min_length=1)
    evidence: EvidenceBinding

    @field_validator("cost_amount", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)

    @model_validator(mode="after")
    def nonzero(self) -> Self:
        if not self.cost_amount:
            raise ValueError("cost allocations must be nonzero; omit unmatched entries")
        return self


class CostReconciliationRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    expected_baseline_sha256: SHA
    expected_execution_head_sha256: SHA
    sources: tuple[CostSourceBinding, ...] = Field(min_length=1, max_length=24)
    allocations: tuple[CostAllocation, ...] = Field(max_length=10000)
    cost_basis: Literal["expense_and_capex_cash_with_explicit_report_comparability"]
    reported_cost_basis_assessment: str = Field(min_length=1)
    scope_and_completeness_assessment: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({s.intake_id for s in self.sources}) != len(self.sources):
            raise ValueError("each cost source must be bound once")
        keys = [(a.delivery.event_id, a.intake_id, a.source_row_id) for a in self.allocations]
        if len(keys) != len(set(keys)):
            raise ValueError("each delivery/source-row allocation must be unique")
        return self


@dataclass(frozen=True)
class CostSourceContext:
    record: PrivateIntake
    raw: bytes
    grants: list[GrantEvent]
    reviews: list[FinanceReview]
    current: PrivateIntake


class CostReconciliationResult(Record):
    calculation_version: Literal["private-delivery-costs/1"] = "private-delivery-costs/1"
    classification: Literal["permissioned_private"] = "permissioned_private"
    reported_cost: Decimal
    matched_expense: Decimal
    matched_capex_cash: Decimal
    matched_cost: Decimal
    reported_less_matched: Decimal
    deliveries: tuple[dict[str, Any], ...]
    ledger_rows: tuple[dict[str, Any], ...]
    all_reported_costs_matched: bool
    all_project_costs_captured: Literal[False] = False
    finance_reviewed: Literal[False] = False
    cross_stream_reservations_checked: Literal[False] = False
    additional_ebitda_or_cash_posting: Literal[False] = False

    def require_public(self) -> None:
        raise ValueError("private cost reconciliations cannot be exported as public exhibits")


def calculate_cost_reconciliation(
    request: CostReconciliationRequest,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    sources: list[CostSourceContext],
    environment_id: str,
) -> CostReconciliationResult:
    """Calculate under the repository lock after resolving the current baseline.

    Source authorization is reproduced here before any ledger parsing. Baseline
    current-use checks, persistence, independent finance review and cross-stream
    reservations remain the integrating repository's responsibilities.
    """
    require_intake_writer(baseline.company_id)
    request = CostReconciliationRequest.model_validate(request.model_dump(mode="json"))
    if request.expected_baseline_sha256 != baseline.content_sha256:
        raise ValueError("cost reconciliation requires the exact frozen baseline")
    if not events or events[-1].content_sha256 != request.expected_execution_head_sha256:
        raise ValueError("cost reconciliation requires the exact execution head")
    state = replay(baseline, plan, events)
    if not state.deliveries:
        raise ValueError("cost reconciliation requires recorded delivery")
    bindings = {s.intake_id: s for s in request.sources}
    if len(sources) != len(bindings) or {s.record.intake_id for s in sources} != set(bindings):
        raise ValueError("cost reconciliation requires exactly its bound source contexts")
    with localcontext() as context:
        context.prec = 40
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        source_hashes = set()
        logical_rows = set()
        for source in sources:
            record = source.record
            policy = record.request.policy
            if (record.company_id, policy.entity_id, policy.currency, record.request.manifest.origin) != (
                baseline.company_id,
                baseline.entity_id,
                baseline.currency,
                baseline.origin,
            ):
                raise ValueError("cost source company, entity, currency or origin differs from baseline")
            authorize_source(
                record, source.raw, source.grants, source.reviews, source.current, environment_id, accepted_only=True
            )
            grant = require_processing_permission(source.grants, policy, environment_id, now=datetime.now(UTC))
            binding = bindings[record.intake_id]
            if (record.content_sha256, source.reviews[-1].content_sha256, grant.content_sha256) != (
                binding.intake_sha256,
                binding.finance_review_sha256,
                binding.grant_sha256,
            ):
                raise ValueError("cost source requires exact current intake, review and grant versions")
            if record.source_sha256 in source_hashes:
                raise ValueError("the same source bytes cannot supply multiple cost pools")
            source_hashes.add(record.source_sha256)
            mappings = {m.account_code: m for m in policy.mappings}
            for source_row in parse_private(Ledger, source.raw).rows:
                mapping = mappings[source_row.account_code]
                if mapping.component not in COST_COMPONENTS:
                    continue
                identity = (
                    record.request.manifest.source_system,
                    source_row.entity_id,
                    source_row.period,
                    source_row.source_row_id,
                )
                if identity in logical_rows:
                    raise ValueError("overlapping source exports cannot supply the same logical cost row twice")
                logical_rows.add(identity)
                rows[record.intake_id, source_row.source_row_id] = dict(
                    intake_id=record.intake_id,
                    source_sha256=record.source_sha256,
                    source_system=record.request.manifest.source_system,
                    source_row_id=source_row.source_row_id,
                    period=source_row.period.isoformat(),
                    component=mapping.component,
                    ledger_cost=-source_row.amount * mapping.multiplier,
                    matched_cost=Decimal(0),
                )
        deliveries: dict[str, dict[str, Any]] = {}
        for event in state.deliveries.values():
            payload = event.request.payload
            assert isinstance(payload, DeliveryReport)
            deliveries[event.event_id] = dict(
                delivery_id=event.event_id,
                delivery_sha256=event.content_sha256,
                task_id=payload.task_id,
                work_key=payload.work_key,
                reported_cost=payload.incurred_cost,
                matched_expense=Decimal(0),
                matched_capex_cash=Decimal(0),
            )
        for allocation in request.allocations:
            delivery = deliveries.get(allocation.delivery.event_id)
            if delivery is None or delivery["delivery_sha256"] != allocation.delivery.sha256:
                raise ValueError("cost allocation requires an exact current delivery segment")
            row = rows.get((allocation.intake_id, allocation.source_row_id))
            if row is None:
                raise ValueError("cost allocation requires a mapped expense or capex source row")
            amount, available = allocation.cost_amount, row["ledger_cost"]
            if not available or (amount > 0) != (available > 0):
                raise ValueError("cost allocations must retain the source charge or credit sign")
            row["matched_cost"] += amount
            if abs(row["matched_cost"]) > abs(available):
                raise ValueError("cost allocations exceed the source row; credits cannot hide overuse")
            category = "matched_capex_cash" if row["component"] == "capex_cash" else "matched_expense"
            delivery[category] += amount
        for row in rows.values():
            row["unassigned_ledger_cost"] = row["ledger_cost"] - row["matched_cost"]
        for delivery in deliveries.values():
            delivery["matched_cost"] = delivery["matched_expense"] + delivery["matched_capex_cash"]
            delivery["reported_less_matched"] = delivery["reported_cost"] - delivery["matched_cost"]
        reported = sum((d["reported_cost"] for d in deliveries.values()), Decimal(0))
        expense = sum((d["matched_expense"] for d in deliveries.values()), Decimal(0))
        capex_cash = sum((d["matched_capex_cash"] for d in deliveries.values()), Decimal(0))
        return CostReconciliationResult(
            reported_cost=reported,
            matched_expense=expense,
            matched_capex_cash=capex_cash,
            matched_cost=expense + capex_cash,
            reported_less_matched=reported - expense - capex_cash,
            deliveries=tuple(deliveries.values()),
            ledger_rows=tuple(rows.values()),
            all_reported_costs_matched=all(d["reported_less_matched"] == 0 for d in deliveries.values()),
        )
