"""Immutable research-case revisions and exact-version review semantics.

Research acceptance does not authorize operations, activate KPIs or certify value.
The constructed exercise can record simulated reviews without impersonating a human.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .. import security
from .models import Record
from .operating_sources import source_forecast
from .scheduling import OperatingPlan, evaluate_plan
from .source_revisions import SourceCasePayload, financial_snapshot
from .underwriting import UnderwritingCase, evaluate


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class CasePayload(Record):
    schema_version: Literal[1] = 1
    underwriting: UnderwritingCase
    operating_plan: OperatingPlan | None = None
    decision_question: str = Field(min_length=1)
    counterevidence: tuple[str, ...] = Field(min_length=1)
    unresolved_items: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def scope(self) -> Self:
        self.underwriting.require_public()
        if self.operating_plan is not None:
            self.operating_plan.bind(self.underwriting)
        return self


class RevisionDraft(Record):
    stage: Literal["underwriting", "close_validation", "ownership_review", "exit_review"]
    effective_on: date
    reason: str = Field(min_length=1)
    payload: CasePayload | SourceCasePayload


class InvestmentCase(Record):
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    company_id: str
    label: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    classification: Literal["constructed_operating_exercise"] = "constructed_operating_exercise"
    created_by: str
    created_at: datetime
    version: int = Field(ge=0)
    current_revision_id: str | None = None
    original_revision_id: str | None = None


class CaseRevision(Record):
    revision_id: str
    case_id: str
    company_id: str
    sequence: int = Field(ge=1)
    parent_revision_id: str | None
    recorded_at: datetime
    author: str
    draft: RevisionDraft
    # JSON strings avoid mutable nested dicts escaping a frozen record and preserve
    # the original calculator's output across future version changes.
    financial_result_json: str
    schedule_result_json: str | None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_content(self) -> Self:
        raw = self.model_dump(mode="json", exclude={"content_sha256"})
        if digest(json.dumps(raw, sort_keys=True)) != self.content_sha256:
            raise ValueError("revision content hash mismatch")
        return self


class ReviewRequest(Record):
    expected_revision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["human", "simulation"]
    decision: Literal["accept", "request_changes", "reject", "withdraw"]
    rationale: str = Field(min_length=1)
    supersedes_review_id: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )


class CaseReview(Record):
    review_id: str
    case_id: str
    company_id: str
    revision_id: str
    revision_sha256: str
    mode: Literal["human", "simulation"]
    decision: Literal["accept", "request_changes", "reject", "withdraw"]
    rationale: str
    actor: str
    actor_type: Literal["human", "service", "model"]
    recorded_at: datetime
    supersedes_review_id: str | None


def writer(company_id: str) -> security.Principal:
    principal = security.require(company_id)
    if not principal.has_scope(security.WRITE_SCOPE):
        raise security.deny("Case changes require pvc.write", "oauth_scope")
    return principal


def new_case(company_id: str, case_id: str, label: str, currency: str) -> InvestmentCase:
    principal = writer(company_id)
    return InvestmentCase(
        case_id=case_id,
        company_id=company_id,
        label=label,
        currency=currency,
        created_by=principal.subject,
        created_at=datetime.now(UTC),
        version=0,
    )


def prepare_revision(case: InvestmentCase, draft: RevisionDraft, parent: CaseRevision | None) -> CaseRevision:
    principal = writer(case.company_id)
    if draft.payload.underwriting.case_id != case.case_id or draft.payload.underwriting.currency != case.currency:
        raise ValueError("revision must retain its case identity and currency")
    if parent is None and draft.stage != "underwriting":
        raise ValueError("first revision must be original underwriting")
    if parent is not None:
        old = parent.draft.payload.underwriting
        new = draft.payload.underwriting
        if draft.effective_on < parent.draft.effective_on:
            raise ValueError("effective date cannot move backward; append a disclosed correction at current date")
        if new.start != old.start or new.months != old.months:
            raise ValueError("revision must preserve the comparison calendar")
        if new.company != old.company:
            raise ValueError("revision must preserve the reference company")
        if {(d.initiative_id, d.kind, d.benefit_pool) for d in new.scenarios[0].drivers} != {
            (d.initiative_id, d.kind, d.benefit_pool) for d in old.scenarios[0].drivers
        }:
            raise ValueError("initiative lineage changes require an explicit mapping; title matching is insufficient")
        if isinstance(parent.draft.payload, SourceCasePayload) and not isinstance(draft.payload, SourceCasePayload):
            raise ValueError("a source-backed revision cannot silently discard its operating-source basis")
    schedule_json = None
    if isinstance(draft.payload, SourceCasePayload):
        if parent is None:
            raise ValueError("source challenge requires an existing original revision")
        payload = SourceCasePayload.model_validate(draft.payload.model_dump(mode="json"))
        payload.bind_parent(parent)
        source = source_forecast(payload.operating_sources, payload.underwriting, payload.operating_plan)
        financial = financial_snapshot(payload, parent, source)
        report = source["schedule"]
    elif draft.payload.operating_plan is None:
        financial = evaluate(draft.payload.underwriting)
    else:
        report = evaluate_plan(draft.payload.operating_plan, draft.payload.underwriting)
        financial = report["scheduled_financials"]
    if draft.payload.operating_plan is not None:
        schedule_json = json.dumps(
            {
                key: report[key]
                for key in (
                    "schedule_version",
                    "plan_sha256",
                    "tasks",
                    "capacity",
                    "timing",
                    "authority",
                    "method",
                    "cost_treatment",
                )
            },
            default=str,
            sort_keys=True,
        )
    raw: dict[str, Any] = {
        "revision_id": str(uuid.uuid4()),
        "case_id": case.case_id,
        "company_id": case.company_id,
        "sequence": case.version + 1,
        "parent_revision_id": case.current_revision_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "author": principal.subject,
        "draft": draft.model_dump(mode="json"),
        "financial_result_json": json.dumps(financial, default=str, sort_keys=True),
        "schedule_result_json": schedule_json,
    }
    # Normalize datetime serialization before signing the immutable envelope.
    raw["recorded_at"] = raw["recorded_at"].replace("+00:00", "Z")
    return CaseRevision.model_validate({**raw, "content_sha256": digest(json.dumps(raw, sort_keys=True))})


def prepare_review(
    case: InvestmentCase, revision: CaseRevision, request: ReviewRequest, previous: CaseReview | None
) -> CaseReview:
    principal = security.require(case.company_id)
    if request.mode == "human":
        from ..approvals import can_approve

        if not can_approve(principal, case.company_id, "approver"):
            raise security.deny(
                "Actual case review requires a human approver with pvc.approve", "case_review_authority"
            )
    else:
        writer(case.company_id)
    if request.expected_revision_sha256 != revision.content_sha256:
        raise ValueError("review must bind the exact stored revision hash")
    if previous is not None:
        if (
            previous.revision_id != revision.revision_id
            or previous.case_id != case.case_id
            or previous.mode != request.mode
        ):
            raise ValueError("review correction must refer to the same revision, case and review mode")
        if previous.actor != principal.subject:
            raise security.deny("Only the original reviewer can correct their receipt", "case_review_authority")
    if request.decision == "withdraw" and previous is None:
        raise ValueError("withdrawal requires a prior receipt")
    return CaseReview(
        review_id=str(uuid.uuid4()),
        case_id=case.case_id,
        company_id=case.company_id,
        revision_id=revision.revision_id,
        revision_sha256=revision.content_sha256,
        mode=request.mode,
        decision=request.decision,
        rationale=request.rationale,
        actor=principal.subject,
        actor_type=principal.principal_type,
        recorded_at=datetime.now(UTC),
        supersedes_review_id=request.supersedes_review_id,
    )


def compare_revisions(original: CaseRevision, current: CaseRevision) -> dict[str, Any]:
    if original.case_id != current.case_id or original.company_id != current.company_id:
        raise ValueError("cannot compare revisions across cases or companies")
    before = json.loads(original.financial_result_json)
    after = json.loads(current.financial_result_json)
    return {
        "case_id": original.case_id,
        "original_revision_id": original.revision_id,
        "current_revision_id": current.revision_id,
        "original_hash": original.content_sha256,
        "current_hash": current.content_sha256,
        "original_financials": before,
        "current_financials": after,
        "measurement_state": "modeled_only",
        "actuals": None,
        "actuals_unavailable_reason": "No observed operating or accounting actuals are attached; modeled change is not realized value.",
        "authority": "Research-case review is separate from operating authorization and KPI activation. Simulation receipts cannot confer human acceptance.",
    }
