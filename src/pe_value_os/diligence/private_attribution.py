"""Private, evidence-bound allocation proposals; accounting agreement is not causation.

Repository callers must independently reproduce and authorize the observation and
baseline, serialize writes with source/authority changes, and reserve overlapping
accepted windows. These pure contracts do not confer current processing permission.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .models import Record
from .private_baselines import PrivateBaseline
from .private_capacity import PrivateCapacityRevision
from .private_execution import (
    AuthorizationDecision,
    DeliveryAcceptance,
    EventBinding,
    EvidenceBinding,
    ExecutionState,
    PrivateExecutionEvent,
    replay,
)
from .private_grants import validate_key
from .private_intake import SHA, Amount, Control
from .private_observations import PrivateObservation, financial_amounts
from .private_records import KEY, UUID, content_hash, require_finance_reviewer, require_intake_writer
from .realization import COMPONENTS, Component
from .underwriting import month_end, month_start


class AttributionAllocation(Record):
    period: date
    component: Component
    initiative_id: str = Field(min_length=1)
    amount: Amount
    mechanism: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)
    evidence: EvidenceBinding
    benefit_acceptance: EventBinding | None = None
    measurement_authorization: EventBinding | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.period.day != 1 or self.amount == 0:
            raise ValueError("attribution requires a whole-month nonzero signed allocation")
        if (self.amount > 0) != (self.benefit_acceptance is not None and self.measurement_authorization is not None):
            raise ValueError("positive allocations require accepted delivery and measurement authorization")
        if self.amount < 0 and (self.benefit_acceptance is not None or self.measurement_authorization is not None):
            raise ValueError("negative allocations use accounting evidence, without benefit-acceptance claims")
        return self


class AttributionRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    observation_id: str = Field(pattern=UUID)
    observation_sha256: SHA
    expected_execution_head_sha256: SHA | None
    allocations: tuple[AttributionAllocation, ...] = Field(default=(), max_length=5000)
    rationale: str = Field(min_length=1)
    method_and_limits: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self) -> Self:
        keys = [(a.period, a.component, a.initiative_id) for a in self.allocations]
        if len(keys) != len(set(keys)):
            raise ValueError("each month/component/initiative allocation must be unique")
        return self


class PrivateAttribution(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    revision_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    attribution_key: str
    sequence: int = Field(ge=1)
    request: AttributionRequest
    baseline_id: str = Field(pattern=UUID)
    baseline_sha256: SHA
    measurement_key: str
    first_month: date
    months: int = Field(ge=1, le=24, strict=True)
    origin: Literal["synthetic_test_fixture", "company_export"]
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    result: dict[str, Any]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    finance_reviewed: Literal[False] = False
    causal_impact_proven: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        for key in (self.case_key, self.attribution_key, self.measurement_key):
            validate_key(key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private attribution hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private attribution requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private attribution cannot be exported as public exhibits")


class AttributionAssessment(Record):
    accounting_reconciliation: str = Field(min_length=1)
    mechanism_and_delivery: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)
    double_counting_and_residuals: str = Field(min_length=1)
    attribution_limits: str = Field(min_length=1)


class AttributionReviewRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    expected_attribution_sha256: SHA
    expected_execution_head_sha256: SHA | None
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    rationale: str = Field(min_length=1)
    evidence: EvidenceBinding
    assessment: AttributionAssessment | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.decision == "accept") != (self.assessment is not None):
            raise ValueError("only attribution acceptance requires a complete finance assessment")
        return self


class AttributionReview(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    review_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    attribution_revision_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: AttributionReviewRequest
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    causal_impact_proven: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if content_hash(self) != self.content_sha256:
            raise ValueError("private attribution review hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("attribution review requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private attribution reviews cannot be exported as public exhibits")


def execution_prefix(events: list[PrivateExecutionEvent], head: str | None) -> list[PrivateExecutionEvent]:
    if head is None:
        return []
    for index, event in enumerate(events):
        if event.content_sha256 == head:
            return events[: index + 1]
    raise ValueError("attribution execution head is unavailable")


def require_benefit_support(allocation: AttributionAllocation, state: ExecutionState) -> None:
    if allocation.benefit_acceptance is None or allocation.measurement_authorization is None:
        raise ValueError("positive attribution lacks operating support")
    inputs = state.plan.schedule_result["scheduled_inputs"]
    if allocation.initiative_id not in inputs["selected_initiatives"]:
        raise ValueError("positive attribution requires a selected initiative")
    task_id = next(
        g.task_id for g in state.plan.request.plan.benefit_gates if g.initiative_id == allocation.initiative_id
    )
    accepted = state.bound(allocation.benefit_acceptance, "acceptance")
    payload = accepted.request.payload
    if not isinstance(payload, DeliveryAcceptance) or payload.task_id != task_id:
        raise ValueError("attribution must bind its own initiative benefit gate")
    error = state.acceptance_error(accepted)
    if error:
        raise ValueError(error)
    start = datetime.combine(allocation.period, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(month_start(allocation.period, 1), datetime.min.time(), tzinfo=UTC)
    if accepted.recorded_at >= start:
        raise ValueError("benefit acceptance must precede the full measurement month")
    authorized = state.bound(allocation.measurement_authorization, "authorization")
    terms = state.authorization_terms(authorized)
    if not (authorized.recorded_at < start and terms.valid_from <= start and end <= terms.expires_at):
        raise ValueError("recorded authorization must cover the full measurement month")
    if task_id not in terms.task_ids or state.reported_cost(authorized.event_id) > terms.approved_cost_limit:
        raise ValueError("measurement authorization lacks task scope or exceeds its reported-cost limit")
    if any(
        isinstance(event.request.payload, AuthorizationDecision)
        and event.sequence > authorized.sequence
        and event.recorded_at < end
        for event in state.events
    ):
        raise ValueError("authorization changed before the measurement month ended")


def calculate_attribution(
    request: AttributionRequest,
    observation: PrivateObservation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    *,
    now: datetime,
    current_support: bool = False,
) -> dict[str, Any]:
    request = AttributionRequest.model_validate(request.model_dump(mode="json"))
    PrivateObservation.model_validate(observation.model_dump(mode="json"))
    if (request.observation_id, request.observation_sha256) != (
        observation.observation_id,
        observation.content_sha256,
    ) or (
        observation.company_id,
        observation.case_key,
        observation.baseline_id,
        observation.baseline_sha256,
        observation.origin,
        observation.entity_id,
        observation.currency,
    ) != (
        baseline.company_id,
        baseline.case_key,
        baseline.baseline_id,
        baseline.content_sha256,
        baseline.origin,
        baseline.entity_id,
        baseline.currency,
    ):
        raise ValueError("attribution requires its exact same-scope observation and frozen baseline")
    state = replay(baseline, plan, events)
    execution_prefix(events, request.expected_execution_head_sha256)
    if not current_support and request.expected_execution_head_sha256 != (
        events[-1].content_sha256 if events else None
    ):
        raise ValueError("attribution requires the current execution head")
    if max([observation.recorded_at, baseline.recorded_at, *(e.recorded_at for e in events)]) > now:
        raise ValueError("attribution predates its observation or execution evidence")
    end = month_end(observation.request.first_month, observation.request.months - 1)
    if end >= now.date():
        raise ValueError("attribution requires completed measurement months")
    registered = {g.initiative_id for g in plan.request.plan.benefit_gates}
    expected = {
        (month_start(observation.request.first_month, n), component)
        for n in range(observation.request.months)
        for component in COMPONENTS
    }
    differences = {
        (date.fromisoformat(month["start"]), row["component"]): Decimal(row["difference"])
        for month in observation.result["monthly"]
        for row in month["components"]
    }
    if set(differences) != expected:
        raise ValueError("attribution observation lacks complete component coverage")
    allocated: dict[tuple[date, str], Decimal] = dict.fromkeys(expected, Decimal(0))
    with localcontext() as ctx:
        ctx.prec = 40
        for allocation in request.allocations:
            key = (allocation.period, allocation.component)
            if key not in expected or allocation.initiative_id not in registered:
                raise ValueError("attribution requires an observed month and registered initiative")
            difference = differences[key]
            if difference == 0 or (allocation.amount > 0) != (difference > 0):
                raise ValueError("allocation must retain the sign of its nonzero accounting difference")
            allocated[key] += allocation.amount
            if abs(allocated[key]) > abs(difference):
                raise ValueError("allocations cannot exceed their accounting difference")
            if allocation.amount > 0:
                require_benefit_support(allocation, state)
        controls: dict[str, list[Control]] = {kind: [] for kind in ("difference", "proposed_attribution", "residual")}
        monthly = []
        for n in range(observation.request.months):
            period = month_start(observation.request.first_month, n)
            rows = []
            for component in COMPONENTS:
                component_key = (period, component)
                values = dict(
                    difference=differences[component_key],
                    proposed_attribution=allocated[component_key],
                    residual=differences[component_key] - allocated[component_key],
                )
                rows.append(dict(component=component, **values))
                for kind, amount in values.items():
                    controls[kind].append(Control(period=period, component=component, amount=amount))
            monthly.append(
                dict(
                    start=period,
                    end=month_end(period),
                    components=rows,
                    financials={
                        kind: financial_amounts(tuple(values), period, month_end(period)).model_dump(mode="json")
                        for kind, values in controls.items()
                    },
                )
            )
        totals = {
            kind: financial_amounts(tuple(values), observation.request.first_month, end).model_dump(mode="json")
            for kind, values in controls.items()
        }
    result: dict[str, Any] = json.loads(
        json.dumps(
            dict(
                calculation_version="private-attribution/1",
                classification="permissioned_private",
                origin=baseline.origin,
                currency=baseline.currency,
                unit_scale=1,
                first_month=observation.request.first_month,
                end=end,
                monthly=monthly,
                totals=totals,
                finance_reviewed=False,
                causal_impact_proven=False,
                limitation="Proposed signed allocations of accounting differences, subject to separate finance review. Evidence references and human attestations are not independently authenticated. Reconciliation and accepted delivery do not prove causation. Unassigned differences remain residuals; no public export or operating permission is created.",
            ),
            default=str,
        )
    )
    return result


def prepare_attribution(
    company_id: str,
    case_key: str,
    key: str,
    request: AttributionRequest,
    observation: PrivateObservation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    previous: PrivateAttribution | None,
) -> PrivateAttribution:
    principal = require_intake_writer(company_id)
    request = AttributionRequest.model_validate(request.model_dump(mode="json"))
    validate_key(key)
    if (company_id, case_key) != (baseline.company_id, baseline.case_key):
        raise ValueError("attribution belongs to another company or case")
    now = datetime.now(UTC)
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("attribution requires its current stream head")
    if previous and (
        (
            previous.company_id,
            previous.case_key,
            previous.attribution_key,
            previous.baseline_id,
            previous.measurement_key,
            previous.first_month,
            previous.months,
        )
        != (
            company_id,
            case_key,
            key,
            baseline.baseline_id,
            observation.measurement_key,
            observation.request.first_month,
            observation.request.months,
        )
        or previous.recorded_at > now
    ):
        raise ValueError("attribution correction cannot change scope, baseline, measurement stream or window")
    payload: dict[str, Any] = dict(
        revision_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        attribution_key=key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        baseline_id=baseline.baseline_id,
        baseline_sha256=baseline.content_sha256,
        measurement_key=observation.measurement_key,
        first_month=observation.request.first_month,
        months=observation.request.months,
        origin=baseline.origin,
        entity_id=baseline.entity_id,
        currency=baseline.currency,
        result=calculate_attribution(request, observation, baseline, plan, events, now=now),
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateAttribution.model_construct(**payload))
    return PrivateAttribution.model_validate(payload)


def verify_attribution(
    record: PrivateAttribution,
    observation: PrivateObservation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
) -> None:
    PrivateAttribution.model_validate(record.model_dump(mode="json"))
    if (
        record.company_id,
        record.case_key,
        record.baseline_id,
        record.baseline_sha256,
        record.measurement_key,
        record.first_month,
        record.months,
        record.origin,
        record.entity_id,
        record.currency,
    ) != (
        baseline.company_id,
        baseline.case_key,
        baseline.baseline_id,
        baseline.content_sha256,
        observation.measurement_key,
        observation.request.first_month,
        observation.request.months,
        baseline.origin,
        baseline.entity_id,
        baseline.currency,
    ):
        raise ValueError("private attribution scope changed")
    original_events = execution_prefix(events, record.request.expected_execution_head_sha256)
    if record.result != calculate_attribution(
        record.request, observation, baseline, plan, original_events, now=record.recorded_at
    ):
        raise ValueError("private attribution does not reproduce from its original evidence")


def attribution_review_head(record: PrivateAttribution, reviews: list[AttributionReview]) -> AttributionReview | None:
    previous = None
    for review in reviews:
        AttributionReview.model_validate(review.model_dump(mode="json"))
        if (
            review.company_id,
            review.case_key,
            review.attribution_revision_id,
            review.request.expected_attribution_sha256,
            review.sequence,
            review.request.expected_previous_sha256,
        ) != (
            record.company_id,
            record.case_key,
            record.revision_id,
            record.content_sha256,
            previous.sequence + 1 if previous else 1,
            previous.content_sha256 if previous else None,
        ) or review.recorded_at < (previous.recorded_at if previous else record.recorded_at):
            raise ValueError("attribution review history is foreign, incomplete or out of order")
        if review.author == record.author:
            raise ValueError("attribution requires a different human finance reviewer")
        if review.request.decision == "withdraw" and (previous is None or previous.request.decision != "accept"):
            raise ValueError("attribution withdrawal requires preceding acceptance")
        previous = review
    return previous


def prepare_attribution_review(
    record: PrivateAttribution,
    request: AttributionReviewRequest,
    reviews: list[AttributionReview],
) -> AttributionReview:
    principal = require_finance_reviewer(record.company_id)
    request = AttributionReviewRequest.model_validate(request.model_dump(mode="json"))
    previous = attribution_review_head(record, reviews)
    if request.expected_attribution_sha256 != record.content_sha256:
        raise ValueError("attribution review requires the exact proposal hash")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("attribution review requires its current head")
    payload: dict[str, Any] = dict(
        review_id=str(uuid.uuid4()),
        company_id=record.company_id,
        case_key=record.case_key,
        attribution_revision_id=record.revision_id,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        author=principal.subject,
        recorded_at=datetime.now(UTC),
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(AttributionReview.model_construct(**payload))
    result = AttributionReview.model_validate(payload)
    attribution_review_head(record, [*reviews, result])
    return result


def require_current_execution_support(
    record: PrivateAttribution,
    observation: PrivateObservation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
) -> None:
    calculate_attribution(
        record.request,
        observation,
        baseline,
        plan,
        events,
        now=datetime.now(UTC),
        current_support=True,
    )


def verify_review_evidence(
    record: PrivateAttribution,
    reviews: list[AttributionReview],
    observation: PrivateObservation,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
) -> None:
    """Reproduce support as it existed for each original acceptance."""
    attribution_review_head(record, reviews)
    for review in reviews:
        prefix = execution_prefix(events, review.request.expected_execution_head_sha256)
        if prefix and prefix[-1].recorded_at > review.recorded_at:
            raise ValueError("attribution review predates its execution evidence")
        if review.request.decision == "accept":
            calculate_attribution(
                record.request,
                observation,
                baseline,
                plan,
                prefix,
                now=review.recorded_at,
                current_support=True,
            )


def require_disjoint_accepted_windows(record: PrivateAttribution, accepted_heads: list[PrivateAttribution]) -> None:
    """Call under the company lock with latest, currently accepted stream heads.

    Conservatively reserve even a stale-source acceptance until withdrawn or
    superseded. No other source's bytes need to be processed to enforce this.
    """
    if not record.request.allocations:
        return
    end = month_start(record.first_month, record.months)
    for other in accepted_heads:
        if (other.company_id, other.case_key, other.baseline_id) != (
            record.company_id,
            record.case_key,
            record.baseline_id,
        ):
            raise ValueError("accepted attribution reservation belongs to another scope")
        if other.attribution_key == record.attribution_key or not other.request.allocations:
            continue
        if record.first_month < month_start(other.first_month, other.months) and other.first_month < end:
            raise ValueError("another accepted attribution stream already reserves this measurement window")
