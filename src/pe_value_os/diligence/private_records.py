"""Private source custody and exact-version finance review; never a public case."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .. import security
from .models import Record
from .private_grants import GrantEvent, require_processing_permission, validate_key
from .private_intake import (
    MAX_BYTES,
    SHA,
    IntakeManifest,
    IntakePolicy,
    IntakeReport,
    assess_intake,
    fingerprint,
    require_operator,
)
from .record_chain import content_hash, seal, verify_link

KEY = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class IntakeRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    grant_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    expected_grant_sha256: SHA
    expected_previous_sha256: SHA | None
    policy: IntakePolicy
    manifest: IntakeManifest
    rationale: str = Field(min_length=1)


class PrivateIntake(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    intake_id: str = Field(pattern=UUID)
    company_id: str
    dataset_key: str
    sequence: int = Field(ge=1)
    request: IntakeRequest
    grant_event_id: str = Field(pattern=UUID)
    source_sha256: SHA
    source_size: int = Field(ge=1, le=MAX_BYTES)
    preflight: IntakeReport
    actor: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    content_sha256: SHA

    def require_public(self) -> None:
        raise ValueError("private source receipts cannot be exported as public exhibits")

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.dataset_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private intake hash mismatch")
        if any(
            self.company_id != company
            for company in (self.request.policy.company_id, self.request.manifest.company_id, self.preflight.company_id)
        ):
            raise ValueError("private intake company mismatch")
        if self.source_sha256 != self.preflight.source_sha256 or self.recorded_at != self.preflight.assessed_at:
            raise ValueError("private intake source or assessment binding mismatch")
        if self.preflight.policy_sha256 != fingerprint(
            self.request.policy
        ) or self.preflight.manifest_sha256 != fingerprint(self.request.manifest):
            raise ValueError("private intake policy or manifest binding mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private intake sequence requires its predecessor")
        return self


class FinanceReviewRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_intake_sha256: SHA
    expected_grant_sha256: SHA
    expected_previous_sha256: SHA | None
    decision: Literal["accept", "reject", "request_changes", "withdraw"]
    rationale: str = Field(min_length=1)
    review_evidence_reference: str = Field(min_length=1)
    review_evidence_sha256: SHA


class FinanceReview(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    review_id: str = Field(pattern=UUID)
    company_id: str
    intake_id: str = Field(pattern=UUID)
    sequence: int = Field(ge=1)
    request: FinanceReviewRequest
    grant_event_id: str = Field(pattern=UUID)
    actor: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    content_sha256: SHA

    def require_public(self) -> None:
        raise ValueError("private finance decisions cannot be exported as public exhibits")

    @model_validator(mode="after")
    def integrity(self) -> Self:
        verify_link(self, "private finance review hash mismatch", "private review sequence requires its predecessor")
        return self


def require_intake_writer(company_id: str) -> security.Principal:
    principal = require_operator(company_id)
    if not principal.has_scope(security.WRITE_SCOPE):
        raise security.deny("Private intake requires pvc.write", "private_intake_write")
    return principal


def require_finance_reviewer(company_id: str) -> security.Principal:
    from ..approvals import can_approve

    principal = require_operator(company_id)
    if not can_approve(principal, company_id, "finance_reviewer"):
        raise security.deny("Private acceptance requires a human finance reviewer", "private_finance_review")
    return principal


def prepare_intake(
    company_id: str,
    dataset_key: str,
    request: IntakeRequest,
    raw: bytes,
    grants: list[GrantEvent],
    previous: PrivateIntake | None,
    environment_id: str,
) -> PrivateIntake:
    principal = require_intake_writer(company_id)
    request = IntakeRequest.model_validate(request.model_dump(mode="json"))
    validate_key(dataset_key)
    if request.policy.company_id != company_id or request.manifest.company_id != company_id:
        raise ValueError("private intake header belongs to another company")
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("private source size is outside the custody limit")
    now = datetime.now(UTC)
    grant = require_processing_permission(grants, request.policy, environment_id, now=now)
    if request.expected_grant_sha256 != grant.content_sha256 or grant.grant_key != request.grant_key:
        raise ValueError("intake requires the exact current grant")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("intake correction requires the current dataset head")
    if previous and (previous.company_id != company_id or previous.dataset_key != dataset_key):
        raise ValueError("intake correction mixes datasets")
    if previous and previous.recorded_at > now:
        raise ValueError("intake correction predates its parent")
    report = assess_intake(request.policy, request.manifest, raw, now=now)
    payload: dict[str, Any] = dict(
        intake_id=str(uuid.uuid4()),
        company_id=company_id,
        dataset_key=dataset_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        grant_event_id=grant.event_id,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_size=len(raw),
        preflight=report,
        actor=principal.subject,
        recorded_at=now,
    )
    return seal(PrivateIntake, payload)


def verify_source(record: PrivateIntake, raw: bytes) -> None:
    if content_hash(record) != record.content_sha256:
        raise ValueError("private intake content changed")
    if hashlib.sha256(raw).hexdigest() != record.source_sha256 or len(raw) != record.source_size:
        raise ValueError("stored private source no longer matches its intake")
    reproduced = assess_intake(record.request.policy, record.request.manifest, raw, now=record.recorded_at)
    if reproduced != record.preflight:
        raise ValueError("stored private preflight cannot be reproduced")


def prepare_review(
    record: PrivateIntake,
    raw: bytes,
    request: FinanceReviewRequest,
    grants: list[GrantEvent],
    previous: FinanceReview | None,
    environment_id: str,
) -> FinanceReview:
    principal = require_finance_reviewer(record.company_id)
    request = FinanceReviewRequest.model_validate(request.model_dump(mode="json"))
    now = datetime.now(UTC)
    grant = require_processing_permission(grants, record.request.policy, environment_id, now=now)
    if request.expected_grant_sha256 != grant.content_sha256 or grant.grant_key != record.request.grant_key:
        raise ValueError("finance review requires the exact current grant")
    if request.expected_intake_sha256 != record.content_sha256:
        raise ValueError("finance review requires the exact intake version")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("finance review requires the current review head")
    if previous and (previous.company_id != record.company_id or previous.intake_id != record.intake_id):
        raise ValueError("finance review mixes intake streams")
    if record.recorded_at > now or (previous and previous.recorded_at > now):
        raise ValueError("finance review predates its source or parent")
    if request.decision == "withdraw" and previous is None:
        raise ValueError("finance withdrawal requires a previous review")
    verify_source(record, raw)
    if request.decision == "accept" and record.preflight.status != "ready_for_finance_review":
        raise ValueError("quarantined source cannot be accepted")
    payload: dict[str, Any] = dict(
        review_id=str(uuid.uuid4()),
        company_id=record.company_id,
        intake_id=record.intake_id,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        grant_event_id=grant.event_id,
        actor=principal.subject,
        recorded_at=now,
    )
    return seal(FinanceReview, payload)


def authorize_source(
    record: PrivateIntake,
    raw: bytes,
    grants: list[GrantEvent],
    reviews: list[FinanceReview],
    current: PrivateIntake,
    environment_id: str,
    *,
    accepted_only: bool,
) -> bytes:
    """Called under the same repository lock as grant, intake and review mutations."""
    require_operator(record.company_id)
    grant = require_processing_permission(grants, record.request.policy, environment_id, now=datetime.now(UTC))
    if grant.grant_key != record.request.grant_key:
        raise ValueError("source permission belongs to another grant stream")
    if accepted_only:
        if current.content_sha256 != record.content_sha256:
            raise ValueError("superseded intake cannot supply accepted data")
        if not reviews or reviews[-1].request.decision != "accept":
            raise ValueError("source requires current finance acceptance")
        review = FinanceReview.model_validate(reviews[-1].model_dump(mode="json"))
        if (
            review.company_id != record.company_id
            or review.intake_id != record.intake_id
            or review.request.expected_intake_sha256 != record.content_sha256
        ):
            raise ValueError("finance acceptance belongs to another intake")
        if record.preflight.status != "ready_for_finance_review":
            raise ValueError("quarantined source cannot supply accepted data")
    verify_source(record, raw)
    return raw
