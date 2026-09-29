"""Versioned source-backed research payloads and evidence-bound constructed lessons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field, model_validator

from .models import Record
from .operating_sources import AllocatedSourceBook, OperatingBook, operating_records, source_records
from .scheduling import OperatingPlan, fingerprint
from .underwriting import EXPECTED_UNITS
from .underwriting_models import UnderwritingModel

if TYPE_CHECKING:
    from .cases import CaseRevision

UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
SHA = r"^[0-9a-f]{64}$"


def source_rows(book: OperatingBook) -> dict[tuple[str, str], Record]:
    return operating_records(source_records(book))


class OperatingRecordRef(Record):
    kind: Literal["renewal", "service_month", "invoice"]
    record_id: str = Field(min_length=1)
    record_sha256: str = Field(pattern=SHA)


class SourceLesson(Record):
    lesson_id: str = Field(min_length=1)
    classification: Literal["constructed_source_lesson"] = "constructed_source_lesson"
    initiative_id: str = Field(min_length=1)
    scenario_id: Literal["downside", "base", "upside"]
    assumption_ids: tuple[str, ...] = Field(min_length=1)
    source_records: tuple[OperatingRecordRef, ...] = Field(min_length=1)
    finding: str = Field(min_length=1)
    response: str = Field(min_length=1)
    follow_up_evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> Self:
        if len(set(self.assumption_ids)) != len(self.assumption_ids):
            raise ValueError("lesson assumption references must be unique")
        if len({(r.kind, r.record_id) for r in self.source_records}) != len(self.source_records):
            raise ValueError("lesson source references must be unique")
        return self


class SourceCasePayload(Record):
    # Separate from v1: adding defaults to the old payload would change hashes of
    # already signed case revisions. v2 must be explicitly requested by a writer.
    schema_version: Literal[2]
    underwriting: UnderwritingModel
    operating_plan: OperatingPlan
    decision_question: str = Field(min_length=1)
    counterevidence: tuple[str, ...] = Field(min_length=1)
    unresolved_items: tuple[str, ...] = Field(min_length=1)
    operating_sources: OperatingBook
    challenged_revision_id: str = Field(pattern=UUID)
    challenged_revision_sha256: str = Field(pattern=SHA)
    lessons: tuple[SourceLesson, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def scope(self) -> Self:
        self.operating_sources.bind(self.underwriting, self.operating_plan)
        if len({lesson.lesson_id for lesson in self.lessons}) != len(self.lessons):
            raise ValueError("lesson IDs must be unique within the revision")
        rows = source_rows(self.operating_sources)
        for lesson in self.lessons:
            for ref in lesson.source_records:
                row = rows.get((ref.kind, ref.record_id))
                if row is None or fingerprint(row) != ref.record_sha256:
                    raise ValueError("lesson must bind an exact record in its source book")
        return self

    def bind_parent(self, parent: CaseRevision) -> None:
        if (self.challenged_revision_id, self.challenged_revision_sha256) != (
            parent.revision_id,
            parent.content_sha256,
        ):
            raise ValueError("source revision must challenge its exact stored parent")
        scenarios = {s.scenario_id: s for s in parent.draft.payload.underwriting.scenarios}
        expected_kind = {"pricing": "renewal", "service": "service_month", "collections": "invoice"}
        for lesson in self.lessons:
            scenario = scenarios[lesson.scenario_id]
            driver = next((d for d in scenario.drivers if d.initiative_id == lesson.initiative_id), None)
            if driver is None:
                raise ValueError("lesson references an unknown prior initiative")
            owned = {getattr(driver, field) for field in EXPECTED_UNITS if hasattr(driver, field)}
            if not set(lesson.assumption_ids) <= owned:
                raise ValueError("lesson assumptions must belong to the prior initiative driver")
            if any(ref.kind != expected_kind[driver.kind] for ref in lesson.source_records):
                raise ValueError("lesson source kind does not match its initiative mechanism")
            if isinstance(self.operating_sources, AllocatedSourceBook):
                owners = {(a.kind, a.record_id): a.pool_id for a in self.operating_sources.assignments}
                if any(owners[(ref.kind, ref.record_id)] != driver.benefit_pool for ref in lesson.source_records):
                    raise ValueError("lesson record must belong to its initiative's economic pool")


def source_payload(payload: Any) -> SourceCasePayload | None:
    """Obtain the unchanged source contract from a source or composed exit payload."""
    if isinstance(payload, SourceCasePayload):
        return payload
    nested = getattr(payload, "source_basis", None)
    return nested if isinstance(nested, SourceCasePayload) else None


def learning_context(payload: SourceCasePayload, parent: CaseRevision) -> list[dict[str, Any]]:
    payload.bind_parent(parent)
    previous = parent.draft.payload
    previous_source = source_payload(previous)
    old_rows = source_rows(previous_source.operating_sources) if previous_source else {}
    new_rows = source_rows(payload.operating_sources)
    lessons = []
    for lesson in payload.lessons:
        scenario = next(s for s in previous.underwriting.scenarios if s.scenario_id == lesson.scenario_id)
        lessons.append(
            {
                **lesson.model_dump(mode="json"),
                "prior_revision_id": parent.revision_id,
                "prior_revision_sha256": parent.content_sha256,
                "prior_recorded_at": parent.recorded_at,
                "prior_assumptions": [
                    a.model_dump(mode="json") for a in scenario.assumptions if a.assumption_id in lesson.assumption_ids
                ],
                "source_comparison": [
                    {
                        "kind": ref.kind,
                        "record_id": ref.record_id,
                        "prior_record": old_rows[(ref.kind, ref.record_id)].model_dump(mode="json")
                        if (ref.kind, ref.record_id) in old_rows
                        else None,
                        "prior_record_sha256": fingerprint(old_rows[(ref.kind, ref.record_id)])
                        if (ref.kind, ref.record_id) in old_rows
                        else None,
                        "current_record": new_rows[(ref.kind, ref.record_id)].model_dump(mode="json"),
                        "current_record_sha256": ref.record_sha256,
                    }
                    for ref in lesson.source_records
                ],
                "authority": "Authored constructed lesson; evidence binding does not independently validate the interpretation, establish causal impact or reconstruct historical information availability.",
            }
        )
    return lessons


def financial_snapshot(payload: SourceCasePayload, parent: CaseRevision, report: dict[str, Any]) -> dict[str, Any]:
    # Store the calculated period totals and source dispositions. The exact input
    # records live in the signed payload; the CLI can reproduce the daily ledger.
    # Do not duplicate its full daily entries or embedded reference forecasts in
    # every revision and comparison response.
    scenarios = []
    for modeled, inputs in zip(report["scenarios"], payload.underwriting.scenarios, strict=True):
        scenarios.append(
            {
                **{key: value for key, value in modeled.items() if key != "entries"},
                "assumptions": [a.model_dump(mode="json") for a in inputs.assumptions],
                "drivers": [d.model_dump(mode="json") for d in inputs.drivers],
                "costs": [c.model_dump(mode="json") for c in inputs.costs],
                "valuation": [],
                "valuation_unavailable_reason": "Source-bounded terms and unreviewed maintainability do not establish an exit-value basis.",
            }
        )
    return {
        "calculation_version": report["version"],
        "calculation_sha256": report["report_sha256"],
        "input_sha256": fingerprint(payload),
        "source_book_sha256": report["book_sha256"],
        "underwriting_sha256": report["underwriting_sha256"],
        "plan_sha256": report["plan_sha256"],
        "case_id": report["case_id"],
        "company": report["company"],
        "currency": report["currency"],
        "classification": "constructed_operating_exercise",
        "source_classification": report["classification"],
        "selected_initiatives": report.get(
            "selected_initiatives", sorted(d.initiative_id for d in payload.underwriting.scenarios[0].drivers)
        ),
        **(
            {key: report[key] for key in ("interaction_policy", "selection_basis")}
            if "interaction_policy" in report
            else {}
        ),
        "scenarios": scenarios,
        "missing_service_months": report["missing_service_months"],
        **({"unrepresented_pools": report["unrepresented_pools"]} if "unrepresented_pools" in report else {}),
        "learning_context": learning_context(payload, parent),
        "cash_definition": report["reference_forecast"]["cash_definition"],
        "limitation": report["limitation"],
        "actual_company_realized_value": None,
    }
