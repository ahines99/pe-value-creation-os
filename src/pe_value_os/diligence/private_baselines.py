"""Human plan reviews and immutable private comparison baselines, never execution grants."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .. import security
from .models import Record
from .private_capacity import PrivateCapacityRevision
from .private_grants import validate_key
from .private_intake import SHA, require_operator
from .private_records import KEY, UUID, content_hash

ReviewKind = Literal["finance", "operating"]


class FinanceAssessment(Record):
    kind: Literal["finance"] = "finance"
    accounting_and_controls: str = Field(min_length=1)
    assumptions_and_eligibility: str = Field(min_length=1)
    cash_and_cost_timing: str = Field(min_length=1)
    valuation_limitations: str = Field(min_length=1)


class OperatingAssessment(Record):
    kind: Literal["operating"] = "operating"
    owners_and_capacity: str = Field(min_length=1)
    dependencies_and_constraints: str = Field(min_length=1)
    measurement_and_stop_conditions: str = Field(min_length=1)
    capacity_confirmed_for_planning: Literal[True]


Assessment = Annotated[FinanceAssessment | OperatingAssessment, Field(discriminator="kind")]


class PlanReviewRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    expected_capacity_sha256: SHA
    review_kind: ReviewKind
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    evidence_sha256: SHA
    assessment: Assessment | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.decision == "accept":
            if self.assessment is None or self.assessment.kind != self.review_kind:
                raise ValueError("acceptance requires the matching finance or operating assessment")
        elif self.assessment is not None:
            raise ValueError("only acceptance may assert a completed assessment")
        return self


class PrivatePlanReview(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    review_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    capacity_revision_id: str = Field(pattern=UUID)
    review_kind: ReviewKind
    sequence: int = Field(ge=1)
    request: PlanReviewRequest
    actor: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    operating_action_authorized: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if self.review_kind != self.request.review_kind or content_hash(self) != self.content_sha256:
            raise ValueError("private plan review kind or hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private plan review requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private plan reviews cannot be exported as public exhibits")


class BaselineRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    capacity_revision_id: str = Field(pattern=UUID)
    expected_capacity_sha256: SHA
    finance_review_id: str = Field(pattern=UUID)
    finance_review_sha256: SHA
    operating_review_id: str = Field(pattern=UUID)
    operating_review_sha256: SHA
    scenario_id: Literal["downside", "base", "upside"]
    rationale: str = Field(min_length=1)


class PrivateBaseline(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    baseline_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    sequence: int = Field(ge=1)
    request: BaselineRequest
    origin: Literal["synthetic_test_fixture", "company_export"]
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    financial_snapshot_sha256: SHA
    underwriting_sha256: SHA
    frozen_forecast: dict[str, Any]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    purpose: Literal["comparison_only"] = "comparison_only"
    operating_action_authorized: Literal[False] = False
    causal_value_claim: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private baseline hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private baseline requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private baselines cannot be exported as public exhibits")


def require_reviewer(company_id: str, kind: ReviewKind) -> security.Principal:
    from ..approvals import can_approve

    principal = require_operator(company_id)
    if kind not in {"finance", "operating"} or not can_approve(principal, company_id, kind + "_reviewer"):
        raise security.deny("Private plan decisions require a matching human reviewer", "private_plan_review")
    return principal


def require_baseline_author(company_id: str) -> security.Principal:
    from ..approvals import can_approve

    principal = require_operator(company_id)
    if not can_approve(principal, company_id, "approver"):
        raise security.deny("Private baseline designation requires a human approver", "private_baseline_author")
    return principal


def review_heads(plan: PrivateCapacityRevision, reviews: list[PrivatePlanReview]) -> dict[str, PrivatePlanReview]:
    heads: dict[str, PrivatePlanReview] = {}
    for review in reviews:
        PrivatePlanReview.model_validate(review.model_dump(mode="json"))
        if (
            review.company_id,
            review.case_key,
            review.capacity_revision_id,
            review.request.expected_capacity_sha256,
        ) != (
            plan.company_id,
            plan.case_key,
            plan.revision_id,
            plan.content_sha256,
        ):
            raise ValueError("private plan review belongs to another exact revision")
        prior = heads.get(review.review_kind)
        if (review.sequence, review.request.expected_previous_sha256) != (
            prior.sequence + 1 if prior else 1,
            prior.content_sha256 if prior else None,
        ) or review.recorded_at < (prior.recorded_at if prior else plan.recorded_at):
            raise ValueError("private plan review history is incomplete or out of order")
        heads[review.review_kind] = review
    return heads


def prepare_review(
    plan: PrivateCapacityRevision,
    request: PlanReviewRequest,
    reviews: list[PrivatePlanReview],
) -> PrivatePlanReview:
    principal = require_reviewer(plan.company_id, request.review_kind)
    request = PlanReviewRequest.model_validate(request.model_dump(mode="json"))
    PrivateCapacityRevision.model_validate(plan.model_dump(mode="json"))
    if request.expected_capacity_sha256 != plan.content_sha256:
        raise ValueError("private review requires its exact capacity revision")
    previous = review_heads(plan, reviews).get(request.review_kind)
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("private review requires the current role-specific head")
    now = datetime.now(UTC)
    if plan.recorded_at > now or (previous and previous.recorded_at > now):
        raise ValueError("private plan review predates its plan or parent")
    if request.decision == "withdraw" and (previous is None or previous.request.decision != "accept"):
        raise ValueError("withdrawal requires a currently accepted review")
    if (
        request.decision == "accept"
        and request.review_kind == "operating"
        and any(t["status"] == "blocked" for t in plan.schedule_result["tasks"])
    ):
        raise ValueError("blocked capacity cannot receive operating acceptance")
    payload: dict[str, Any] = dict(
        review_id=str(uuid.uuid4()),
        company_id=plan.company_id,
        case_key=plan.case_key,
        capacity_revision_id=plan.revision_id,
        review_kind=request.review_kind,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        actor=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivatePlanReview.model_construct(**payload))
    return PrivatePlanReview.model_validate(payload)


def accepted_reviews(
    plan: PrivateCapacityRevision,
    reviews: list[PrivatePlanReview],
    request: BaselineRequest,
) -> tuple[PrivatePlanReview, PrivatePlanReview]:
    heads = review_heads(plan, reviews)
    finance, operating = heads.get("finance"), heads.get("operating")
    if (
        finance is None
        or operating is None
        or (
            finance.review_id,
            finance.content_sha256,
            finance.request.decision,
            operating.review_id,
            operating.content_sha256,
            operating.request.decision,
        )
        != (
            request.finance_review_id,
            request.finance_review_sha256,
            "accept",
            request.operating_review_id,
            request.operating_review_sha256,
            "accept",
        )
    ):
        raise ValueError("baseline requires the exact current accepted finance and operating reviews")
    if finance.actor == operating.actor:
        raise ValueError("baseline requires two distinct human reviewers")
    return finance, operating


def forecast(plan: PrivateCapacityRevision, request: BaselineRequest) -> dict[str, Any]:
    if (request.capacity_revision_id, request.expected_capacity_sha256) != (plan.revision_id, plan.content_sha256):
        raise ValueError("baseline requires its exact capacity revision")
    if any(t["status"] == "blocked" for t in plan.schedule_result["tasks"]):
        raise ValueError("blocked capacity cannot support a frozen baseline")
    return next(
        s for s in plan.schedule_result["scheduled_financials"]["scenarios"] if s["scenario_id"] == request.scenario_id
    )


def prepare_baseline(
    company_id: str,
    case_key: str,
    request: BaselineRequest,
    plan: PrivateCapacityRevision,
    reviews: list[PrivatePlanReview],
    previous: PrivateBaseline | None,
) -> PrivateBaseline:
    principal = require_baseline_author(company_id)
    request = BaselineRequest.model_validate(request.model_dump(mode="json"))
    if (company_id, case_key) != (plan.company_id, plan.case_key):
        raise ValueError("baseline belongs to another company or case")
    finance, operating = accepted_reviews(plan, reviews, request)
    frozen = forecast(plan, request)
    now = datetime.now(UTC)
    if max(plan.recorded_at, finance.recorded_at, operating.recorded_at) > now:
        raise ValueError("baseline cannot predate its plan or reviews")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("baseline designation requires the current case head")
    if previous and (
        (previous.company_id, previous.case_key, previous.origin) != (company_id, case_key, plan.origin)
        or previous.recorded_at > now
    ):
        raise ValueError("baseline history cannot change scope, origin or chronology")
    payload: dict[str, Any] = dict(
        baseline_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        origin=plan.origin,
        entity_id=plan.schedule_result["scheduled_inputs"]["entity_id"],
        currency=plan.schedule_result["scheduled_financials"]["currency"],
        financial_snapshot_sha256=plan.schedule_result["financial_snapshot_sha256"],
        underwriting_sha256=plan.schedule_result["underwriting_sha256"],
        frozen_forecast=copy.deepcopy(frozen),
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateBaseline.model_construct(**payload))
    return PrivateBaseline.model_validate(payload)


def baseline_view(
    baseline: PrivateBaseline,
    plan: PrivateCapacityRevision,
    reviews: list[PrivatePlanReview],
    baselines: list[PrivateBaseline],
    *,
    source_current: bool,
) -> dict[str, Any]:
    """Caller reproduces original source/plan under fresh processing permission first."""
    PrivateBaseline.model_validate(baseline.model_dump(mode="json"))
    if (baseline.company_id, baseline.case_key, baseline.origin) != (plan.company_id, plan.case_key, plan.origin):
        raise ValueError("baseline source scope changed")
    if (baseline.entity_id, baseline.currency, baseline.financial_snapshot_sha256, baseline.underwriting_sha256) != (
        plan.schedule_result["scheduled_inputs"]["entity_id"],
        plan.schedule_result["scheduled_financials"]["currency"],
        plan.schedule_result["financial_snapshot_sha256"],
        plan.schedule_result["underwriting_sha256"],
    ):
        raise ValueError("baseline financial scope changed")
    if baseline.frozen_forecast != forecast(plan, baseline.request):
        raise ValueError("frozen forecast differs from its exact saved plan")
    review_heads(plan, reviews)
    try:
        accepted_reviews(plan, reviews, baseline.request)
        review_current = True
    except ValueError:
        review_current = False
    if not baselines or any((b.company_id, b.case_key) != (baseline.company_id, baseline.case_key) for b in baselines):
        raise ValueError("baseline view cannot mix designation histories")
    current = baselines[-1].baseline_id == baseline.baseline_id
    return {
        "baseline": baseline.model_dump(mode="json"),
        "current_designation": current,
        "supporting_reviews_currently_accepted": review_current,
        "source_currently_accepted": source_current,
        "processing_currently_permitted": True,
        "usable_for_comparison": current and review_current and source_current,
        "frozen_forecast": copy.deepcopy(baseline.frozen_forecast),
        "operating_action_authorized": False,
        "authority": "Reviewed private comparison baseline. Later forecasts never move it implicitly; current support is reported separately. This is not authority to intervene or a causal value claim.",
    }
