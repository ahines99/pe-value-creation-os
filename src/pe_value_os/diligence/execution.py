"""Constructed delivery receipts; acceptance, authority and financial claims stay distinct."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from .. import security
from .cases import CaseReview, CaseRevision, InvestmentCase, digest, writer
from .close_baseline import UUID_PATTERN, CloseBaseline, close_baseline_view
from .models import Record
from .realization import Attribution, Observation, require_baseline, signed_record
from .record_chain import content_hash
from .scheduling import OperatingPlan


class ExecutionEvidence(Record):
    evidence_id: str = Field(min_length=1)
    classification: Literal["constructed_execution_evidence"]
    content: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if digest(self.content) != self.sha256:
            raise ValueError("execution evidence hash mismatch")
        return self


class ReceiptBinding(Record):
    event_id: str = Field(pattern=UUID_PATTERN)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Assignment(Record):
    kind: Literal["assignment"]
    resource_id: str = Field(min_length=1)
    status: Literal["assigned", "withdrawn"]
    operator_subject: str | None = None
    sponsor_subject: str | None = None

    @model_validator(mode="after")
    def identities(self) -> Self:
        if self.status == "assigned" and (not self.operator_subject or not self.sponsor_subject):
            raise ValueError("assignment requires one named operator and sponsor")
        if self.status == "withdrawn" and (self.operator_subject is not None or self.sponsor_subject is not None):
            raise ValueError("withdrawn assignment cannot declare assigned identities")
        return self


class Steering(Record):
    kind: Literal["steering"]
    initiative_id: str = Field(min_length=1)
    decision: Literal["proceed", "hold", "stop"]


class Delivery(Record):
    kind: Literal["delivery"]
    task_id: str = Field(min_length=1)
    assignment: ReceiptBinding
    state: Literal["in_progress", "blocked", "completed"]
    started_on: date
    completed_on: date | None = None

    @model_validator(mode="after")
    def dates(self) -> Self:
        if (self.state == "completed") != (self.completed_on is not None):
            raise ValueError("only completed work has a completion date")
        if self.completed_on is not None and self.completed_on < self.started_on:
            raise ValueError("completion cannot precede the reported start")
        return self


class Acceptance(Record):
    kind: Literal["acceptance"]
    task_id: str = Field(min_length=1)
    delivery: ReceiptBinding
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    prerequisite_acceptances: tuple[ReceiptBinding, ...] = ()


class ClaimLink(Record):
    kind: Literal["claim_link"]
    status: Literal["linked", "withdrawn"] = "linked"
    attribution_id: str = Field(pattern=UUID_PATTERN)
    attribution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_id: str = Field(min_length=1)
    initiative_id: str = Field(min_length=1)
    acceptance: ReceiptBinding


ExecutionPayload = Annotated[Assignment | Steering | Delivery | Acceptance | ClaimLink, Field(discriminator="kind")]


class ExecutionRequest(Record):
    schema_version: Literal[1] = 1
    ingestion_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    baseline_id: str = Field(pattern=UUID_PATTERN)
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["human", "simulation"]
    effective_on: date
    payload: ExecutionPayload
    evidence: tuple[ExecutionEvidence, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    expected_previous_id: str | None = Field(default=None, pattern=UUID_PATTERN)

    @model_validator(mode="after")
    def evidence_ids(self) -> Self:
        if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate execution evidence identity")
        return self


def stream_key(payload: ExecutionPayload) -> str:
    if isinstance(payload, Assignment):
        identity = [payload.kind, payload.resource_id]
    elif isinstance(payload, Steering):
        identity = [payload.kind, payload.initiative_id]
    elif isinstance(payload, ClaimLink):
        identity = [payload.kind, payload.attribution_id, payload.row_id, payload.initiative_id]
    else:
        identity = [payload.kind, payload.task_id]
    return digest(json.dumps(identity))


class ExecutionEvent(Record):
    schema_version: Literal[1] = 1
    event_id: str = Field(pattern=UUID_PATTERN)
    company_id: str
    case_id: str
    stream_key: str
    sequence: int = Field(ge=1)
    request: ExecutionRequest
    actor: str
    actor_type: Literal["human", "service", "model"]
    recorded_at: datetime
    content_sha256: str

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if content_hash(self) != self.content_sha256 or self.stream_key != stream_key(self.request.payload):
            raise ValueError("execution receipt content hash or stream mismatch")
        if self.request.mode == "human" and self.actor_type != "human":
            raise ValueError("human execution receipt requires human authorship")
        return self


class ExecutionState:
    """Latest evidence corrections plus dated assignment/steering history.

    Effective dates are exercise dates, not historical knowledge cutoffs. No
    state here authorizes a live company intervention or certifies causal value.
    """

    def __init__(self, plan: OperatingPlan, events: list[ExecutionEvent]):
        self.plan = plan
        self.events = events
        self.by_id = {e.event_id: e for e in events}
        self.heads: dict[str, ExecutionEvent] = {}
        for event in sorted(events, key=lambda e: e.sequence):
            self.heads[event.stream_key] = event
        self.tasks = {t.task_id: t for t in plan.tasks}
        self.gates = {g.initiative_id: g.task_id for g in plan.benefit_gates}

    def bound(self, binding: ReceiptBinding, kind: str, *, current: bool = False) -> ExecutionEvent:
        event = self.by_id.get(binding.event_id)
        if event is None or event.content_sha256 != binding.sha256 or event.request.payload.kind != kind:
            raise ValueError("execution link requires exact same-baseline receipt and kind")
        if current and self.heads[event.stream_key].event_id != event.event_id:
            raise ValueError("supporting execution receipt has been superseded")
        return event

    def assignment_on(self, resource_id: str, day: date) -> ExecutionEvent | None:
        records = [
            e
            for e in self.events
            if isinstance(e.request.payload, Assignment)
            and e.request.payload.resource_id == resource_id
            and e.request.effective_on <= day
        ]
        return max(records, key=lambda e: e.sequence) if records else None

    def decision_on(self, initiative_id: str, day: date) -> str:
        records = [
            e
            for e in self.events
            if isinstance(e.request.payload, Steering)
            and e.request.payload.initiative_id == initiative_id
            and e.request.effective_on <= day
        ]
        record = max(records, key=lambda e: e.sequence) if records else None
        return (
            record.request.payload.decision
            if record and isinstance(record.request.payload, Steering)
            else "not_recorded"
        )

    def delivery_assignment(self, delivery: Delivery, reported_on: date) -> ExecutionEvent:
        assignment = self.bound(delivery.assignment, "assignment")
        payload = assignment.request.payload
        task = self.tasks[delivery.task_id]
        if (
            not isinstance(payload, Assignment)
            or payload.resource_id != task.accountable_resource
            or payload.status != "assigned"
        ):
            raise ValueError("delivery must bind its task's assigned accountable operator")
        end = delivery.completed_on or reported_on
        if (
            self.assignment_on(payload.resource_id, delivery.started_on) != assignment
            or self.assignment_on(payload.resource_id, end) != assignment
        ):
            raise ValueError("assignment must cover the reported work interval")
        return assignment

    def acceptance_error(self, event: ExecutionEvent, visiting: frozenset[str] = frozenset()) -> str | None:
        try:
            self._require_acceptance(event, visiting)
        except ValueError as exc:
            return str(exc)
        return None

    def _require_acceptance(self, event: ExecutionEvent, visiting: frozenset[str]) -> None:
        payload = event.request.payload
        if not isinstance(payload, Acceptance) or payload.decision != "accept":
            raise ValueError("task has no accepted receipt")
        if event.event_id in visiting:
            raise ValueError("cyclic acceptance evidence")
        if self.heads[event.stream_key].event_id != event.event_id:
            raise ValueError("acceptance has been superseded or withdrawn")
        delivery_event = self.bound(payload.delivery, "delivery", current=True)
        delivery = delivery_event.request.payload
        if not isinstance(delivery, Delivery) or delivery.task_id != payload.task_id or delivery.state != "completed":
            raise ValueError("acceptance requires its exact completed task submission")
        if delivery.completed_on is None or delivery.completed_on > event.request.effective_on:
            raise ValueError("acceptance cannot precede completed work")
        self.delivery_assignment(delivery, delivery_event.request.effective_on)
        prerequisites = self.tasks[payload.task_id].prerequisites
        receipts = [self.bound(b, "acceptance", current=True) for b in payload.prerequisite_acceptances]
        task_ids = [r.request.payload.task_id for r in receipts if isinstance(r.request.payload, Acceptance)]
        if len(task_ids) != len(set(task_ids)) or set(task_ids) != set(prerequisites):
            raise ValueError("acceptance must bind every exact prerequisite acceptance once")
        for receipt in receipts:
            self._require_acceptance(receipt, visiting | {event.event_id})
            if receipt.request.effective_on >= delivery.started_on:
                raise ValueError("prerequisite acceptance must precede dependent work start")

    def link_error(
        self, link: ClaimLink, observations: list[Observation], attributions: list[Attribution], effective_on: date
    ) -> str | None:
        try:
            if link.status == "withdrawn":
                raise ValueError("delivery support link explicitly withdrawn")
            attribution = next((a for a in attributions if a.attribution_id == link.attribution_id), None)
            if attribution is None or attribution.content_sha256 != link.attribution_sha256:
                raise ValueError("claim link requires the exact attribution batch")
            if any(a.request.expected_previous_id == attribution.attribution_id for a in attributions):
                raise ValueError("attribution batch has been corrected or withdrawn")
            observation = next(
                (o for o in observations if o.observation_id == attribution.request.observation_id), None
            )
            if observation is None or any(
                o.request.expected_previous_id == observation.observation_id for o in observations
            ):
                raise ValueError("observation has been corrected or is missing")
            allocation = next(
                (
                    a
                    for a in attribution.request.allocations
                    if (a.row_id, a.initiative_id) == (link.row_id, link.initiative_id)
                ),
                None,
            )
            if allocation is None or allocation.amount <= 0:
                raise ValueError(
                    "delivery support applies to a registered positive benefit claim; signed costs remain separate"
                )
            accepted = self.bound(link.acceptance, "acceptance", current=True)
            if not isinstance(
                accepted.request.payload, Acceptance
            ) or accepted.request.payload.task_id != self.gates.get(link.initiative_id):
                raise ValueError("claim must bind its own initiative benefit-gate acceptance")
            self._require_acceptance(accepted, frozenset())
            start, end = observation.request.observed.start, observation.request.observed.end
            if accepted.request.effective_on >= start:
                raise ValueError("whole-month support requires gate acceptance before the recorded month; no proration")
            if effective_on < max(end, accepted.request.effective_on):
                raise ValueError("claim link cannot precede its observation period or acceptance")
            if self.decision_on(link.initiative_id, start) != "proceed" or any(
                isinstance(e.request.payload, Steering)
                and e.request.payload.initiative_id == link.initiative_id
                and start <= e.request.effective_on <= end
                and e.request.payload.decision != "proceed"
                for e in self.events
            ):
                raise ValueError("the whole observation month requires a proceed decision without hold or stop")
        except ValueError as exc:
            return str(exc)
        return None


def prepare_execution(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revision: CaseRevision,
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
    events: list[ExecutionEvent],
    observations: list[Observation],
    attributions: list[Attribution],
    request: ExecutionRequest,
    previous: ExecutionEvent | None,
) -> ExecutionEvent:
    from ..approvals import can_approve

    principal = writer(case.company_id)
    require_baseline(case, baseline, revision, reviews, baselines)
    if (request.baseline_id, request.baseline_sha256, request.mode) != (
        baseline.baseline_id,
        baseline.content_sha256,
        baseline.request.mode,
    ):
        raise ValueError("execution receipt requires the exact baseline and review mode")
    plan = revision.draft.payload.operating_plan
    if plan is None:
        raise ValueError("execution requires an explicit operating plan")
    if request.effective_on < plan.start:
        raise ValueError("execution effective date cannot precede the exercise start")
    scoped = [e for e in events if e.request.baseline_id == baseline.baseline_id]
    if any(
        (e.company_id, e.case_id, e.request.mode, e.request.baseline_sha256)
        != (case.company_id, case.case_id, request.mode, baseline.content_sha256)
        for e in scoped
    ):
        raise ValueError("execution records cannot cross company, case, baseline or mode")
    state = ExecutionState(plan, scoped)
    if request.expected_previous_id != (previous.event_id if previous else None):
        raise ValueError("execution correction requires its exact predecessor")
    if previous is not None and (
        previous.stream_key != stream_key(request.payload)
        or previous.request.baseline_id != baseline.baseline_id
        or request.effective_on < previous.request.effective_on
    ):
        raise ValueError("execution stream must retain its identity and monotonic exercise date")
    payload = request.payload
    if request.mode == "human" and principal.principal_type != "human":
        raise security.deny("Human execution requires a human identity", "case_review_authority")
    if (
        request.mode == "human"
        and not isinstance(payload, Delivery)
        and not can_approve(principal, case.company_id, "approver")
    ):
        raise security.deny("Assignment, steering and review require a human approver", "case_review_authority")
    if isinstance(payload, Assignment):
        if payload.resource_id not in {r.resource_id for r in plan.resources}:
            raise ValueError("assignment references an unknown plan resource")
        if payload.status == "assigned":
            identities = (payload.operator_subject or "", payload.sponsor_subject or "")
            if request.mode == "simulation" and not all(s.startswith("simulated:") for s in identities):
                raise ValueError("simulation must explicitly label its declared identities")
            if request.mode == "human" and any(s.startswith(("simulated:", "model:", "service:")) for s in identities):
                raise ValueError("human assignments cannot nominate simulated or service identities")
    elif isinstance(payload, Steering):
        if payload.initiative_id not in state.gates:
            raise ValueError("steering references an unknown initiative")
        task = state.tasks[state.gates[payload.initiative_id]]
        assigned = state.assignment_on(task.accountable_resource, request.effective_on)
        if payload.decision == "proceed" and (
            assigned is None
            or not isinstance(assigned.request.payload, Assignment)
            or assigned.request.payload.status != "assigned"
        ):
            raise ValueError("proceed requires a recorded operator and sponsor assignment")
    elif isinstance(payload, Delivery):
        if payload.task_id not in state.tasks:
            raise ValueError("delivery references an unknown work package")
        if (
            payload.started_on < plan.start
            or payload.started_on > request.effective_on
            or (payload.completed_on and payload.completed_on > request.effective_on)
        ):
            raise ValueError("reported work dates must fall between plan start and reporting date")
        assigned = state.delivery_assignment(payload, request.effective_on)
        if (
            request.mode == "human"
            and isinstance(assigned.request.payload, Assignment)
            and principal.subject != assigned.request.payload.operator_subject
        ):
            raise security.deny("Only the assigned operator may report human delivery", "execution_operator")
    elif isinstance(payload, Acceptance):
        if payload.task_id not in state.tasks:
            raise ValueError("acceptance references an unknown task")
        delivery = state.bound(payload.delivery, "delivery", current=payload.decision != "withdraw")
        if not isinstance(delivery.request.payload, Delivery) or delivery.request.payload.task_id != payload.task_id:
            raise ValueError("acceptance must reference the same task submission")
        if request.effective_on < delivery.request.effective_on:
            raise ValueError("review cannot precede submission")
        if request.mode == "human" and delivery.actor == principal.subject:
            raise security.deny(
                "Human acceptance requires a reviewer other than the submitting operator", "execution_separation"
            )
        if payload.decision == "withdraw" and previous is None:
            raise ValueError("withdrawal requires a preceding review receipt")
    else:
        obs = [
            o
            for o in observations
            if o.request.baseline_id == baseline.baseline_id
            and o.company_id == case.company_id
            and o.case_id == case.case_id
        ]
        attrs = [
            a
            for a in attributions
            if a.request.observation_id in {o.observation_id for o in obs}
            and a.request.mode == request.mode
            and a.company_id == case.company_id
            and a.case_id == case.case_id
        ]
        if payload.status == "withdrawn":
            if previous is None or not isinstance(previous.request.payload, ClaimLink):
                raise ValueError("link withdrawal requires its preceding receipt")
            if payload.model_dump(exclude={"status"}) != previous.request.payload.model_dump(exclude={"status"}):
                raise ValueError("link withdrawal must retain its exact claim and acceptance binding")
        else:
            error = state.link_error(payload, obs, attrs, request.effective_on)
            if error:
                raise ValueError(error)
    record = signed_record(
        ExecutionEvent,
        {
            "event_id": str(uuid.uuid4()),
            "company_id": case.company_id,
            "case_id": case.case_id,
            "stream_key": stream_key(payload),
            "sequence": previous.sequence + 1 if previous else 1,
            "request": request.model_dump(mode="json"),
            "actor": principal.subject,
            "actor_type": principal.principal_type,
        },
    )
    if isinstance(payload, Acceptance) and payload.decision == "accept":
        error = ExecutionState(plan, [*scoped, record]).acceptance_error(record)
        if error:
            raise ValueError(error)
    return record


def execution_report(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revision: CaseRevision,
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
    events: list[ExecutionEvent],
    observations: list[Observation],
    attributions: list[Attribution],
    as_of: date,
) -> dict[str, Any]:
    if any(
        (r.company_id, r.case_id) != (case.company_id, case.case_id)
        for group in (events, observations, attributions)
        for r in group
    ):
        raise ValueError("execution report cannot mix companies or cases")
    if (baseline.company_id, baseline.case_id) != (case.company_id, case.case_id):
        raise ValueError("execution report requires its same-case baseline")
    plan = revision.draft.payload.operating_plan
    if plan is None:
        raise ValueError("execution report requires an operating plan")
    if as_of < plan.start:
        raise ValueError("exercise review date cannot precede the plan")
    view = close_baseline_view(baseline, revision, reviews, baselines)
    scoped = [e for e in events if e.request.baseline_id == baseline.baseline_id]
    if any(
        e.request.baseline_sha256 != baseline.content_sha256 or e.request.mode != baseline.request.mode for e in scoped
    ):
        raise ValueError("execution receipt baseline or authority mismatch")
    state = ExecutionState(plan, scoped)
    tasks = []
    scheduled = {t["task_id"]: t for t in json.loads(revision.schedule_result_json or "{}").get("tasks", [])}
    for task in plan.tasks:
        delivery = next(
            (
                e
                for e in state.heads.values()
                if isinstance(e.request.payload, Delivery) and e.request.payload.task_id == task.task_id
            ),
            None,
        )
        acceptance = next(
            (
                e
                for e in state.heads.values()
                if isinstance(e.request.payload, Acceptance) and e.request.payload.task_id == task.task_id
            ),
            None,
        )
        assigned = state.assignment_on(task.accountable_resource, as_of)
        reason = state.acceptance_error(acceptance) if acceptance else "acceptance not recorded"
        if not view["usable_for_comparison"]:
            reason = "supporting baseline review invalidated"
        if acceptance and acceptance.request.effective_on > as_of:
            reason = "acceptance falls after the exercise review date"
        tasks.append(
            {
                "task_id": task.task_id,
                "title": task.title,
                "initiative_id": task.initiative_id,
                "accountable_resource": task.accountable_resource,
                "assignment": assigned.model_dump(mode="json") if assigned else None,
                "delivery": delivery.model_dump(mode="json") if delivery else None,
                "acceptance": acceptance.model_dump(mode="json") if acceptance else None,
                "acceptance_valid": reason is None,
                "acceptance_limitation": reason,
                "planned_start": scheduled.get(task.task_id, {}).get("scheduled_start"),
                "planned_finish": scheduled.get(task.task_id, {}).get("scheduled_finish"),
                "acceptance_criteria": task.acceptance_evidence,
            }
        )
    links: list[dict[str, Any]] = []
    scoped_obs = [o for o in observations if o.request.baseline_id == baseline.baseline_id]
    scoped_attrs = [a for a in attributions if a.request.observation_id in {o.observation_id for o in scoped_obs}]
    for event in state.heads.values():
        if isinstance(event.request.payload, ClaimLink):
            reason = state.link_error(event.request.payload, scoped_obs, scoped_attrs, event.request.effective_on)
            if not view["usable_for_comparison"]:
                reason = "supporting baseline review invalidated"
            if event.request.effective_on > as_of:
                reason = "link falls after the exercise review date"
            links.append(
                {
                    "event_id": event.event_id,
                    "claim": event.request.payload.model_dump(mode="json"),
                    "delivery_support_valid": reason is None,
                    "limitation": reason,
                    "causality_validated": False,
                }
            )
    replaced_observations = {o.request.expected_previous_id for o in scoped_obs}
    active_observations = {o.observation_id: o for o in scoped_obs if o.observation_id not in replaced_observations}
    replaced_attributions = {a.request.expected_previous_id for a in scoped_attrs}
    coverage = []
    for attribution in scoped_attrs:
        if (
            attribution.attribution_id in replaced_attributions
            or attribution.request.observation_id not in active_observations
        ):
            continue
        observation = active_observations[attribution.request.observation_id]
        if observation.request.observed.end > as_of:
            continue
        for allocation in attribution.request.allocations:
            linked = next(
                (
                    link
                    for link in links
                    if (link["claim"]["attribution_id"], link["claim"]["row_id"], link["claim"]["initiative_id"])
                    == (attribution.attribution_id, allocation.row_id, allocation.initiative_id)
                ),
                None,
            )
            status = (
                "adverse_or_cost_claim"
                if allocation.amount <= 0
                else "no_delivery_link"
                if linked is None
                else "delivery_supported"
                if linked["delivery_support_valid"]
                else "delivery_support_invalidated"
            )
            coverage.append(
                {
                    "observation_id": observation.observation_id,
                    "source_id": observation.request.observed.source_id,
                    "period_start": str(observation.request.observed.start),
                    "period_end": str(observation.request.observed.end),
                    "attribution_id": attribution.attribution_id,
                    "row_id": allocation.row_id,
                    "initiative_id": allocation.initiative_id,
                    "amount": allocation.amount,
                    "status": status,
                    "link_event_id": linked["event_id"] if linked else None,
                    "limitation": linked["limitation"]
                    if linked
                    else "No delivery support asserted; accounting and claim evidence remain separate.",
                }
            )
    return {
        "version": "constructed-execution/1",
        "classification": "constructed_operating_exercise",
        "case_id": case.case_id,
        "company_id": case.company_id,
        "exercise_as_of": str(as_of),
        "baseline": view,
        "tasks": tasks,
        "initiatives": [
            {
                "initiative_id": i,
                "gate_task_id": t,
                "steering_decision": state.decision_on(i, as_of),
                "gate_acceptance_valid": next(row["acceptance_valid"] for row in tasks if row["task_id"] == t),
            }
            for i, t in state.gates.items()
        ],
        "claim_links": links,
        "claim_coverage": coverage,
        "events": [e.model_dump(mode="json") for e in scoped],
        "actual_company_execution": None,
        "actual_company_realized_value": None,
        "limitation": "Constructed receipts only. Latest delivery/review corrections are assessed with dated assignment and steering records; this is not a historical knowledge-cutoff replay. Technical acceptance, operating direction and measured value are separate. Positive whole-month claim links require prior gate acceptance and uninterrupted proceed authority; they still do not validate causality. Costs remain in the financial ledger regardless of gate status. No live company operation or KPI activation is authorized.",
    }
