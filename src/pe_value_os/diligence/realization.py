"""Constructed monthly observations and explicit attribution against a frozen baseline."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal, Self, TypeVar

from pydantic import Field, model_validator

from .. import security
from .cases import CaseReview, CaseRevision, InvestmentCase, digest, writer
from .close_baseline import UUID_PATTERN, CloseBaseline, close_baseline_view
from .models import Record
from .record_chain import content_hash, seal_json
from .scheduling import fingerprint
from .underwriting import Entry, money, month_end, totals

Component = Literal[
    "revenue", "operating_expense", "implementation_expense", "operating_cash", "working_capital_cash", "capex_cash"
]
COMPONENTS = (
    "revenue",
    "operating_expense",
    "implementation_expense",
    "operating_cash",
    "working_capital_cash",
    "capex_cash",
)
ENTRY_COMPONENT: dict[str, Any] = {
    "revenue": "gross_price_benefit",
    "operating_expense": "recurring_cost",
    "implementation_expense": "implementation_expense",
    "operating_cash": "operating_cash",
    "working_capital_cash": "working_capital_cash",
    "capex_cash": "capex_cash",
}


class Posting(Record):
    row_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    label: str = Field(min_length=1)
    component: Component
    amount: Decimal

    @model_validator(mode="after")
    def cents(self) -> Self:
        if money(self.amount) != self.amount:
            raise ValueError("posting requires native-currency whole-cent precision")
        return self


class Controls(Record):
    revenue: Decimal
    operating_expense: Decimal
    implementation_expense: Decimal
    operating_cash: Decimal
    working_capital_cash: Decimal
    capex_cash: Decimal
    ebitda: Decimal

    @model_validator(mode="after")
    def cents(self) -> Self:
        if any(money(value) != value for value in self.model_dump().values()):
            raise ValueError("controls require whole-cent precision")
        return self


class SourceBook(Record):
    schema_version: Literal[1] = 1
    classification: Literal["constructed_operating_records"]
    kind: Literal["observed", "no_intervention_counterfactual"]
    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1]
    start: date
    end: date
    scope_explanation: str = Field(min_length=1)
    method_and_limits: str = Field(min_length=1)
    rows: tuple[Posting, ...] = Field(min_length=1)
    controls: Controls

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.start.day != 1 or self.end != month_end(self.start, 0):
            raise ValueError("observations require a complete calendar month; no partial-month proration")
        if len({r.row_id for r in self.rows}) != len(self.rows):
            raise ValueError("duplicate source posting")
        if {r.component for r in self.rows} != set(COMPONENTS):
            raise ValueError("source must explicitly cover every earnings/cash component, including known zeros")
        return self


class ObservationRequest(Record):
    schema_version: Literal[1] = 1
    ingestion_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    baseline_id: str = Field(pattern=UUID_PATTERN)
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed: SourceBook
    counterfactual: SourceBook
    observed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    counterfactual_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initiative_ids: tuple[str, ...] = Field(min_length=1)
    scope_mapping_rationale: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expected_previous_id: str | None = Field(default=None, pattern=UUID_PATTERN)

    @model_validator(mode="after")
    def matched_books(self) -> Self:
        a, b = self.observed, self.counterfactual
        if fingerprint(a) != self.observed_sha256 or fingerprint(b) != self.counterfactual_sha256:
            raise ValueError("source book fingerprints do not match")
        if a.kind != "observed" or b.kind != "no_intervention_counterfactual":
            raise ValueError("observed and counterfactual source roles are distinct")
        if (a.case_id, a.currency, a.start, a.end) != (b.case_id, b.currency, b.start, b.end):
            raise ValueError("observed and counterfactual scope, currency and period must match")
        if {(r.row_id, r.component) for r in a.rows} != {(r.row_id, r.component) for r in b.rows}:
            raise ValueError("source rows must align explicitly; absent rows are not zero")
        if len(set(self.initiative_ids)) != len(self.initiative_ids):
            raise ValueError("duplicate measurement scope initiative")
        return self


class Observation(Record):
    schema_version: Literal[1] = 1
    observation_id: str
    case_id: str
    company_id: str
    sequence: int = Field(ge=1)
    request: ObservationRequest
    actor: str
    recorded_at: datetime
    content_sha256: str

    @model_validator(mode="after")
    def verify(self) -> Self:
        verify_hash(self)
        return self


class ClaimEvidence(Record):
    evidence_id: str = Field(min_length=1)
    classification: Literal["constructed_attribution_evidence"]
    content: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> Self:
        if digest(self.content) != self.sha256:
            raise ValueError("attribution evidence content hash mismatch")
        return self


class Allocation(Record):
    row_id: str
    initiative_id: str
    amount: Decimal
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: Literal["unvalidated", "limited", "supported_in_constructed_example"]
    alternative_explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def cents(self) -> Self:
        if money(self.amount) != self.amount or self.amount == 0:
            raise ValueError("allocation needs a nonzero whole-cent amount")
        return self


class AttributionRequest(Record):
    schema_version: Literal[1] = 1
    ingestion_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    observation_id: str = Field(pattern=UUID_PATTERN)
    observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["human", "simulation"]
    evidence: tuple[ClaimEvidence, ...]
    allocations: tuple[Allocation, ...]
    rationale: str = Field(min_length=1)
    expected_previous_id: str | None = Field(default=None, pattern=UUID_PATTERN)

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = {e.evidence_id for e in self.evidence}
        if len(ids) != len(self.evidence):
            raise ValueError("duplicate attribution evidence")
        keys = [(a.row_id, a.initiative_id) for a in self.allocations]
        if len(keys) != len(set(keys)) or any(not set(a.evidence_ids) <= ids for a in self.allocations):
            raise ValueError("duplicate allocation or unregistered claim evidence")
        return self


class Attribution(Record):
    schema_version: Literal[1] = 1
    attribution_id: str
    company_id: str
    case_id: str
    sequence: int = Field(ge=1)
    request: AttributionRequest
    actor: str
    actor_type: Literal["human", "service", "model"]
    recorded_at: datetime
    content_sha256: str

    @model_validator(mode="after")
    def verify(self) -> Self:
        verify_hash(self)
        if self.request.mode == "human" and self.actor_type != "human":
            raise ValueError("human attribution requires human authorship")
        return self


def verify_hash(record: Observation | Attribution) -> None:
    if content_hash(record) != record.content_sha256:
        raise ValueError("realization record content hash mismatch")


SignedRecord = TypeVar("SignedRecord", bound=Record)


def signed_record(model: type[SignedRecord], raw: dict[str, Any]) -> SignedRecord:
    raw.update(schema_version=1, recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    return seal_json(model, raw)


def reconcile(book: SourceBook) -> list[dict[str, Any]]:
    sums = {c: sum((r.amount for r in book.rows if r.component == c), Decimal(0)) for c in COMPONENTS}
    sums["ebitda"] = sums["revenue"] + sums["operating_expense"] + sums["implementation_expense"]
    return [
        {
            "component": c,
            "control": getattr(book.controls, c),
            "calculated": v,
            "difference": v - getattr(book.controls, c),
            "status": "matched" if v == getattr(book.controls, c) else "mismatch",
        }
        for c, v in sums.items()
    ]


def differences(request: ObservationRequest) -> list[dict[str, Any]]:
    counter = {r.row_id: r for r in request.counterfactual.rows}
    return [
        {
            "row_id": r.row_id,
            "label": r.label,
            "component": r.component,
            "observed": r.amount,
            "counterfactual": counter[r.row_id].amount,
            "difference": r.amount - counter[r.row_id].amount,
        }
        for r in request.observed.rows
    ]


def shared_totals(rows: list[dict[str, Any]], day: date, key: str = "difference") -> dict[str, Decimal]:
    entries = tuple(
        Entry(
            day=day,
            initiative_id="unassigned",
            component=ENTRY_COMPONENT[r["component"]],
            amount=r[key],
            reference=r["row_id"],
        )
        for r in rows
    )
    financial = totals(entries, day, day)
    # Reuse the earnings/cash identity, but do not expose the calculator's driver
    # names (e.g. gross_price_benefit) as causal labels on observed differences.
    return {
        **{c: sum((r[key] for r in rows if r["component"] == c), Decimal(0)) for c in COMPONENTS},
        **{
            k: financial[k]
            for k in ("incremental_ebitda", "recurring_contribution", "operating_accrual_to_cash", "pre_tax_cash_proxy")
        },
    }


def require_baseline(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revision: CaseRevision,
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
) -> None:
    if (baseline.company_id, baseline.case_id) != (case.company_id, case.case_id):
        raise ValueError("realization cannot cross case or company boundaries")
    if not close_baseline_view(baseline, revision, reviews, baselines)["usable_for_comparison"]:
        raise ValueError("supporting baseline review is invalidated or missing")


def prepare_observation(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revision: CaseRevision,
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
    request: ObservationRequest,
    previous: Observation | None,
) -> Observation:
    principal = writer(case.company_id)
    require_baseline(case, baseline, revision, reviews, baselines)
    if request.baseline_id != baseline.baseline_id or request.baseline_sha256 != baseline.content_sha256:
        raise ValueError("observation requires the exact frozen baseline")
    book = request.observed
    if book.case_id != case.case_id or book.currency != case.currency:
        raise ValueError("observation must retain the case scope and currency")
    forecast = close_baseline_view(baseline, revision, reviews, baselines)["frozen_forecast"]
    if not any(p["start"] == str(book.start) and p["end"] == str(book.end) for p in forecast["monthly"]):
        raise ValueError("observation period lies outside the frozen comparison calendar")
    if set(request.initiative_ids) != set(json.loads(revision.financial_result_json)["selected_initiatives"]):
        raise ValueError("measurement scope must cover the exact frozen initiative set")
    if previous is not None and (
        previous.case_id,
        previous.company_id,
        previous.request.baseline_id,
        previous.request.observed.start,
        previous.request.observed.end,
    ) != (case.case_id, case.company_id, baseline.baseline_id, book.start, book.end):
        raise ValueError("correction must retain the same baseline and period")
    if request.expected_previous_id != (previous.observation_id if previous else None):
        raise ValueError("observation correction must bind its predecessor")
    return signed_record(
        Observation,
        {
            "observation_id": str(uuid.uuid4()),
            "company_id": case.company_id,
            "case_id": case.case_id,
            "sequence": previous.sequence + 1 if previous else 1,
            "request": request.model_dump(mode="json"),
            "actor": principal.subject,
        },
    )


def prepare_attribution(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revision: CaseRevision,
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
    observation: Observation,
    request: AttributionRequest,
    previous: Attribution | None,
) -> Attribution:
    from ..approvals import can_approve

    principal = writer(case.company_id)
    require_baseline(case, baseline, revision, reviews, baselines)
    if (observation.company_id, observation.case_id, observation.request.baseline_id) != (
        case.company_id,
        case.case_id,
        baseline.baseline_id,
    ):
        raise ValueError("attribution requires the same case and baseline observation")
    if request.mode == "human" and not can_approve(principal, case.company_id, "approver"):
        raise security.deny("Human attribution requires a human approver", "case_review_authority")
    if request.mode != baseline.request.mode:
        raise ValueError("attribution mode must retain the baseline review authority")
    if request.observation_id != observation.observation_id or request.observation_sha256 != observation.content_sha256:
        raise ValueError("attribution requires the exact observed snapshot")
    if any(
        c["status"] != "matched"
        for book in (observation.request.observed, observation.request.counterfactual)
        for c in reconcile(book)
    ):
        raise ValueError("unreconciled sources cannot support attribution")
    by_row = {r["row_id"]: r for r in differences(observation.request)}
    used: dict[str, Decimal] = {}
    for allocation in request.allocations:
        if allocation.row_id not in by_row or allocation.initiative_id not in observation.request.initiative_ids:
            raise ValueError("attribution references an unknown source row or initiative")
        delta = by_row[allocation.row_id]["difference"]
        if delta * allocation.amount <= 0:
            raise ValueError("attribution must retain the source difference direction")
        used[allocation.row_id] = used.get(allocation.row_id, Decimal(0)) + allocation.amount
        if abs(used[allocation.row_id]) > abs(delta):
            raise ValueError("attribution exceeds the available source difference")
    if previous is not None and (
        previous.company_id,
        previous.case_id,
        previous.request.observation_id,
        previous.request.mode,
    ) != (case.company_id, case.case_id, observation.observation_id, request.mode):
        raise ValueError("attribution correction must retain snapshot and review mode")
    if request.expected_previous_id != (previous.attribution_id if previous else None):
        raise ValueError("attribution correction must bind its predecessor")
    return signed_record(
        Attribution,
        {
            "attribution_id": str(uuid.uuid4()),
            "company_id": case.company_id,
            "case_id": case.case_id,
            "sequence": previous.sequence + 1 if previous else 1,
            "request": request.model_dump(mode="json"),
            "actor": principal.subject,
            "actor_type": principal.principal_type,
        },
    )


def realization_report(
    case: InvestmentCase,
    baseline: CloseBaseline,
    revisions: list[CaseRevision],
    reviews: list[CaseReview],
    baselines: list[CloseBaseline],
    observations: list[Observation],
    attributions: list[Attribution],
) -> dict[str, Any]:
    records: list[CaseRevision | Observation | Attribution | CloseBaseline] = [
        baseline,
        *revisions,
        *observations,
        *attributions,
    ]
    if any((r.company_id, r.case_id) != (case.company_id, case.case_id) for r in records):
        raise ValueError("realization report cannot mix cases or companies")
    if case.original_revision_id is None or case.current_revision_id is None:
        raise ValueError("realization requires original and current forecasts")
    by_revision = {r.revision_id: r for r in revisions}
    frozen = by_revision[baseline.request.revision_id]
    view = close_baseline_view(baseline, frozen, reviews, baselines)
    original, current = by_revision[case.original_revision_id], by_revision[case.current_revision_id]

    def forecast(revision: CaseRevision, start: str) -> dict[str, Any] | None:
        scenario = next(
            (
                s
                for s in json.loads(revision.financial_result_json)["scenarios"]
                if s["scenario_id"] == baseline.request.scenario_id
            ),
            None,
        )
        return next((m for m in scenario["monthly"] if m["start"] == start), None) if scenario else None

    scoped = [o for o in observations if o.request.baseline_id == baseline.baseline_id]
    if any(o.request.baseline_sha256 != baseline.content_sha256 for o in scoped):
        raise ValueError("stored observation baseline fingerprint mismatch")
    replaced = {o.request.expected_previous_id for o in scoped}
    latest = {str(o.request.observed.start): o for o in scoped if o.observation_id not in replaced}
    if len(latest) != sum(o.observation_id not in replaced for o in scoped):
        raise ValueError("ambiguous observation heads")
    rows = []
    for period in view["frozen_forecast"]["monthly"]:
        o = latest.get(period["start"])
        row: dict[str, Any] = {
            "start": period["start"],
            "end": period["end"],
            "original_forecast": forecast(original, period["start"]),
            "close_forecast": period,
            "current_forecast": forecast(current, period["start"]),
            "status": "not_recorded",
            "measured_difference": None,
            "attributed_difference": None,
            "unassigned_residual": None,
            "rows": [],
        }
        if o is not None:
            checks = {book.kind: reconcile(book) for book in (o.request.observed, o.request.counterfactual)}
            row.update(
                observation_id=o.observation_id,
                source_checks=checks,
                status="reconciled"
                if all(c["status"] == "matched" for group in checks.values() for c in group)
                else "unreconciled",
            )
            if not view["usable_for_comparison"]:
                row["status"] = "baseline_review_invalidated"
            if row["status"] == "reconciled":
                claims = [
                    a
                    for a in attributions
                    if a.request.observation_id == o.observation_id and a.request.observation_sha256 == o.content_sha256
                ]
                if any(a.request.mode != baseline.request.mode for a in claims):
                    raise ValueError("stored attribution mode differs from the baseline")
                corrected = {a.request.expected_previous_id for a in claims}
                active = [a for a in claims if a.attribution_id not in corrected]
                if len(active) > 1:
                    raise ValueError("ambiguous attribution heads")
                allocation = active[0] if active else None
                detail = differences(o.request)
                for item in detail:
                    item["attributed"] = (
                        sum(
                            (a.amount for a in allocation.request.allocations if a.row_id == item["row_id"]), Decimal(0)
                        )
                        if allocation
                        else Decimal(0)
                    )
                    item["unassigned"] = item["difference"] - item["attributed"]
                row.update(
                    measured_difference=shared_totals(detail, o.request.observed.end),
                    attributed_difference=shared_totals(detail, o.request.observed.end, "attributed"),
                    unassigned_residual=shared_totals(detail, o.request.observed.end, "unassigned"),
                    rows=detail,
                    attribution_id=allocation.attribution_id if allocation else None,
                    attribution_status="explicit_claims"
                    if allocation and allocation.request.allocations
                    else "unassigned",
                )
        rows.append(row)
    submitted = [r for r in rows if r["status"] != "not_recorded"]
    eligible = [r for r in submitted if r["status"] == "reconciled"]
    aggregate: dict[str, Any] | None = None
    if submitted and len(eligible) == len(submitted):
        aggregate = {
            name: {
                metric: sum((Decimal(str(r[name][metric])) for r in eligible), Decimal(0))
                for metric in ("incremental_ebitda", "pre_tax_cash_proxy")
            }
            for name in ("measured_difference", "attributed_difference", "unassigned_residual")
        }
        for name in ("original_forecast", "close_forecast", "current_forecast"):
            aggregate[name] = (
                {
                    metric: sum((Decimal(str(r[name][metric])) for r in eligible), Decimal(0))
                    for metric in ("incremental_ebitda", "pre_tax_cash_proxy")
                }
                if all(r[name] is not None for r in eligible)
                else None
            )
    result = {
        "version": "constructed-realization/1",
        "classification": "constructed_operating_exercise",
        "case_id": case.case_id,
        "company_id": case.company_id,
        "currency": case.currency,
        "case_version": case.version,
        "original_revision_id": original.revision_id,
        "original_revision_sha256": original.content_sha256,
        "current_revision_id": current.revision_id,
        "current_revision_sha256": current.content_sha256,
        "baseline": view,
        "periods": rows,
        "submitted_periods": len(submitted),
        "eligible_periods": len(eligible),
        "aggregate_recorded_periods": aggregate,
        "observations": [o.model_dump(mode="json") for o in scoped],
        "attributions": [
            a.model_dump(mode="json")
            for a in attributions
            if a.request.observation_id in {o.observation_id for o in scoped}
        ],
        "actual_company_realized_value": None,
        "day_100_actual": None,
        "limitation": "Constructed monthly records and authored no-intervention counterfactuals. Financial differences are not causal impact. Explicit attribution claims and unassigned residual are separate. Missing periods are not zero; no monthly observation is prorated into a day-100 actual. No company intervention or observed customer result is claimed.",
    }
    lineage = json.loads(current.financial_result_json).get("lineage_review")
    if lineage is not None:
        frozen_ids = json.loads(frozen.financial_result_json)["selected_initiatives"]
        families = {identity: f for f in lineage["families"] for identity in f["all_identities"]}
        if not set(frozen_ids) <= families.keys():
            raise ValueError("lineage must retain the complete frozen measurement perimeter")
        result["version"] = "constructed-realization/2"
        result["initiative_comparability"] = {
            "current_revision_sha256": current.content_sha256,
            "frozen_to_current": [
                {
                    "frozen_initiative_id": identity,
                    "family_id": families[identity]["family_id"],
                    "current_ids": families[identity]["current_ids"],
                }
                for identity in frozen_ids
            ],
            "historical_child_allocations": None,
            "authority": "Read-only identity mapping. Accounting and attribution retain their exact frozen initiative IDs; neither split shares nor KPI readings allocate historical financial claims to successors.",
        }
    current_financial = json.loads(current.financial_result_json)
    if "interaction_policy" in current_financial:
        result["version"] = "constructed-realization/4" if lineage else "constructed-realization/3"
        result["allocation_comparability"] = {
            "original_selected_initiatives": json.loads(original.financial_result_json)["selected_initiatives"],
            "frozen_selected_initiatives": json.loads(frozen.financial_result_json)["selected_initiatives"],
            "current_selected_initiatives": current_financial["selected_initiatives"],
            "current_policy": current_financial["interaction_policy"],
            "financial_attribution": None,
            "authority": "Current modeled choices and population shares may differ from the frozen plan. Accounting observations and attribution retain their exact frozen initiative perimeter. Allocation policy and cost explanations do not change the counterfactual, redistribute earlier claims or establish observed impact.",
        }
    return result
