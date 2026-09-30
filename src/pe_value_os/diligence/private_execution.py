"""Private human intervention decisions and delivery evidence; no automated operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .. import security
from .models import Record
from .private_baselines import PrivateBaseline, require_baseline_author, require_reviewer
from .private_capacity import PrivateCapacityRevision
from .private_grants import validate_key
from .private_intake import SHA, Amount, Control
from .private_records import KEY, UUID, content_hash, require_intake_writer


class EvidenceBinding(Record):
    reference: str = Field(min_length=1)
    sha256: SHA
    attestation: str = Field(min_length=1)


class EventBinding(Record):
    event_id: str = Field(pattern=UUID)
    sha256: SHA


class OperatorAssignment(Record):
    resource_id: str = Field(min_length=1)
    operator_subject: str = Field(min_length=1)
    capacity_commitment: EvidenceBinding

    @model_validator(mode="after")
    def human(self) -> Self:
        if self.operator_subject.startswith(("model:", "service:", "simulated:")):
            raise ValueError("private assignments require named human identities")
        return self


class AuthorizationTerms(Record):
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    task_ids: tuple[str, ...] = Field(min_length=1, max_length=250)
    assignments: tuple[OperatorAssignment, ...] = Field(min_length=1, max_length=100)
    approved_cost_limit: Amount = Field(ge=0)
    permitted_population_and_actions: str = Field(min_length=1)
    constraints_and_exclusions: str = Field(min_length=1)
    stop_conditions: str = Field(min_length=1)
    rollback_plan: str = Field(min_length=1)
    sponsor_authority: EvidenceBinding

    @field_validator("approved_cost_limit", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.expires_at <= self.valid_from:
            raise ValueError("authorization requires a nonempty bounded window")
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("authorization task IDs must be unique")
        if len({a.resource_id for a in self.assignments}) != len(self.assignments):
            raise ValueError("authorization assigns each resource once")
        return self


class AuthorizationDecision(Record):
    kind: Literal["authorization"] = "authorization"
    decision: Literal["authorize", "hold", "stop", "withdraw"]
    terms: AuthorizationTerms | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.decision == "authorize") != (self.terms is not None):
            raise ValueError("only an explicit authorization can supply operating terms")
        return self


class ReportedEffort(Record):
    resource_id: str = Field(min_length=1)
    hours: Decimal = Field(ge=0, le=100000, max_digits=12, decimal_places=6)

    @field_validator("hours", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)


class DeliveryReport(Record):
    kind: Literal["delivery"] = "delivery"
    task_id: str = Field(min_length=1)
    work_key: str = Field(pattern=KEY)
    authorization: EventBinding
    state: Literal["in_progress", "blocked", "completed"]
    started_at: AwareDatetime
    through_at: AwareDatetime
    reported_effort: tuple[ReportedEffort, ...] = Field(min_length=1, max_length=100)
    incurred_cost: Amount = Field(ge=0)
    delivered_scope_and_exceptions: str = Field(min_length=1)
    delivery_evidence: EvidenceBinding

    @field_validator("incurred_cost", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.through_at < self.started_at:
            raise ValueError("reported work interval is reversed")
        if len({e.resource_id for e in self.reported_effort}) != len(self.reported_effort):
            raise ValueError("reported effort must identify each resource once")
        return self


class DeliveryAcceptance(Record):
    kind: Literal["acceptance"] = "acceptance"
    task_id: str = Field(min_length=1)
    deliveries: tuple[EventBinding, ...] = Field(min_length=1, max_length=250)
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    prerequisite_acceptances: tuple[EventBinding, ...] = Field(default=(), max_length=250)
    quality_and_scope_assessment: str = Field(min_length=1)
    review_evidence: EvidenceBinding


Payload = Annotated[AuthorizationDecision | DeliveryReport | DeliveryAcceptance, Field(discriminator="kind")]


class PrivateExecutionRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    baseline_sha256: SHA
    payload: Payload
    rationale: str = Field(min_length=1)


class PrivateExecutionEvent(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    event_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    baseline_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: PrivateExecutionRequest
    origin: Literal["synthetic_test_fixture", "company_export"]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    automated_action_executed: Literal[False] = False
    causal_value_claim: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private execution event hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private execution history requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private execution records cannot be exported as public exhibits")


def reducing_support(request: PrivateExecutionRequest) -> bool:
    payload = request.payload
    return (isinstance(payload, AuthorizationDecision) and payload.decision != "authorize") or (
        isinstance(payload, DeliveryAcceptance) and payload.decision == "withdraw"
    )


def require_author(company_id: str, request: PrivateExecutionRequest) -> security.Principal:
    if isinstance(request.payload, AuthorizationDecision):
        return require_baseline_author(company_id)
    if isinstance(request.payload, DeliveryAcceptance):
        return require_reviewer(company_id, "operating")
    return require_intake_writer(company_id)


class ExecutionState:
    """Replay original receipts, then assess current support without rewriting them."""

    def __init__(self, baseline: PrivateBaseline, plan: PrivateCapacityRevision):
        PrivateBaseline.model_validate(baseline.model_dump(mode="json"))
        PrivateCapacityRevision.model_validate(plan.model_dump(mode="json"))
        if (
            baseline.company_id,
            baseline.case_key,
            baseline.request.capacity_revision_id,
            baseline.request.expected_capacity_sha256,
            baseline.origin,
        ) != (plan.company_id, plan.case_key, plan.revision_id, plan.content_sha256, plan.origin):
            raise ValueError("private execution requires its exact frozen plan")
        self.baseline, self.plan = baseline, plan
        self.tasks = {t.task_id: t for t in plan.request.plan.tasks}
        self.selected = {r["task_id"] for r in plan.schedule_result["tasks"] if r["status"] == "scheduled"}
        self.events: list[PrivateExecutionEvent] = []
        self.by_id: dict[str, PrivateExecutionEvent] = {}
        self.deliveries: dict[str, PrivateExecutionEvent] = {}
        self.acceptances: dict[str, PrivateExecutionEvent] = {}
        self.authorization: PrivateExecutionEvent | None = None

    def bound(self, binding: EventBinding, kind: str) -> PrivateExecutionEvent:
        event = self.by_id.get(binding.event_id)
        if event is None or event.content_sha256 != binding.sha256 or event.request.payload.kind != kind:
            raise ValueError("private execution requires an exact same-baseline receipt and kind")
        return event

    def authorization_terms(self, event: PrivateExecutionEvent) -> AuthorizationTerms:
        payload = event.request.payload
        if not isinstance(payload, AuthorizationDecision) or payload.decision != "authorize" or payload.terms is None:
            raise ValueError("delivery requires a positive recorded authorization")
        return payload.terms

    def reported_cost(self, authorization_id: str | None = None) -> Decimal:
        return sum(
            (
                e.request.payload.incurred_cost
                for e in self.deliveries.values()
                if isinstance(e.request.payload, DeliveryReport)
                and (authorization_id is None or e.request.payload.authorization.event_id == authorization_id)
            ),
            Decimal(0),
        )

    def task_deliveries(self, task_id: str) -> list[PrivateExecutionEvent]:
        return [
            e
            for e in self.deliveries.values()
            if isinstance(e.request.payload, DeliveryReport) and e.request.payload.task_id == task_id
        ]

    def delivery_errors(self, event: PrivateExecutionEvent) -> list[str]:
        payload = event.request.payload
        if not isinstance(payload, DeliveryReport):
            raise ValueError("delivery report required")
        grant = self.bound(payload.authorization, "authorization")
        terms = self.authorization_terms(grant)
        errors = []
        if not (grant.recorded_at <= terms.valid_from <= payload.started_at <= payload.through_at < terms.expires_at):
            errors.append("authorization_did_not_cover_work_interval")
        if any(
            isinstance(e.request.payload, AuthorizationDecision)
            and e.sequence > grant.sequence
            and e.recorded_at <= payload.through_at
            for e in self.events
        ):
            errors.append("authorization_changed_before_work_ended")
        task = self.tasks[payload.task_id]
        if payload.started_at.date() < task.earliest_start:
            errors.append("work_precedes_plan_earliest_start")
        hours = Decimal(str((payload.through_at - payload.started_at).total_seconds())) / Decimal(3600)
        if any(e.hours > hours for e in payload.reported_effort):
            errors.append("reported_person_hours_exceed_elapsed_interval")
        if self.reported_cost(grant.event_id) > terms.approved_cost_limit:
            errors.append("authorization_reported_cost_limit_exceeded")
        return errors

    def acceptance_error(self, event: PrivateExecutionEvent, visiting: frozenset[str] = frozenset()) -> str | None:
        try:
            payload = event.request.payload
            if not isinstance(payload, DeliveryAcceptance) or payload.decision != "accept":
                raise ValueError("task has no accepted delivery")
            if event.event_id in visiting or self.acceptances.get(payload.task_id) != event:
                raise ValueError("task acceptance is superseded or cyclic")
            deliveries = [self.bound(b, "delivery") for b in payload.deliveries]
            if len({d.event_id for d in deliveries}) != len(deliveries) or {d.event_id for d in deliveries} != {
                d.event_id for d in self.task_deliveries(payload.task_id)
            }:
                raise ValueError(
                    "acceptance must bind every current delivery segment once; a delivery may have been corrected"
                )
            for delivery in deliveries:
                report = delivery.request.payload
                if (
                    not isinstance(report, DeliveryReport)
                    or report.task_id != payload.task_id
                    or report.state != "completed"
                ):
                    raise ValueError("acceptance requires completed work segments for this task")
                errors = self.delivery_errors(delivery)
                if errors:
                    raise ValueError("; ".join(errors))
            work_start = min(
                d.request.payload.started_at for d in deliveries if isinstance(d.request.payload, DeliveryReport)
            )
            prerequisites = [self.bound(b, "acceptance") for b in payload.prerequisite_acceptances]
            task_ids = [
                p.request.payload.task_id for p in prerequisites if isinstance(p.request.payload, DeliveryAcceptance)
            ]
            if len(set(task_ids)) != len(task_ids) or set(task_ids) != set(self.tasks[payload.task_id].prerequisites):
                raise ValueError("acceptance requires every exact prerequisite once")
            for prerequisite in prerequisites:
                error = self.acceptance_error(prerequisite, visiting | {event.event_id})
                if error or prerequisite.recorded_at >= work_start:
                    raise ValueError(error or "prerequisite acceptance must precede dependent work")
        except ValueError as exc:
            return str(exc)
        return None

    def append(self, event: PrivateExecutionEvent) -> None:
        PrivateExecutionEvent.model_validate(event.model_dump(mode="json"))
        baseline = self.baseline
        previous = self.events[-1] if self.events else None
        if (
            event.company_id,
            event.case_key,
            event.baseline_id,
            event.request.baseline_sha256,
            event.origin,
            event.sequence,
            event.request.expected_previous_sha256,
        ) != (
            baseline.company_id,
            baseline.case_key,
            baseline.baseline_id,
            baseline.content_sha256,
            baseline.origin,
            previous.sequence + 1 if previous else 1,
            previous.content_sha256 if previous else None,
        ) or event.recorded_at < (previous.recorded_at if previous else baseline.recorded_at):
            raise ValueError("private execution history has changed scope, predecessor or chronology")
        if event.event_id in self.by_id:
            raise ValueError("duplicate private execution event")
        payload = event.request.payload
        if isinstance(payload, AuthorizationDecision):
            if payload.terms is None:
                if self.authorization is None:
                    raise ValueError("a hold, stop or withdrawal requires preceding authorization history")
            else:
                terms = payload.terms
                start = datetime.combine(self.plan.request.plan.start, datetime.min.time(), tzinfo=UTC)
                if not (
                    event.recorded_at <= terms.valid_from
                    and start <= terms.valid_from < terms.expires_at <= start + timedelta(days=100)
                ):
                    raise ValueError("authorization cannot be backdated or extend beyond the frozen 100-day plan")
                if not set(terms.task_ids) <= self.selected:
                    raise ValueError("authorization can cover only scheduled selected tasks")
                if any(not set(self.tasks[k].prerequisites) <= set(terms.task_ids) for k in terms.task_ids):
                    raise ValueError("authorization scope must include its prerequisite tasks")
                required = {d.resource_id for k in terms.task_ids for d in self.tasks[k].demands}
                if {a.resource_id for a in terms.assignments} != required:
                    raise ValueError("authorization requires a named capacity commitment for each demanded resource")
            self.authorization = event
        elif isinstance(payload, DeliveryReport):
            grant = self.bound(payload.authorization, "authorization")
            terms = self.authorization_terms(grant)
            if payload.task_id not in terms.task_ids or payload.through_at > event.recorded_at:
                raise ValueError("delivery must report a scoped task without future work")
            task = self.tasks[payload.task_id]
            assignment = next(a for a in terms.assignments if a.resource_id == task.accountable_resource)
            if event.author != assignment.operator_subject:
                raise ValueError("only the assigned accountable operator can report delivery")
            if {e.resource_id for e in payload.reported_effort} != {d.resource_id for d in task.demands}:
                raise ValueError("delivery requires explicit effort, including known zero, for every demanded resource")
            prior_delivery = self.deliveries.get(payload.work_key)
            if prior_delivery and (
                not isinstance(prior_delivery.request.payload, DeliveryReport)
                or prior_delivery.request.payload.task_id != payload.task_id
                or prior_delivery.author != event.author
            ):
                raise ValueError("delivery correction must retain its work key, task and reporting author")
            self.deliveries[payload.work_key] = event
        else:
            deliveries = [self.bound(b, "delivery") for b in payload.deliveries]
            if any(
                not isinstance(d.request.payload, DeliveryReport) or d.request.payload.task_id != payload.task_id
                for d in deliveries
            ):
                raise ValueError("acceptance must bind the same task deliveries")
            if any(event.author == d.author for d in deliveries):
                raise ValueError("delivery acceptance requires a different human reviewer")
            if payload.decision == "withdraw":
                prior = self.acceptances.get(payload.task_id)
                if (
                    prior is None
                    or not isinstance(prior.request.payload, DeliveryAcceptance)
                    or prior.request.payload.decision != "accept"
                    or prior.request.payload.deliveries != payload.deliveries
                ):
                    raise ValueError("withdrawal requires the preceding accepted delivery binding")
            self.acceptances[payload.task_id] = event
            if payload.decision == "accept":
                error = self.acceptance_error(event)
                if error:
                    raise ValueError(error)
        self.events.append(event)
        self.by_id[event.event_id] = event


def replay(
    baseline: PrivateBaseline, plan: PrivateCapacityRevision, events: list[PrivateExecutionEvent]
) -> ExecutionState:
    state = ExecutionState(baseline, plan)
    with localcontext() as ctx:
        ctx.prec = 40
        for event in events:
            state.append(event)
    return state


def prepare_event(
    company_id: str,
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    request: PrivateExecutionRequest,
    events: list[PrivateExecutionEvent],
) -> PrivateExecutionEvent:
    request = PrivateExecutionRequest.model_validate(request.model_dump(mode="json"))
    principal = require_author(company_id, request)
    if company_id != baseline.company_id:
        raise ValueError("execution baseline belongs to another company")
    state = replay(baseline, plan, events)
    payload: dict[str, Any] = dict(
        event_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=baseline.case_key,
        baseline_id=baseline.baseline_id,
        sequence=len(events) + 1,
        request=request,
        origin=baseline.origin,
        author=principal.subject,
        recorded_at=datetime.now(UTC),
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateExecutionEvent.model_construct(**payload))
    result = PrivateExecutionEvent.model_validate(payload)
    with localcontext() as ctx:
        ctx.prec = 40
        state.append(result)
    return result


def execution_view(
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    events: list[PrivateExecutionEvent],
    *,
    baseline_supported: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if baseline.recorded_at > now or any(event.recorded_at > now for event in events):
        raise ValueError("execution status predates its recorded history")
    state = replay(baseline, plan, events)
    tasks = []
    with localcontext() as ctx:
        ctx.prec = 40
        reported_cost = state.reported_cost()
        for task in plan.request.plan.tasks:
            deliveries = state.task_deliveries(task.task_id)
            accepted = state.acceptances.get(task.task_id)
            error = state.acceptance_error(accepted) if accepted else "no acceptance recorded"
            tasks.append(
                dict(
                    task_id=task.task_id,
                    delivery_segments=[
                        dict(
                            delivery_id=d.event_id,
                            work_key=d.request.payload.work_key,
                            reported_state=d.request.payload.state,
                            reported_cost=str(d.request.payload.incurred_cost),
                            exceptions=state.delivery_errors(d),
                        )
                        for d in deliveries
                        if isinstance(d.request.payload, DeliveryReport)
                    ],
                    acceptance_id=accepted.event_id if accepted else None,
                    acceptance_supported=baseline_supported and error is None,
                    acceptance_limitation=error
                    if error
                    else (None if baseline_supported else "baseline support withdrawn"),
                )
            )
        authorization = state.authorization
        terms = (
            authorization.request.payload.terms
            if authorization and isinstance(authorization.request.payload, AuthorizationDecision)
            else None
        )
        authorization_cost = state.reported_cost(authorization.event_id) if authorization else Decimal(0)
        active = bool(
            terms
            and baseline_supported
            and terms.valid_from <= now < terms.expires_at
            and authorization_cost <= terms.approved_cost_limit
        )
    return {
        "classification": "permissioned_private",
        "origin": baseline.origin,
        "baseline_id": baseline.baseline_id,
        "baseline_sha256": baseline.content_sha256,
        "baseline_currently_supported": baseline_supported,
        "authorization_event_id": authorization.event_id if authorization else None,
        "recorded_authorization_currently_supported": active,
        "reported_cost": str(reported_cost),
        "current_authorization_reported_cost": str(authorization_cost),
        "currency": baseline.currency,
        "reported_cost_limit_exceeded": bool(terms and authorization_cost > terms.approved_cost_limit),
        "tasks": tasks,
        "automated_action_executed": False,
        "causal_value_claim": False,
        "limitation": "Recorded human decisions and reported work only. Evidence references and sponsor authority are assertions requiring company review. Reported costs are not reconciled ledger actuals. No source-system action or causal value claim is created.",
    }
