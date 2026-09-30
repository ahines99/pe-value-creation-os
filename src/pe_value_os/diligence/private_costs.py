"""Private delivery-to-ledger matching; never an additional financial posting.

The repository must resolve these source contexts and call the calculator under
its company transaction. This module alone does not persist a review or reserve
ledger rows against other reconciliation streams.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .models import Record
from .private_baselines import PrivateBaseline
from .private_capacity import PrivateCapacityRevision
from .private_execution import DeliveryReport, EventBinding, EvidenceBinding, PrivateExecutionEvent, replay
from .private_grants import GrantEvent, require_processing_permission, validate_key
from .private_intake import SHA, Amount, Control, Ledger, parse_private, require_operator
from .private_records import (
    KEY,
    UUID,
    FinanceReview,
    PrivateIntake,
    authorize_source,
    content_hash,
    require_finance_reviewer,
    require_intake_writer,
)

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


class PrivateCostReconciliation(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    revision_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    baseline_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: CostReconciliationRequest
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    origin: Literal["synthetic_test_fixture", "company_export"]
    result: CostReconciliationResult
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private cost reconciliation hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private cost reconciliation requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private cost reconciliations cannot be exported as public exhibits")


class CostReviewAssessment(Record):
    source_identity_and_scope: str = Field(min_length=1)
    report_basis_and_timing: str = Field(min_length=1)
    cost_classification: str = Field(min_length=1)
    differences_and_completeness: str = Field(min_length=1)
    double_counting: str = Field(min_length=1)


class CostReviewRequest(Record):
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    expected_reconciliation_sha256: SHA
    expected_execution_head_sha256: SHA
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    rationale: str = Field(min_length=1)
    evidence: EvidenceBinding
    assessment: CostReviewAssessment | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.decision == "accept") != (self.assessment is not None):
            raise ValueError("only cost acceptance requires a complete finance assessment")
        return self


class CostReview(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    review_id: str = Field(pattern=UUID)
    company_id: str
    baseline_id: str = Field(pattern=UUID)
    reconciliation_revision_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: CostReviewRequest
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if content_hash(self) != self.content_sha256:
            raise ValueError("private cost review hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private cost review requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private cost reviews cannot be exported as public exhibits")


def prepare_cost_reconciliation(
    company_id: str,
    request: CostReconciliationRequest,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    sources: list[CostSourceContext],
    previous: PrivateCostReconciliation | None,
    environment_id: str,
) -> PrivateCostReconciliation:
    principal = require_intake_writer(company_id)
    now = datetime.now(UTC)
    if company_id != baseline.company_id:
        raise ValueError("cost reconciliation belongs to another company")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("cost reconciliation requires its current baseline stream head")
    if previous:
        PrivateCostReconciliation.model_validate(previous.model_dump(mode="json"))
        if (previous.company_id, previous.case_key, previous.baseline_id) != (
            company_id,
            baseline.case_key,
            baseline.baseline_id,
        ) or previous.recorded_at > now:
            raise ValueError("cost reconciliation correction cannot change baseline or chronology")
    if baseline.recorded_at > now or any(event.recorded_at > now for event in events):
        raise ValueError("cost reconciliation predates its baseline or execution")
    if any(source.record.recorded_at > now or any(r.recorded_at > now for r in source.reviews) for source in sources):
        raise ValueError("cost reconciliation predates its source or finance review")
    payload: dict[str, Any] = dict(
        revision_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=baseline.case_key,
        baseline_id=baseline.baseline_id,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        entity_id=baseline.entity_id,
        currency=baseline.currency,
        origin=baseline.origin,
        result=calculate_cost_reconciliation(request, baseline, plan, events, sources, environment_id),
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateCostReconciliation.model_construct(**payload))
    return PrivateCostReconciliation.model_validate(payload)


def cost_review_head(record: PrivateCostReconciliation, reviews: list[CostReview]) -> CostReview | None:
    PrivateCostReconciliation.model_validate(record.model_dump(mode="json"))
    previous: CostReview | None = None
    for review in reviews:
        CostReview.model_validate(review.model_dump(mode="json"))
        if (review.company_id, review.baseline_id, review.reconciliation_revision_id) != (
            record.company_id,
            record.baseline_id,
            record.revision_id,
        ) or review.request.expected_reconciliation_sha256 != record.content_sha256:
            raise ValueError("cost review belongs to another exact reconciliation")
        if review.author == record.author or review.author.startswith(("model:", "service:", "simulated:")):
            raise ValueError("cost review requires a distinct human finance reviewer")
        if review.sequence != (previous.sequence + 1 if previous else 1) or review.request.expected_previous_sha256 != (
            previous.content_sha256 if previous else None
        ):
            raise ValueError("cost review chain does not reconcile")
        if review.recorded_at < (previous.recorded_at if previous else record.recorded_at):
            raise ValueError("cost review predates its proposal or predecessor")
        if review.request.decision == "withdraw":
            if previous is None or previous.request.decision != "accept":
                raise ValueError("cost withdrawal requires preceding acceptance")
        elif review.request.expected_execution_head_sha256 != record.request.expected_execution_head_sha256:
            raise ValueError("cost review must bind the reconciliation's exact execution history")
        previous = review
    return previous


def prepare_cost_review(
    record: PrivateCostReconciliation, request: CostReviewRequest, reviews: list[CostReview]
) -> CostReview:
    principal = require_finance_reviewer(record.company_id)
    request = CostReviewRequest.model_validate(request.model_dump(mode="json"))
    previous = cost_review_head(record, reviews)
    payload: dict[str, Any] = dict(
        review_id=str(uuid.uuid4()),
        company_id=record.company_id,
        baseline_id=record.baseline_id,
        reconciliation_revision_id=record.revision_id,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        author=principal.subject,
        recorded_at=datetime.now(UTC),
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(CostReview.model_construct(**payload))
    result = CostReview.model_validate(payload)
    cost_review_head(record, [*reviews, result])
    return result


def verify_cost_reconciliation(
    record: PrivateCostReconciliation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    sources: list[CostSourceContext],
    environment_id: str,
) -> None:
    """Reproduce the proposal under fresh source permission and exact current heads."""
    PrivateCostReconciliation.model_validate(record.model_dump(mode="json"))
    if (record.company_id, record.case_key, record.baseline_id, record.entity_id, record.currency, record.origin) != (
        baseline.company_id,
        baseline.case_key,
        baseline.baseline_id,
        baseline.entity_id,
        baseline.currency,
        baseline.origin,
    ):
        raise ValueError("cost reconciliation scope differs from its frozen baseline")
    expected = calculate_cost_reconciliation(record.request, baseline, plan, events, sources, environment_id)
    if expected != record.result:
        raise ValueError("private cost reconciliation cannot be reproduced")


def require_cost_reservations(
    candidate: PrivateCostReconciliation, other_accepted: list[PrivateCostReconciliation]
) -> None:
    """Caller supplies the other accepted company ledgers under its company lock.

    Stale source acceptance must still reserve its rows until an explicit
    replacement or withdrawal; current-use failure alone cannot free capacity.
    The repository resolves the replaced baseline stream before calling this.
    """
    pools: dict[tuple[str, str, str, str], tuple[tuple[Any, ...], Decimal]] = {}
    seen_revisions = set()
    with localcontext() as context:
        context.prec = 40
        for record in [candidate, *other_accepted]:
            PrivateCostReconciliation.model_validate(record.model_dump(mode="json"))
            if record.company_id != candidate.company_id:
                raise ValueError("cost reservations require the same company")
            if record.revision_id in seen_revisions:
                raise ValueError("cost reservation set repeats a revision")
            seen_revisions.add(record.revision_id)
            for row in record.result.ledger_rows:
                assigned = Decimal(str(row["matched_cost"]))
                if not assigned:
                    continue
                available = Decimal(str(row["ledger_cost"]))
                if not available or (assigned > 0) != (available > 0):
                    raise ValueError("reserved cost must preserve the ledger row sign")
                identity = (row["source_system"], record.entity_id, row["period"], row["source_row_id"])
                scope = (record.currency, record.origin, row["component"], available)
                previous_scope, used = pools.get(identity, (scope, Decimal(0)))
                if previous_scope != scope:
                    raise ValueError("accepted cost row has changed scope or amount; resolve its prior reservation")
                used += abs(assigned)
                if used > abs(available):
                    raise ValueError("accepted cost allocations exceed the shared company ledger row")
                pools[identity] = scope, used


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
    require_operator(baseline.company_id)
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
