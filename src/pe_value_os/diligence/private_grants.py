"""Human processing grants and revocations, separate from finance or operating approval."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .. import security
from .models import Record
from .private_intake import SHA, IntakePolicy, fingerprint, require_operator


class GrantRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    action: Literal["grant", "revoke"]
    expected_previous_sha256: SHA | None
    policy: IntakePolicy | None = None
    operator_subjects: tuple[str, ...] = Field(default=(), max_length=100)
    environment_id: str | None = Field(default=None, min_length=1)
    rationale: str = Field(min_length=1)
    authority_attestation: str = Field(min_length=1)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.action == "grant") != (self.policy is not None):
            raise ValueError("grant requires a policy; revocation must not replace the policy")
        if self.action == "revoke" and self.expected_previous_sha256 is None:
            raise ValueError("revocation requires the exact existing grant head")
        if self.action == "grant":
            if not self.operator_subjects or self.environment_id is None:
                raise ValueError("grant must name permitted operators and one processing environment")
            if len(set(self.operator_subjects)) != len(self.operator_subjects) or any(
                not subject or subject.strip() != subject for subject in self.operator_subjects
            ):
                raise ValueError("operator subjects must be unique nonempty identities")
        elif self.operator_subjects or self.environment_id is not None:
            raise ValueError("revocation cannot assign new operators or an environment")
        return self


class GrantEvent(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    event_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    company_id: str
    grant_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    sequence: int = Field(ge=1)
    request: GrantRequest
    actor: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    content_sha256: SHA

    @model_validator(mode="after")
    def identity(self) -> Self:
        security.validate_company_id(self.company_id)
        if event_hash(self) != self.content_sha256:
            raise ValueError("private grant content hash mismatch")
        if self.request.policy is not None and self.request.policy.company_id != self.company_id:
            raise ValueError("private grant policy belongs to another company")
        return self


def event_hash(event: GrantEvent) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(event.model_dump(mode="json", exclude={"content_sha256"}), sort_keys=True).encode()
    ).hexdigest()


def require_reader(company_id: str) -> security.Principal:
    principal = security.require(company_id)
    if not principal.is_human or not principal.has_scope("pvc.read"):
        raise security.deny("Private grants require scoped human read access", "private_grant_read")
    return principal


def require_author(company_id: str) -> security.Principal:
    from ..approvals import can_approve

    principal = require_reader(company_id)
    if not can_approve(principal, company_id, "data_owner"):
        raise security.deny("Processing authority requires a human data owner", "private_grant_authority")
    return principal


def validate_key(grant_key: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", grant_key):
        raise ValueError("invalid private grant key")


def prepare_event(company_id: str, grant_key: str, request: GrantRequest, previous: GrantEvent | None) -> GrantEvent:
    principal = require_author(company_id)
    request = GrantRequest.model_validate(request.model_dump(mode="json"))
    validate_key(grant_key)
    now = datetime.now(UTC)
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("private grant requires the current head")
    if previous is not None:
        if previous.company_id != company_id or previous.grant_key != grant_key:
            raise ValueError("private grant stream scope mismatch")
        if previous.recorded_at > now:
            raise ValueError("private grant time cannot move backward")
    if request.action == "revoke" and (previous is None or previous.request.action != "grant"):
        raise ValueError("only a granted scope can be revoked")
    if request.policy is not None:
        if request.policy.company_id != company_id or now >= request.policy.expires_at:
            raise ValueError("private grant policy is foreign or already expired")
    raw: dict[str, Any] = dict(
        event_id=str(uuid.uuid4()),
        company_id=company_id,
        grant_key=grant_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        actor=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    draft = GrantEvent.model_construct(**raw)
    raw["content_sha256"] = event_hash(draft)
    return GrantEvent.model_validate(raw)


def permission_status(events: list[GrantEvent], policy_sha256: str, *, now: datetime) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("permission assessment requires an aware time")
    previous = None
    for index, event in enumerate(events, start=1):
        if event_hash(event) != event.content_sha256:
            raise ValueError("private grant content hash mismatch")
        if event.sequence != index or event.request.expected_previous_sha256 != (
            previous.content_sha256 if previous else None
        ):
            raise ValueError("private grant history is incomplete or reordered")
        if previous and (event.company_id, event.grant_key) != (previous.company_id, previous.grant_key):
            raise ValueError("private grant history mixes scopes")
        previous = event
    latest = previous
    policy = latest.request.policy if latest else None
    reason = "no_grant"
    if latest:
        if latest.recorded_at > now:
            reason = "not_yet_recorded"
        elif latest.request.action == "revoke":
            reason = "revoked"
        elif policy is not None:
            if fingerprint(policy) != policy_sha256:
                reason = "policy_mismatch"
            elif not policy.valid_from <= now < policy.expires_at or now >= policy.retain_until:
                reason = "outside_processing_window"
            else:
                reason = "active_human_grant"
    return {
        "classification": "permissioned_private",
        "processing_grant_active": reason == "active_human_grant",
        "reason": reason,
        "event_id": latest.event_id if latest else None,
        "event_sha256": latest.content_sha256 if latest else None,
        "policy_sha256": fingerprint(policy) if policy else None,
        "operator_subjects": latest.request.operator_subjects if policy and latest else (),
        "environment_id": latest.request.environment_id if policy and latest else None,
        "basis": "recorded_human_data_owner_attestation",
        "legal_authority_independently_verified": False,
        "finance_reviewed": False,
        "data_admitted": False,
        "operating_action_authorized": False,
    }


def require_processing_permission(
    events: list[GrantEvent], policy: IntakePolicy, environment_id: str, *, now: datetime
) -> GrantEvent:
    """Check a supplied current stream; intake must load it under its own transaction.

    This does not ingest data or turn a cached history into a current decision.
    """
    principal = require_operator(policy.company_id)
    status = permission_status(events, fingerprint(policy), now=now)
    if not status["processing_grant_active"]:
        raise security.deny("No active grant for this exact policy", "private_processing_grant")
    latest = events[-1]
    if (
        latest.company_id != policy.company_id
        or principal.subject not in latest.request.operator_subjects
        or environment_id != latest.request.environment_id
    ):
        raise security.deny("Operator or environment is outside the processing grant", "private_processing_grant")
    return latest
