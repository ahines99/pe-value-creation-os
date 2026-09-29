"""Private forecasts anchored to accepted financials, with explicit authored judgments.

Repositories must load a currently usable snapshot under the company lock before
calling these functions. A documentary citation is not independent verification
of eligibility, feasibility, maintainability, or authority to operate.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .models import Record, SourceClass
from .private_financials import PrivateFinancialSnapshot
from .private_grants import validate_key
from .private_intake import SHA
from .private_records import KEY, UUID, content_hash, require_intake_writer
from .realization import Component
from .underwriting import EvidenceRef, Scenario, scenario_report, single_pool_ledger, validate_inputs


class PrivateEvidence(EvidenceRef):
    classification: Literal[SourceClass.PERMISSIONED_PRIVATE] = SourceClass.PERMISSIONED_PRIVATE
    sha256: SHA


class Basis(Record):
    scenario_id: Literal["downside", "base", "upside"]
    assumption_id: str = Field(min_length=1)


class FinancialBasis(Basis):
    kind: Literal["financial_component"] = "financial_component"
    month: date
    component: Component
    transform: Literal["identity", "absolute"]


class JudgmentBasis(Basis):
    kind: Literal["operator_judgment"] = "operator_judgment"
    rationale: str = Field(min_length=1)


AssumptionBasis = Annotated[FinancialBasis | JudgmentBasis, Field(discriminator="kind")]


class InitiativeBasis(Record):
    initiative_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    eligibility_rationale: str = Field(min_length=1)
    constraints: str = Field(min_length=1)
    falsification_test: str = Field(min_length=1)


class PrivateUnderwritingInputs(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    case_key: str = Field(pattern=KEY)
    company_id: str
    entity_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    financial_snapshot_id: str = Field(pattern=UUID)
    financial_snapshot_sha256: SHA
    start: date
    months: Literal[24] = 24
    evidence: tuple[PrivateEvidence, ...]
    scenarios: tuple[Scenario, ...]
    assumption_bases: tuple[AssumptionBasis, ...]
    initiative_bases: tuple[InitiativeBasis, ...]
    selected_initiatives: tuple[str, ...]
    selection_rationale: str = Field(min_length=1)
    multiples: tuple[Decimal, ...] = Field(min_length=1)
    multiple_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_inputs(
            self.start,
            self.months,
            self.multiples,
            self.evidence,
            self.scenarios,
            1,
            SourceClass.PERMISSIONED_PRIVATE,
        )
        values = (*self.multiples, *(a.value for s in self.scenarios for a in s.assumptions))
        for value in values:
            exponent = value.as_tuple().exponent
            if (
                not isinstance(exponent, int)
                or len(value.as_tuple().digits) > 24
                or value.adjusted() > 23
                or exponent < -12
            ):
                raise ValueError("private forecast values support at most 24 digits and 12 decimal places")
        keys = {(s.scenario_id, a.assumption_id) for s in self.scenarios for a in s.assumptions}
        bases = {(b.scenario_id, b.assumption_id) for b in self.assumption_bases}
        if bases != keys or len(bases) != len(self.assumption_bases):
            raise ValueError("each scenario assumption requires exactly one explicit basis")
        ids = {d.initiative_id for d in self.scenarios[0].drivers}
        if set(self.selected_initiatives) - ids or len(set(self.selected_initiatives)) != len(
            self.selected_initiatives
        ):
            raise ValueError("private selection contains duplicate or unknown initiatives")
        if {b.initiative_id for b in self.initiative_bases} != ids or len(self.initiative_bases) != len(ids):
            raise ValueError("each initiative requires its eligibility, constraints and falsification basis")
        evidence_ids = {e.evidence_id for e in self.evidence}
        if any(not set(b.evidence_ids) <= evidence_ids for b in self.initiative_bases):
            raise ValueError("initiative references unknown evidence")
        return self

    def require_public(self) -> None:
        raise ValueError("private underwriting cannot be exported as public exhibits")

    def bind(self, snapshot: PrivateFinancialSnapshot) -> None:
        PrivateFinancialSnapshot.model_validate(snapshot.model_dump(mode="json"))
        if (
            self.company_id,
            self.case_key,
            self.entity_id,
            self.currency,
            self.financial_snapshot_id,
            self.financial_snapshot_sha256,
        ) != (
            snapshot.company_id,
            snapshot.case_key,
            snapshot.entity_id,
            snapshot.currency,
            snapshot.snapshot_id,
            snapshot.content_sha256,
        ):
            raise ValueError("private underwriting requires its exact financial snapshot and scope")
        if snapshot.request.purpose != "baseline_candidate":
            raise ValueError("private underwriting requires baseline-candidate financials")
        if self.start <= snapshot.monthly[-1].end:
            raise ValueError("forecast must start after the historical financial period")
        controls = {(c.period, c.component): c.amount for month in snapshot.monthly for c in month.components}
        assumptions = {(s.scenario_id, a.assumption_id): a for s in self.scenarios for a in s.assumptions}
        for basis in self.assumption_bases:
            if isinstance(basis, FinancialBasis):
                key = (basis.month, basis.component)
                if key not in controls:
                    raise ValueError("financial assumption references an unavailable month or component")
                value = controls[key] if basis.transform == "identity" else controls[key].copy_abs()
                assumption = assumptions[(basis.scenario_id, basis.assumption_id)]
                if assumption.unit != "currency" or assumption.value != value:
                    raise ValueError("financial assumption must equal its explicitly mapped component")


class UnderwritingRequest(Record):
    schema_version: Literal[1] = 1
    idempotency_key: str = Field(pattern=KEY)
    expected_previous_sha256: SHA | None
    inputs: PrivateUnderwritingInputs
    rationale: str = Field(min_length=1)


class PrivateUnderwritingRevision(Record):
    schema_version: Literal[1] = 1
    classification: Literal["permissioned_private"] = "permissioned_private"
    revision_id: str = Field(pattern=UUID)
    company_id: str
    case_key: str
    sequence: int = Field(ge=1)
    request: UnderwritingRequest
    origin: Literal["synthetic_test_fixture", "company_export"]
    forecast: dict[str, Any]
    author: str
    actor_type: Literal["human"] = "human"
    recorded_at: AwareDatetime
    finance_reviewed: Literal[False] = False
    operating_reviewed: Literal[False] = False
    frozen_comparison_baseline: Literal[False] = False
    causal_value_claim: Literal[False] = False
    operating_action_authorized: Literal[False] = False
    content_sha256: SHA

    @model_validator(mode="after")
    def integrity(self) -> Self:
        validate_key(self.case_key)
        if (self.company_id, self.case_key) != (self.request.inputs.company_id, self.request.inputs.case_key):
            raise ValueError("private underwriting revision scope mismatch")
        if content_hash(self) != self.content_sha256:
            raise ValueError("private underwriting revision hash mismatch")
        if (self.sequence == 1) != (self.request.expected_previous_sha256 is None):
            raise ValueError("private underwriting history requires its predecessor")
        return self

    def require_public(self) -> None:
        raise ValueError("private underwriting cannot be exported as public exhibits")


def calculate(
    inputs: PrivateUnderwritingInputs,
    snapshot: PrivateFinancialSnapshot,
    *,
    benefit_blocks: dict[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    """Reproducible arithmetic only; repository verifies current source authority."""
    inputs = PrivateUnderwritingInputs.model_validate(inputs.model_dump(mode="json"))
    inputs.bind(snapshot)
    selected = frozenset(inputs.selected_initiatives)
    benefit_blocks = benefit_blocks or {}
    ids = {d.initiative_id for d in inputs.scenarios[0].drivers}
    if not set(benefit_blocks) <= {s.scenario_id for s in inputs.scenarios} or any(
        not blocked <= ids for blocked in benefit_blocks.values()
    ):
        raise ValueError("benefit block references an unknown private scenario or initiative")
    with localcontext() as ctx:
        # Bounded inputs include the three-factor service-cost product; keep its
        # full intermediate precision before the shared cent-rounding convention.
        ctx.prec = 128
        scenarios = [
            scenario_report(
                inputs.start,
                inputs.months,
                inputs.multiples,
                scenario,
                single_pool_ledger(
                    inputs.start,
                    inputs.months,
                    scenario,
                    selected,
                    benefit_blocks.get(scenario.scenario_id, frozenset()),
                ),
                benefit_blocks.get(scenario.scenario_id, frozenset()),
            )
            for scenario in inputs.scenarios
        ]
    result: dict[str, Any] = json.loads(
        json.dumps(
            {
                "calculation_version": "private-monthly-underwriting/1",
                "classification": "permissioned_private",
                "financial_snapshot_sha256": snapshot.content_sha256,
                "origin": snapshot.origin,
                "currency": inputs.currency,
                "unit_scale": 1,
                "selected_initiatives": sorted(selected),
                "scenarios": scenarios,
                "cash_definition": "Incremental pre-tax operating cash proxy; excludes tax, financing and unmodeled working capital. Post-horizon settlements are separate.",
                "valuation_definition": "Year-two incremental recurring contribution times an assumed multiple; not total company EV, equity proceeds, fair value or reviewed maintainable earnings.",
                "assumption_authority": "Financial component mappings reproduce accepted ledger amounts only. Eligibility, constraints, judgments and documentary references require separate review.",
                "documentary_references_independently_verified": False,
                "finance_reviewed": False,
                "operating_action_authorized": False,
            },
            default=str,
        )
    )

    return result


def prepare_revision(
    company_id: str,
    case_key: str,
    request: UnderwritingRequest,
    snapshot: PrivateFinancialSnapshot,
    previous: PrivateUnderwritingRevision | None,
) -> PrivateUnderwritingRevision:
    principal = require_intake_writer(company_id)
    request = UnderwritingRequest.model_validate(request.model_dump(mode="json"))
    if (company_id, case_key) != (request.inputs.company_id, request.inputs.case_key):
        raise ValueError("private underwriting request belongs to another company or case")
    now = datetime.now(UTC)
    if snapshot.recorded_at > now:
        raise ValueError("underwriting cannot predate its financial snapshot")
    if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
        raise ValueError("private underwriting requires its current case head")
    if previous and (
        (
            previous.company_id,
            previous.case_key,
            previous.origin,
            previous.request.inputs.entity_id,
            previous.request.inputs.currency,
        )
        != (company_id, case_key, snapshot.origin, snapshot.entity_id, snapshot.currency)
        or previous.recorded_at > now
    ):
        raise ValueError("private underwriting history cannot change scope, origin or chronology")
    payload: dict[str, Any] = dict(
        revision_id=str(uuid.uuid4()),
        company_id=company_id,
        case_key=case_key,
        sequence=previous.sequence + 1 if previous else 1,
        request=request,
        origin=snapshot.origin,
        forecast=calculate(request.inputs, snapshot),
        author=principal.subject,
        recorded_at=now,
        content_sha256="0" * 64,
    )
    payload["content_sha256"] = content_hash(PrivateUnderwritingRevision.model_construct(**payload))
    return PrivateUnderwritingRevision.model_validate(payload)


def verify_revision(revision: PrivateUnderwritingRevision, snapshot: PrivateFinancialSnapshot) -> None:
    PrivateUnderwritingRevision.model_validate(revision.model_dump(mode="json"))
    if revision.origin != snapshot.origin or revision.forecast != calculate(revision.request.inputs, snapshot):
        raise ValueError("private underwriting forecast does not reproduce from its financial input")
