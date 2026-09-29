"""Private ledger preflight: source conformance is not authorization or admission.

No input enters the constructed-case store, a model, or a public renderer. A
referenced authorization document still needs verification by the actual parties.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Annotated, Literal, Self, TypeVar

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .. import security
from .models import Record
from .realization import COMPONENTS, Component
from .underwriting import month_end, month_start

MAX_BYTES = 10 * 1024 * 1024
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Amount = Annotated[Decimal, Field(max_digits=24, decimal_places=2)]
R = TypeVar("R", bound=Record)


def parse_private(model: type[R], raw: bytes) -> R:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    return model.model_validate(json.loads(raw, object_pairs_hook=unique_object))


def fingerprint(record: Record) -> str:
    return hashlib.sha256(json.dumps(record.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class AccountMapping(Record):
    account_code: str = Field(min_length=1)
    component: Component
    multiplier: Literal[-1, 1]

    @field_validator("multiplier", mode="before")
    @classmethod
    def explicit_sign(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("mapping sign must be an explicit integer")
        return value


class Control(Record):
    period: date
    component: Component
    amount: Amount

    @field_validator("amount", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("amount requires a decimal string or integer")
        return value


class IntakePolicy(Record):
    schema_version: Literal[1] = 1
    company_id: str
    entity_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1]
    first_month: date
    months: int = Field(ge=1, le=24, strict=True)
    purpose: str = Field(min_length=1)
    authorization_reference: str = Field(min_length=1)
    authorization_sha256: SHA
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    retain_until: AwareDatetime
    control_source_reference: str = Field(min_length=1)
    control_source_sha256: SHA
    mappings: tuple[AccountMapping, ...] = Field(min_length=1)
    controls: tuple[Control, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def scope(self) -> Self:
        security.validate_company_id(self.company_id)
        if self.first_month.day != 1:
            raise ValueError("scope starts at a calendar month boundary")
        if not self.valid_from < self.expires_at <= self.retain_until:
            raise ValueError("processing and retention dates do not reconcile")
        if len({m.account_code for m in self.mappings}) != len(self.mappings):
            raise ValueError("each account needs exactly one mapping")
        if {m.component for m in self.mappings} != set(COMPONENTS):
            raise ValueError("map every component, including known zeros")
        expected = {(month_start(self.first_month, n), c) for n in range(self.months) for c in COMPONENTS}
        keys = [(c.period, c.component) for c in self.controls]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError("one independent control per month and component is required")
        return self


class IntakeManifest(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"]
    origin: Literal["synthetic_test_fixture", "company_export"]
    company_id: str
    export_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    extraction_reference: str = Field(min_length=1)
    extracted_at: AwareDatetime
    data_cutoff: date
    source_sha256: SHA
    policy_sha256: SHA
    record_count: int = Field(ge=1, le=100000, strict=True)


class LedgerRow(Record):
    source_row_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    period: date
    account_code: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Amount

    @field_validator("amount", mode="before")
    @classmethod
    def exact(cls, value: object) -> object:
        return Control.exact(value)


class Ledger(Record):
    schema_version: Literal[1] = 1
    rows: tuple[LedgerRow, ...] = Field(min_length=1, max_length=100000)


class IntakeIssue(Record):
    code: str
    # Ordinals refer to the immutable source file; no private cell values in errors.
    row_numbers: tuple[int, ...] = ()


class ControlResult(Record):
    period: date
    component: Component
    expected: Decimal
    observed: Decimal
    difference: Decimal
    source_rows: int


class IntakeReport(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    company_id: str
    origin: Literal["synthetic_test_fixture", "company_export"]
    assessed_at: AwareDatetime
    source_sha256: SHA
    policy_sha256: SHA
    manifest_sha256: SHA
    status: Literal["quarantined", "ready_for_finance_review"]
    issues: tuple[IntakeIssue, ...]
    controls: tuple[ControlResult, ...]
    authorization_verified: Literal[False] = False
    finance_reviewed: Literal[False] = False
    data_admitted: Literal[False] = False
    operating_action_authorized: Literal[False] = False

    def require_public(self) -> None:
        raise ValueError("private intake reports cannot be exported as public exhibits")


def require_operator(company_id: str) -> security.Principal:
    principal = security.require(company_id)
    if not principal.is_human or "operator" not in principal.roles or not principal.has_scope("pvc.read"):
        raise security.deny("Private preflight requires a scoped human operator", "private_intake")
    return principal


def header_issues(policy: IntakePolicy, manifest: IntakeManifest, now: datetime) -> list[IntakeIssue]:
    if now.tzinfo is None:
        raise ValueError("assessment time must be timezone-aware")
    now = now.astimezone(UTC)
    issues = []
    checks = (
        (manifest.company_id == policy.company_id, "company_scope_mismatch"),
        (manifest.policy_sha256 == fingerprint(policy), "policy_fingerprint_mismatch"),
        (policy.valid_from <= now < policy.expires_at, "outside_processing_window"),
        (now < policy.retain_until, "retention_expired"),
        (policy.valid_from <= manifest.extracted_at <= now, "extraction_outside_processing_window"),
        (
            manifest.data_cutoff == month_end(policy.first_month, policy.months - 1)
            and manifest.extracted_at.astimezone(UTC).date() >= manifest.data_cutoff,
            "cutoff_mismatch",
        ),
    )
    for passed, code in checks:
        if not passed:
            issues.append(IntakeIssue(code=code))
    return issues


def assess_intake(policy: IntakePolicy, manifest: IntakeManifest, raw: bytes, *, now: datetime) -> IntakeReport:
    require_operator(policy.company_id)
    issues = header_issues(policy, manifest, now)
    now = now.astimezone(UTC)
    results: list[ControlResult] = []

    def issue(code: str, *rows: int) -> None:
        issues.append(IntakeIssue(code=code, row_numbers=rows))

    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != manifest.source_sha256:
        issue("source_fingerprint_mismatch")
    if len(raw) > MAX_BYTES:
        issue("source_size_limit")

    # Do not parse a file with failed identity, scope, processing or size checks.
    if not issues:
        try:
            ledger = parse_private(Ledger, raw)
        except ValueError:
            issue("invalid_ledger_schema")
        else:
            if len(ledger.rows) != manifest.record_count:
                issue("record_count_mismatch")
            mappings = {m.account_code: m for m in policy.mappings}
            totals = {(c.period, c.component): Decimal(0) for c in policy.controls}
            counts = dict.fromkeys(totals, 0)
            identities: dict[str, int] = {}
            for index, row in enumerate(ledger.rows, start=1):
                if row.source_row_id in identities:
                    issue("duplicate_source_row", identities[row.source_row_id], index)
                    continue
                identities[row.source_row_id] = index
                if row.entity_id != policy.entity_id or row.currency != policy.currency:
                    issue("row_scope_mismatch", index)
                    continue
                mapping = mappings.get(row.account_code)
                if mapping is None:
                    issue("unmapped_account", index)
                    continue
                key = (row.period, mapping.component)
                if key not in totals:
                    issue("row_period_outside_scope", index)
                    continue
                # Maximum 100,000 rows of at most 24 digits; keep cents even
                # when large debit/credit balances cancel late in the file.
                with localcontext() as context:
                    context.prec = 40
                    totals[key] += row.amount * mapping.multiplier
                counts[key] += 1
            for control in policy.controls:
                key = (control.period, control.component)
                observed = totals[key]
                with localcontext() as context:
                    context.prec = 40
                    difference = observed - control.amount
                results.append(
                    ControlResult(
                        period=control.period,
                        component=control.component,
                        expected=control.amount,
                        observed=observed,
                        difference=difference,
                        source_rows=counts[key],
                    )
                )
                if not counts[key]:
                    issue("missing_component_rows")
                if observed != control.amount:
                    issue("control_total_mismatch")

    return IntakeReport(
        company_id=policy.company_id,
        origin=manifest.origin,
        assessed_at=now,
        source_sha256=actual_hash,
        policy_sha256=fingerprint(policy),
        manifest_sha256=fingerprint(manifest),
        status="quarantined" if issues else "ready_for_finance_review",
        issues=tuple(issues),
        controls=tuple(results),
    )


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds private preflight size limit")
    return raw


def check_files(policy_path: Path, manifest_path: Path, ledger_path: Path, name: str) -> IntakeReport:
    """Local operator entry point. Writes one private receipt, never source records."""
    policy = parse_private(IntakePolicy, read_bounded(policy_path))
    # Require scope before opening the operating ledger or preparing output paths.
    require_operator(policy.company_id)
    manifest = parse_private(IntakeManifest, read_bounded(manifest_path))
    now = datetime.now(UTC)
    if header_issues(policy, manifest, now):
        raise ValueError("private header checks failed before opening the ledger")
    raw = read_bounded(ledger_path)
    report = assess_intake(policy, manifest, raw, now=now)
    root = Path.cwd().resolve() / "var" / "permissioned-pilot"
    if root.resolve() != root:
        raise ValueError("private output root cannot redirect through a symbolic link")
    destination = (root / f"{name}.json").resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ValueError("private output must stay within var/permissioned-pilot")
    if destination in {p.resolve() for p in (policy_path, manifest_path, ledger_path)}:
        raise ValueError("report must not overwrite its input")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create preserves old review receipts; choose another name to rerun.
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(report.model_dump_json(indent=2) + "\n")
    return report
