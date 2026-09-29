"""Reviewed private counterfactuals and whole-month observations, without causal claims."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .models import Record
from .private_baselines import PrivateBaseline
from .private_financials import (
    FinancialAmounts,
    PrivateFinancialSnapshot,
    PrivateMonth,
    amounts,
    require_snapshot_writer,
)
from .private_grants import validate_key
from .private_intake import SHA, Amount, Control
from .private_records import KEY, UUID, content_hash, require_finance_reviewer, require_intake_writer
from .realization import COMPONENTS, ENTRY_COMPONENT, Component
from .underwriting import Entry, month_end, month_start


class CounterfactualAdjustment(Record):
    adjustment_id: str = Field(pattern=KEY)
    amount: Amount
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    evidence_sha256: SHA

    @field_validator("amount", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)


class CounterfactualComponent(Record):
    period: date
    component: Component
    anchor_month: date
    rationale: str = Field(min_length=1)
    adjustments: tuple[CounterfactualAdjustment, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if len({a.adjustment_id for a in self.adjustments}) != len(self.adjustments):
            raise ValueError("counterfactual adjustment IDs must be unique within a component")
        return self


class CounterfactualRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    baseline_id: str = Field(pattern=UUID)
    baseline_sha256: SHA
    first_month: date
    months: int = Field(ge=1, le=24, strict=True)
    design_timing: Literal["prospective", "retrospective"]
    timing_rationale: str = Field(min_length=1)
    method: Literal["historical_financials_plus_authored_adjustments"] = (
        "historical_financials_plus_authored_adjustments"
    )
    scope_and_limits: str = Field(min_length=1)
    components: tuple[CounterfactualComponent, ...] = Field(min_length=6, max_length=144)

    @model_validator(mode="after")
    def coverage(self) -> Self:
        expected = {(month_start(self.first_month, n), c) for n in range(self.months) for c in COMPONENTS}
        actual = [(c.period, c.component) for c in self.components]
        if self.first_month.day != 1 or set(actual) != expected or len(actual) != len(expected):
            raise ValueError("counterfactual requires each complete month and component, including known zeros")
        return self


class PrivateCounterfactual(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    revision_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    counterfactual_key: str
    sequence: int = Field(ge=1)
    request: CounterfactualRequest
    origin: Literal["synthetic_test_fixture", "company_export"]
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    financial_snapshot_sha256: SHA
    monthly: tuple[PrivateMonth, ...]
    period_totals: FinancialAmounts
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    finance_reviewed: Literal[False] = False
    causal_value_claim: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        validate_key(self.counterfactual_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private counterfactual hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("counterfactual history requires its predecessor")
        if self.request.design_timing == "prospective" and self.recorded_at.date() >= self.request.first_month:
            raise ValueError("prospective counterfactual must be authored before the first measurement month")
        return self

    def require_public(self) -> None:
        raise ValueError("private counterfactuals cannot be exported as public exhibits")


class CounterfactualAssessment(Record):
    perimeter_units_and_definitions: str = Field(min_length=1)
    anchor_and_adjustments: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)
    timing_and_comparison_limits: str = Field(min_length=1)


class CounterfactualReviewRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    expected_counterfactual_sha256: SHA
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    evidence_sha256: SHA
    assessment: CounterfactualAssessment | None = None

    @model_validator(mode="after")
    def acceptance(self) -> Self:
        if (self.decision == "accept") != (self.assessment is not None):
            raise ValueError("only counterfactual acceptance requires a complete finance assessment")
        return self


class CounterfactualReview(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    review_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    counterfactual_revision_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: CounterfactualReviewRequest
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    causal_value_claim: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if content_hash(self) != self.content_sha256:
            raise ValueError("counterfactual review hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("counterfactual review requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private counterfactual reviews cannot be exported as public exhibits")


class PrivateObservationRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    counterfactual_revision_id: str = Field(pattern=UUID)
    counterfactual_sha256: SHA
    counterfactual_review_sha256: SHA
    actual_snapshot_id: str = Field(pattern=UUID)
    actual_snapshot_sha256: SHA
    first_month: date
    months: int = Field(ge=1, le=24, strict=True)
    scope_comparability_attestation: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class PrivateObservation(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    observation_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    measurement_key: str
    sequence: int = Field(ge=1)
    request: PrivateObservationRequest
    baseline_id: str = Field(pattern=UUID)
    baseline_sha256: SHA
    counterfactual_key: str
    origin: Literal["synthetic_test_fixture", "company_export"]
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    result: dict[str, Any]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    causal_value_claim: Literal[False] = False
    operating_action_authorized: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        validate_key(self.measurement_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private observation hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private observation requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private observations cannot be exported as public exhibits")


def financial_amounts(controls: tuple[Control, ...], start: date, end: date) -> FinancialAmounts:
    entries = tuple(
        Entry(
            day=c.period,
            initiative_id="unattributed",
            component=ENTRY_COMPONENT[c.component],
            amount=c.amount,
            reference=c.component,
        )
        for c in controls
    )
    return amounts(entries, start, end)


def calculate_counterfactual(
    request: CounterfactualRequest,
    baseline: PrivateBaseline,
    anchor: PrivateFinancialSnapshot,
) -> tuple[tuple[PrivateMonth, ...], FinancialAmounts]:
    request = CounterfactualRequest.model_validate(request.model_dump(mode="json"))
    if (request.baseline_id, request.baseline_sha256, baseline.financial_snapshot_sha256) != (
        baseline.baseline_id,
        baseline.content_sha256,
        anchor.content_sha256,
    ) or (baseline.company_id, baseline.case_key, baseline.entity_id, baseline.currency, baseline.origin) != (
        anchor.company_id,
        anchor.case_key,
        anchor.entity_id,
        anchor.currency,
        anchor.origin,
    ):
        raise ValueError("counterfactual requires its exact baseline and historical financial anchor")
    forecast_months = {date.fromisoformat(m["start"]) for m in baseline.frozen_forecast["monthly"]}
    source = {(c.period, c.component): c.amount for month in anchor.monthly for c in month.components}
    controls = []
    with localcontext() as ctx:
        ctx.prec = 40
        for component in request.components:
            key = (component.anchor_month, component.component)
            if key not in source or component.period not in forecast_months:
                raise ValueError("counterfactual anchor or forecast month is unavailable")
            value = source[key] + sum((a.amount for a in component.adjustments), Decimal(0))
            controls.append(Control(period=component.period, component=component.component, amount=value))
        monthly = tuple(
            PrivateMonth(
                start=month_start(request.first_month, n),
                end=month_end(request.first_month, n),
                components=tuple(c for c in controls if c.period == month_start(request.first_month, n)),
                amounts=financial_amounts(
                    tuple(controls), month_start(request.first_month, n), month_end(request.first_month, n)
                ),
            )
            for n in range(request.months)
        )
        total = financial_amounts(
            tuple(controls), request.first_month, month_end(request.first_month, request.months - 1)
        )
    return monthly, total


def prepare_counterfactual(
    company_id: str,
    case_key: str,
    key: str,
    request: CounterfactualRequest,
    baseline: PrivateBaseline,
    anchor: PrivateFinancialSnapshot,
    previous: PrivateCounterfactual | None,
) -> PrivateCounterfactual:
    principal = require_intake_writer(company_id)
    request = CounterfactualRequest.model_validate(request.model_dump(mode="json"))
    validate_key(key)
    if (company_id, case_key) != (baseline.company_id, baseline.case_key):
        raise ValueError("counterfactual belongs to another company or case")
    now = datetime.now(UTC)
    if baseline.recorded_at > now or (previous and previous.recorded_at > now):
        raise ValueError("counterfactual predates its baseline or predecessor")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("counterfactual requires the current stream head")
    if previous and (
        previous.company_id,
        previous.case_key,
        previous.counterfactual_key,
        previous.request.baseline_id,
        previous.request.first_month,
        previous.request.months,
    ) != (
        company_id,
        case_key,
        key,
        request.baseline_id,
        request.first_month,
        request.months,
    ):
        raise ValueError("counterfactual correction cannot change scope, baseline or period window")
    monthly, total = calculate_counterfactual(request, baseline, anchor)
    payload: dict[str, Any] = dict(
        revision_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        counterfactual_key=key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        origin=baseline.origin,
        entity_id=baseline.entity_id,
        currency=baseline.currency,
        financial_snapshot_sha256=anchor.content_sha256,
        monthly=monthly,
        period_totals=total,
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateCounterfactual.model_construct(**payload))
    return PrivateCounterfactual.model_validate(payload)


def verify_counterfactual(
    record: PrivateCounterfactual, baseline: PrivateBaseline, anchor: PrivateFinancialSnapshot
) -> None:
    PrivateCounterfactual.model_validate(record.model_dump(mode="json"))
    if record.recorded_at < baseline.recorded_at:
        raise ValueError("counterfactual predates its frozen baseline")
    if (
        record.company_id,
        record.case_key,
        record.entity_id,
        record.currency,
        record.origin,
        record.financial_snapshot_sha256,
    ) != (
        baseline.company_id,
        baseline.case_key,
        baseline.entity_id,
        baseline.currency,
        baseline.origin,
        anchor.content_sha256,
    ):
        raise ValueError("counterfactual source scope changed")
    if (record.monthly, record.period_totals) != calculate_counterfactual(record.request, baseline, anchor):
        raise ValueError("counterfactual does not reproduce from its historical anchor and authored adjustments")


def counterfactual_review_head(
    record: PrivateCounterfactual, reviews: list[CounterfactualReview]
) -> CounterfactualReview | None:
    previous = None
    for review in reviews:
        CounterfactualReview.model_validate(review.model_dump(mode="json"))
        if (
            review.company_id,
            review.case_key,
            review.counterfactual_revision_id,
            review.request.expected_counterfactual_sha256,
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
            raise ValueError("counterfactual review history is foreign, incomplete or out of order")
        if review.request.decision == "withdraw" and (previous is None or previous.request.decision != "accept"):
            raise ValueError("counterfactual review withdrawal has no prior acceptance")
        if (
            review.request.decision == "accept"
            and record.request.design_timing == "prospective"
            and review.recorded_at.date() >= record.request.first_month
        ):
            raise ValueError("prospective counterfactual must be accepted before its first measurement month")
        previous = review
    return previous


def prepare_counterfactual_review(
    record: PrivateCounterfactual,
    request: CounterfactualReviewRequest,
    reviews: list[CounterfactualReview],
) -> CounterfactualReview:
    principal = require_finance_reviewer(record.company_id)
    request = CounterfactualReviewRequest.model_validate(request.model_dump(mode="json"))
    previous = counterfactual_review_head(record, reviews)
    if request.expected_counterfactual_sha256 != record.content_sha256:
        raise ValueError("counterfactual review requires the exact proposal hash")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("counterfactual review requires its current head")
    if request.decision == "withdraw" and (previous is None or previous.request.decision != "accept"):
        raise ValueError("withdrawal requires a currently accepted counterfactual review")
    payload: dict[str, Any] = dict(
        review_id=str(uuid.uuid4()),
        company_id=record.company_id,
        case_key=record.case_key,
        counterfactual_revision_id=record.revision_id,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        author=principal.subject,
        recorded_at=datetime.now(UTC),
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(CounterfactualReview.model_construct(**payload))
    result = CounterfactualReview.model_validate(payload)
    counterfactual_review_head(record, [*reviews, result])
    return result


def planned_components(month: dict[str, Any]) -> dict[str, Decimal]:
    return {
        "revenue": Decimal(month["gross_price_benefit"]) + Decimal(month["revenue_leakage"]),
        "operating_expense": sum(
            (Decimal(month[k]) for k in ("variable_cost", "cost_removed", "recurring_cost")), Decimal(0)
        ),
        **{
            k: Decimal(month[k])
            for k in ("implementation_expense", "operating_cash", "working_capital_cash", "capex_cash")
        },
    }


def calculate_observation(
    request: PrivateObservationRequest,
    counterfactual: PrivateCounterfactual,
    review: CounterfactualReview,
    baseline: PrivateBaseline,
    actual: PrivateFinancialSnapshot,
    anchor: PrivateFinancialSnapshot,
    *,
    now: datetime,
) -> dict[str, Any]:
    request = PrivateObservationRequest.model_validate(request.model_dump(mode="json"))
    verify_counterfactual(counterfactual, baseline, anchor)
    CounterfactualReview.model_validate(review.model_dump(mode="json"))
    PrivateFinancialSnapshot.model_validate(actual.model_dump(mode="json"))
    if (
        (
            request.counterfactual_revision_id,
            request.counterfactual_sha256,
            request.counterfactual_review_sha256,
            request.actual_snapshot_id,
            request.actual_snapshot_sha256,
        )
        != (
            counterfactual.revision_id,
            counterfactual.content_sha256,
            review.content_sha256,
            actual.snapshot_id,
            actual.content_sha256,
        )
        or review.request.decision != "accept"
        or review.counterfactual_revision_id != counterfactual.revision_id
        or review.request.expected_counterfactual_sha256 != counterfactual.content_sha256
        or (review.company_id, review.case_key) != (counterfactual.company_id, counterfactual.case_key)
    ):
        raise ValueError("observation requires exact accepted counterfactual and actual financial versions")
    if (actual.company_id, actual.case_key, actual.entity_id, actual.currency, actual.origin) != (
        counterfactual.company_id,
        counterfactual.case_key,
        counterfactual.entity_id,
        counterfactual.currency,
        counterfactual.origin,
    ) or actual.request.purpose != "observed_actuals":
        raise ValueError("observation actuals must retain entity, currency, origin and observed-actuals purpose")
    definition_fields = ("accounting_basis", "earnings_basis", "cash_basis")
    if any(getattr(actual.request.definition, f) != getattr(anchor.request.definition, f) for f in definition_fields):
        raise ValueError("observation accounting and cash definitions differ from the reviewed anchor")
    end = month_end(request.first_month, request.months - 1)
    if request.first_month.day != 1 or end >= now.date():
        raise ValueError("observations require completed calendar months; no future or partial-month results")
    if max(actual.recorded_at, counterfactual.recorded_at, review.recorded_at, baseline.recorded_at) > now:
        raise ValueError("observation predates a required source or review")
    actual_months = {m.start: m for m in actual.monthly}
    counter_months = {m.start: m for m in counterfactual.monthly}
    frozen_months = {date.fromisoformat(m["start"]): m for m in baseline.frozen_forecast["monthly"]}
    monthly = []
    all_controls: dict[str, list[Control]] = {
        k: [] for k in ("actual", "counterfactual", "difference", "frozen_forecast", "variance")
    }
    with localcontext() as ctx:
        ctx.prec = 40
        for n in range(request.months):
            period = month_start(request.first_month, n)
            if period not in actual_months or period not in counter_months or period not in frozen_months:
                raise ValueError("observation period is missing from actuals, counterfactual or frozen forecast")
            observed: dict[str, Decimal] = {c.component: c.amount for c in actual_months[period].components}
            expected: dict[str, Decimal] = {c.component: c.amount for c in counter_months[period].components}
            planned = planned_components(frozen_months[period])
            rows = []
            for component in COMPONENTS:
                difference = observed[component] - expected[component]
                values = dict(
                    actual=observed[component],
                    counterfactual=expected[component],
                    difference=difference,
                    frozen_forecast=planned[component],
                    variance=difference - planned[component],
                )
                rows.append({"component": component, **values, "attributed": Decimal(0), "unattributed": difference})
                for kind, value in values.items():
                    all_controls[kind].append(Control(period=period, component=component, amount=value))
            values_by_kind = {
                k: financial_amounts(tuple(v), period, month_end(period)).model_dump(mode="json")
                for k, v in all_controls.items()
            }
            monthly.append(
                {"start": period, "end": month_end(period), "components": rows, "financials": values_by_kind}
            )
        totals = {
            k: financial_amounts(tuple(v), request.first_month, end).model_dump(mode="json")
            for k, v in all_controls.items()
        }
    result: dict[str, Any] = json.loads(
        json.dumps(
            {
                "calculation_version": "private-observation/1",
                "classification": "permissioned_private",
                "origin": actual.origin,
                "currency": actual.currency,
                "unit_scale": 1,
                "first_month": request.first_month,
                "end": end,
                "monthly": monthly,
                "totals": totals,
                "counterfactual_design_timing": counterfactual.request.design_timing,
                "unattributed_difference": totals["difference"],
                "causal_value_claim": False,
                "limitation": "Entity-level actual-minus-authored-counterfactual differences, not causal impact. All differences remain unattributed. Forecast variances retain the frozen plan; no partial-month or day-100 actual is inferred.",
            },
            default=str,
        )
    )
    return result


def prepare_observation(
    company_id: str,
    case_key: str,
    key: str,
    request: PrivateObservationRequest,
    counterfactual: PrivateCounterfactual,
    review: CounterfactualReview,
    baseline: PrivateBaseline,
    actual: PrivateFinancialSnapshot,
    anchor: PrivateFinancialSnapshot,
    previous: PrivateObservation | None,
) -> PrivateObservation:
    principal = require_snapshot_writer(company_id)
    request = PrivateObservationRequest.model_validate(request.model_dump(mode="json"))
    validate_key(key)
    if (company_id, case_key) != (baseline.company_id, baseline.case_key):
        raise ValueError("observation belongs to another company or case")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("observation requires its current stream head")
    now = datetime.now(UTC)
    if previous and (
        (
            previous.company_id,
            previous.case_key,
            previous.measurement_key,
            previous.baseline_id,
            previous.counterfactual_key,
            previous.request.first_month,
            previous.request.months,
        )
        != (
            company_id,
            case_key,
            key,
            baseline.baseline_id,
            counterfactual.counterfactual_key,
            request.first_month,
            request.months,
        )
        or previous.recorded_at > now
    ):
        raise ValueError(
            "observation correction cannot change baseline, counterfactual stream, scope, window or chronology"
        )
    payload: dict[str, Any] = dict(
        observation_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        measurement_key=key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        baseline_id=baseline.baseline_id,
        baseline_sha256=baseline.content_sha256,
        counterfactual_key=counterfactual.counterfactual_key,
        origin=actual.origin,
        entity_id=actual.entity_id,
        currency=actual.currency,
        result=calculate_observation(request, counterfactual, review, baseline, actual, anchor, now=now),
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateObservation.model_construct(**payload))
    return PrivateObservation.model_validate(payload)


def verify_observation(
    record: PrivateObservation,
    counterfactual: PrivateCounterfactual,
    review: CounterfactualReview,
    baseline: PrivateBaseline,
    actual: PrivateFinancialSnapshot,
    anchor: PrivateFinancialSnapshot,
) -> None:
    PrivateObservation.model_validate(record.model_dump(mode="json"))
    if (
        record.company_id,
        record.case_key,
        record.baseline_id,
        record.baseline_sha256,
        record.entity_id,
        record.currency,
        record.origin,
        record.counterfactual_key,
    ) != (
        baseline.company_id,
        baseline.case_key,
        baseline.baseline_id,
        baseline.content_sha256,
        actual.entity_id,
        actual.currency,
        actual.origin,
        counterfactual.counterfactual_key,
    ):
        raise ValueError("private observation source scope changed")
    if record.result != calculate_observation(
        record.request, counterfactual, review, baseline, actual, anchor, now=record.recorded_at
    ):
        raise ValueError("private observation does not reproduce from its accepted sources and reviewed counterfactual")
