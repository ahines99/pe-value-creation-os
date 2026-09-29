"""Versioned private financial inputs from accepted sources, never constructed cases."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .. import security
from .models import Record
from .private_grants import GrantEvent, require_processing_permission, validate_key
from .private_intake import SHA, Control, Ledger, parse_private
from .private_records import (
    KEY,
    UUID,
    FinanceReview,
    PrivateIntake,
    authorize_source,
    content_hash,
    require_finance_reviewer,
    require_intake_writer,
    verify_source,
)
from .realization import COMPONENTS, ENTRY_COMPONENT
from .underwriting import Entry, month_end, month_start, totals


class FinancialDefinition(Record):
    accounting_basis: Literal["US_GAAP", "IFRS", "management_accounts"]
    earnings_basis: Literal["revenue_and_operating_expense_excluding_interest_tax_da"]
    cash_basis: Literal["disjoint_operating_working_capital_and_capex_flows"]
    evidence_reference: str = Field(min_length=1)
    evidence_sha256: SHA
    reviewer_attestation: str = Field(min_length=1)


class FinancialSnapshotRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    intake_id: str = Field(pattern=UUID)
    expected_intake_sha256: SHA
    expected_finance_review_sha256: SHA
    expected_grant_sha256: SHA
    purpose: Literal["baseline_candidate", "observed_actuals"]
    definition: FinancialDefinition
    rationale: str = Field(min_length=1)


class FinancialAmounts(Record):
    mapped_ebitda: Decimal
    recurring_operating_contribution: Decimal
    operating_accrual_to_cash_difference: Decimal
    pre_tax_cash_proxy: Decimal


class PrivateMonth(Record):
    start: date
    end: date
    components: tuple[Control, ...]
    amounts: FinancialAmounts


class PrivateFinancialSnapshot(Record):
    schema_version: Literal[1] = 1
    calculation_version: Literal["private-monthly-financials/1"] = "private-monthly-financials/1"
    classification: Literal["permissioned_private"] = "permissioned_private"
    snapshot_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    sequence: int = Field(ge=1)
    request: FinancialSnapshotRequest
    entity_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1] = 1
    origin: Literal["synthetic_test_fixture", "company_export"]
    dataset_key: str
    source_sha256: SHA
    policy_sha256: SHA
    finance_review_id: str = Field(pattern=UUID)
    grant_event_id: str = Field(pattern=UUID)
    monthly: tuple[PrivateMonth, ...] = Field(min_length=1, max_length=24)
    period_totals: FinancialAmounts
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    frozen_comparison_baseline: Literal[False] = False
    causal_value_claim: Literal[False] = False
    operating_action_authorized: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if content_hash(self) != self.content_sha256:
            raise ValueError("private financial snapshot hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private financial history requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private financial snapshots cannot be exported as public exhibits")


def require_snapshot_writer(company_id: str) -> security.Principal:
    # Source acceptance does not independently review a new accounting definition.
    # The person signing the snapshot must have both processing and finance rights.
    principal = require_finance_reviewer(company_id)
    require_intake_writer(company_id)
    return principal


def amounts(entries: tuple[Entry, ...], start: date, end: date) -> FinancialAmounts:
    # Reuse the neutral Decimal earnings/cash identities, not a constructed input
    # contract or the underwriting evaluator's constructed-only authorization.
    calculated = totals(entries, start, end)
    return FinancialAmounts(
        mapped_ebitda=calculated["incremental_ebitda"],
        recurring_operating_contribution=calculated["recurring_contribution"],
        operating_accrual_to_cash_difference=calculated["operating_accrual_to_cash"],
        pre_tax_cash_proxy=calculated["pre_tax_cash_proxy"],
    )


def calculate(record: PrivateIntake, raw: bytes) -> tuple[tuple[PrivateMonth, ...], FinancialAmounts]:
    ledger = parse_private(Ledger, raw)
    policy = record.request.policy
    mappings = {m.account_code: m for m in policy.mappings}
    with localcontext() as ctx:
        ctx.prec = 40
        entries = tuple(
            Entry(
                day=row.period,
                initiative_id="unattributed-private-ledger",
                component=ENTRY_COMPONENT[mappings[row.account_code].component],
                amount=row.amount * mappings[row.account_code].multiplier,
                reference=row.source_row_id,
            )
            for row in ledger.rows
        )
        months = []
        for offset in range(policy.months):
            start = month_start(policy.first_month, offset)
            end = month_end(start)
            components = tuple(
                Control(
                    period=start,
                    component=component,
                    amount=sum(
                        (e.amount for e in entries if e.day == start and e.component == ENTRY_COMPONENT[component]),
                        Decimal(0),
                    ),
                )
                for component in COMPONENTS
            )
            controls = {c.component: c.amount for c in policy.controls if c.period == start}
            if any(c.amount != controls[c.component] for c in components):
                raise ValueError("private financial components do not reconcile to source controls")
            months.append(
                PrivateMonth(start=start, end=end, components=components, amounts=amounts(entries, start, end))
            )
        return tuple(months), amounts(entries, policy.first_month, month_end(policy.first_month, policy.months - 1))


def prepare_snapshot(
    company_id: str,
    case_key: str,
    request: FinancialSnapshotRequest,
    record: PrivateIntake,
    raw: bytes,
    grants: list[GrantEvent],
    reviews: list[FinanceReview],
    current: PrivateIntake,
    previous: PrivateFinancialSnapshot | None,
    environment_id: str,
) -> PrivateFinancialSnapshot:
    principal = require_snapshot_writer(company_id)
    request = FinancialSnapshotRequest.model_validate(request.model_dump(mode="json"))
    validate_key(case_key)
    if record.company_id != company_id or record.intake_id != request.intake_id:
        raise ValueError("private financial source belongs to another company or intake")
    authorize_source(record, raw, grants, reviews, current, environment_id, accepted_only=True)
    now = datetime.now(UTC)
    grant = require_processing_permission(grants, record.request.policy, environment_id, now=now)
    review = reviews[-1]
    if (record.content_sha256, review.content_sha256, grant.content_sha256) != (
        request.expected_intake_sha256,
        request.expected_finance_review_sha256,
        request.expected_grant_sha256,
    ):
        raise ValueError("private financial snapshot requires exact current intake, finance and grant hashes")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("private financial snapshot requires the current case head")
    policy = record.request.policy
    if previous and (
        (previous.company_id, previous.case_key, previous.entity_id, previous.currency, previous.origin)
        != (company_id, case_key, policy.entity_id, policy.currency, record.request.manifest.origin)
        or previous.recorded_at > now
    ):
        raise ValueError("private financial history cannot mix case, entity, currency, origin or chronology")
    if review.recorded_at > now:
        raise ValueError("private financial snapshot predates finance acceptance")
    monthly, total = calculate(record, raw)
    payload: dict[str, Any] = dict(
        snapshot_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        entity_id=policy.entity_id,
        currency=policy.currency,
        origin=record.request.manifest.origin,
        dataset_key=record.dataset_key,
        source_sha256=record.source_sha256,
        policy_sha256=record.preflight.policy_sha256,
        finance_review_id=review.review_id,
        grant_event_id=grant.event_id,
        monthly=monthly,
        period_totals=total,
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateFinancialSnapshot.model_construct(**payload))
    return PrivateFinancialSnapshot.model_validate(payload)


def verify_snapshot(snapshot: PrivateFinancialSnapshot, record: PrivateIntake, raw: bytes) -> None:
    PrivateFinancialSnapshot.model_validate(snapshot.model_dump(mode="json"))
    verify_source(record, raw)
    policy = record.request.policy
    if (snapshot.entity_id, snapshot.currency, snapshot.origin, snapshot.dataset_key) != (
        policy.entity_id,
        policy.currency,
        record.request.manifest.origin,
        record.dataset_key,
    ):
        raise ValueError("private financial snapshot changed its source scope")
    if (
        snapshot.company_id,
        snapshot.request.intake_id,
        snapshot.request.expected_intake_sha256,
        snapshot.source_sha256,
        snapshot.policy_sha256,
    ) != (
        record.company_id,
        record.intake_id,
        record.content_sha256,
        record.source_sha256,
        record.preflight.policy_sha256,
    ):
        raise ValueError("private financial snapshot source binding changed")
    monthly, total = calculate(record, raw)
    if snapshot.monthly != monthly or snapshot.period_totals != total:
        raise ValueError("private financial snapshot does not reproduce from its source")


def require_current_snapshot(
    snapshot: PrivateFinancialSnapshot,
    record: PrivateIntake,
    raw: bytes,
    grants: list[GrantEvent],
    reviews: list[FinanceReview],
    current: PrivateIntake,
    environment_id: str,
) -> None:
    """Recheck all source authority while the repository holds the company lock."""
    authorize_source(record, raw, grants, reviews, current, environment_id, accepted_only=True)
    grant = require_processing_permission(grants, record.request.policy, environment_id, now=datetime.now(UTC))
    if (
        snapshot.request.expected_finance_review_sha256 != reviews[-1].content_sha256
        or snapshot.request.expected_grant_sha256 != grant.content_sha256
    ):
        raise ValueError("private financial snapshot authority changed; prepare a new version")
    verify_snapshot(snapshot, record, raw)
