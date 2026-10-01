"""Private capacity proposals alter forecast timing without authorizing operations."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import localcontext
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .models import Record
from .private_financials import PrivateFinancialSnapshot
from .private_grants import validate_key
from .private_intake import SHA
from .private_records import KEY, UUID, require_intake_writer
from .private_underwriting import PrivateUnderwritingInputs, PrivateUnderwritingRevision
from .private_underwriting import calculate as calculate_forecast
from .private_underwriting import verify_revision as verify_underwriting
from .record_chain import seal, verify_link
from .scheduling import Resource, WorkPackage, _PlanningInputs, apply_benefit_timing, schedule


class PrivateResource(Resource):
    assignment: Literal["proposed"] = "proposed"
    capacity_evidence_reference: str = Field(min_length=1)
    capacity_evidence_sha256: SHA
    capacity_attestation: str = Field(min_length=1)


class PrivateOperatingPlan(_PlanningInputs):
    classification: Literal["permissioned_private"] = "permissioned_private"
    resources: tuple[PrivateResource, ...] = Field(min_length=1, max_length=100)
    tasks: tuple[WorkPackage, ...] = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def precision(self) -> Self:
        values = [h for r in self.resources for h in r.weekly_hours if h is not None]
        values.extend(d.hours_per_week for t in self.tasks for d in t.demands)
        for value in values:
            exponent = value.as_tuple().exponent
            if not isinstance(exponent, int) or exponent < -6:
                raise ValueError("private capacity hours support at most six decimal places")
        return self

    def bind(self, revision: PrivateUnderwritingRevision) -> None:
        PrivateUnderwritingRevision.model_validate(revision.model_dump(mode="json"))
        inputs = revision.request.inputs
        if (self.case_id, self.start, self.underwriting_sha256) != (
            revision.case_key,
            inputs.start,
            revision.content_sha256,
        ):
            raise ValueError("private plan must bind the exact underwriting revision, case and start")
        if {g.initiative_id for g in self.benefit_gates} != {d.initiative_id for d in inputs.scenarios[0].drivers}:
            raise ValueError("private benefit gates must cover the exact underwriting initiatives")

    def require_public(self) -> None:
        raise ValueError("private capacity plans cannot be exported as public exhibits")


class CapacityPlanRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    underwriting_revision_id: str = Field(pattern=UUID)
    plan: PrivateOperatingPlan
    rationale: str = Field(min_length=1)


class PrivateCapacityRevision(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    revision_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    sequence: int = Field(ge=1)
    request: CapacityPlanRequest
    origin: Literal["synthetic_test_fixture", "company_export"]
    schedule_result: dict[str, Any]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    capacity_committed: Literal[False] = False
    finance_reviewed: Literal[False] = False
    operating_reviewed: Literal[False] = False
    frozen_comparison_baseline: Literal[False] = False
    operating_action_authorized: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if self.case_key != self.request.plan.case_id:
            raise ValueError("private capacity revision scope mismatch")
        verify_link(
            self, "private capacity revision hash mismatch", "private capacity history requires its predecessor"
        )
        return self

    def require_public(self) -> None:
        raise ValueError("private capacity plans cannot be exported as public exhibits")


def calculate(
    plan: PrivateOperatingPlan,
    underwriting: PrivateUnderwritingRevision,
    financials: PrivateFinancialSnapshot,
) -> dict[str, Any]:
    """Pure reproduction; repositories separately check fresh source/processing authority."""
    plan = PrivateOperatingPlan.model_validate(plan.model_dump(mode="json"))
    plan.bind(underwriting)
    verify_underwriting(underwriting, financials)
    inputs = underwriting.request.inputs
    with localcontext() as ctx:
        ctx.prec = 128
        result = schedule(plan, frozenset(inputs.selected_initiatives))
        scenarios, blocks, timing = apply_benefit_timing(
            inputs.scenarios,
            plan.benefit_gates,
            result,
            frozenset(inputs.selected_initiatives),
        )
        raw = inputs.model_dump(mode="json")
        raw["scenarios"] = scenarios
        scheduled_inputs = PrivateUnderwritingInputs.model_validate(raw)
        scheduled_forecast = calculate_forecast(scheduled_inputs, financials, benefit_blocks=blocks)
    report: dict[str, Any] = json.loads(
        json.dumps(
            {
                **result,
                "calculation_version": "private-capacity-plan/1",
                "classification": "permissioned_private",
                "origin": underwriting.origin,
                "underwriting_revision_id": underwriting.revision_id,
                "underwriting_sha256": underwriting.content_sha256,
                "financial_snapshot_sha256": financials.content_sha256,
                "timing": timing,
                "original_financials": underwriting.forecast,
                "scheduled_financials": scheduled_forecast,
                "scheduled_inputs": scheduled_inputs.model_dump(mode="json"),
                "cost_treatment": "Selected initiatives retain all their dated costs. Explicitly avoidable costs of unselected initiatives are excluded; retained commitments remain once. A blocked selected initiative keeps its costs. No cost is rescheduled by the capacity solver.",
                "capacity_committed": False,
                "operating_action_authorized": False,
            },
            default=str,
        )
    )
    return report


def prepare_revision(
    company_id: str,
    case_key: str,
    request: CapacityPlanRequest,
    underwriting: PrivateUnderwritingRevision,
    financials: PrivateFinancialSnapshot,
    previous: PrivateCapacityRevision | None,
) -> PrivateCapacityRevision:
    principal = require_intake_writer(company_id)
    request = CapacityPlanRequest.model_validate(request.model_dump(mode="json"))
    if (company_id, case_key, request.underwriting_revision_id) != (
        underwriting.company_id,
        underwriting.case_key,
        underwriting.revision_id,
    ):
        raise ValueError("private capacity request requires its exact same-company underwriting revision")
    now = datetime.now(UTC)
    if underwriting.recorded_at > now:
        raise ValueError("private capacity plan cannot predate its underwriting revision")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("private capacity plan requires the current case head")
    if previous and (
        (previous.company_id, previous.case_key, previous.origin) != (company_id, case_key, underwriting.origin)
        or previous.recorded_at > now
    ):
        raise ValueError("private capacity history cannot change scope, origin or chronology")
    payload: dict[str, Any] = dict(
        revision_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        origin=underwriting.origin,
        schedule_result=calculate(request.plan, underwriting, financials),
        author=principal.subject,
        recorded_at=now,
    )
    return seal(PrivateCapacityRevision, payload)


def verify_revision(
    revision: PrivateCapacityRevision,
    underwriting: PrivateUnderwritingRevision,
    financials: PrivateFinancialSnapshot,
) -> None:
    PrivateCapacityRevision.model_validate(revision.model_dump(mode="json"))
    if (revision.company_id, revision.case_key, revision.request.underwriting_revision_id, revision.origin) != (
        underwriting.company_id,
        underwriting.case_key,
        underwriting.revision_id,
        underwriting.origin,
    ):
        raise ValueError("private capacity revision source scope changed")
    if revision.schedule_result != calculate(revision.request.plan, underwriting, financials):
        raise ValueError("private capacity plan does not reproduce from its exact underwriting and financial inputs")
