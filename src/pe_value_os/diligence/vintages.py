"""Preserve acquisition-allocation vintages without inventing publication times."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from .models import Record, SourceClass, SourceDocument
from .scheduling import fingerprint

Metric = Literal[
    "working_capital",
    "ppe",
    "technology",
    "trade_name",
    "customer_relationships",
    "deferred_taxes",
    "deferred_revenue",
    "goodwill",
    "net_assets",
]
METRICS = {
    "working_capital",
    "ppe",
    "technology",
    "trade_name",
    "customer_relationships",
    "deferred_taxes",
    "deferred_revenue",
    "goodwill",
    "net_assets",
}


class TimestampEvidence(Record):
    timestamp: AwareDatetime
    source_url: HttpUrl
    locator: str = Field(min_length=1)

    @model_validator(mode="after")
    def https(self) -> Self:
        if self.source_url.scheme != "https":
            raise ValueError("timestamp evidence requires HTTPS")
        return self


class AllocationRow(Record):
    metric: Metric
    reported_amount: Decimal
    source_row: str = Field(min_length=1)
    label: str = Field(min_length=1)


class AllocationVintage(Record):
    vintage_id: str = Field(min_length=1)
    document: SourceDocument
    accepted: TimestampEvidence
    # EDGAR acceptance and today's retrieval cannot fill this field.
    public_available: TimestampEvidence | None = None
    acquisition_date: date
    acquired_business: str = Field(min_length=1)
    status: Literal["preliminary", "final"]
    currency: Literal["USD"]
    unit_scale: Literal[1000]
    pdf_page: int = Field(ge=1)
    printed_page: str = Field(min_length=1)
    table_heading: str = Field(min_length=1)
    rows: tuple[AllocationRow, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.document.classification != SourceClass.PUBLIC_FILING:
            raise ValueError("allocation history accepts only public filings")
        if self.document.form not in ("10-K", "10-Q"):
            raise ValueError("allocation requires a financial filing")
        if self.acquisition_date > self.document.filed_on:
            raise ValueError("acquisition must precede its filing")
        if self.accepted.timestamp > self.document.retrieved_at:
            raise ValueError("acceptance cannot follow retrieval")
        if self.public_available and not (
            self.accepted.timestamp <= self.public_available.timestamp <= self.document.retrieved_at
        ):
            raise ValueError("SEC document availability must fall between acceptance and retrieval")
        if len(self.rows) != len(METRICS) or {r.metric for r in self.rows} != METRICS:
            raise ValueError("allocation requires each of the nine rows exactly once")
        amounts = {r.metric: r.reported_amount for r in self.rows}
        if sum(v for k, v in amounts.items() if k != "net_assets") != amounts["net_assets"]:
            raise ValueError("allocation components do not reconcile to net assets")
        return self


class AllocationHistory(Record):
    schema_version: Literal[1] = 1
    classification: Literal["public_filing_vintage_comparison"]
    revision_kind: Literal["measurement_period_adjustment"]
    revision_explanation: str = Field(min_length=1)
    explanation_url: HttpUrl
    explanation_locator: str = Field(min_length=1)
    timestamp_policy_url: HttpUrl
    coverage: str = Field(min_length=1)
    vintages: tuple[AllocationVintage, AllocationVintage]

    @model_validator(mode="after")
    def sequence(self) -> Self:
        original, revised = self.vintages
        if any(url.scheme != "https" for url in (self.explanation_url, self.timestamp_policy_url)):
            raise ValueError("public history citations require HTTPS")
        if (original.status, revised.status) != ("preliminary", "final"):
            raise ValueError("history must retain preliminary then final allocation")
        for name in ("acquisition_date", "acquired_business", "currency", "unit_scale"):
            if getattr(original, name) != getattr(revised, name):
                raise ValueError("vintages must describe the same acquisition and units")
        if original.document.entity_id != revised.document.entity_id:
            raise ValueError("vintages must belong to the same entity")
        if original.vintage_id == revised.vintage_id or original.document.accession == revised.document.accession:
            raise ValueError("vintages require distinct identities and filings")
        if original.accepted.timestamp >= revised.accepted.timestamp:
            raise ValueError("vintages must follow acceptance chronology")
        return self


def select_vintage(
    history: AllocationHistory, cutoff: datetime, *, basis: Literal["acceptance", "public_availability"]
) -> dict[str, Any]:
    """Select within the registered SEC documents only; never infer missing availability."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff requires an explicit timezone")
    if basis not in ("acceptance", "public_availability"):
        raise ValueError("unsupported selection basis")
    candidates = [v for v in history.vintages if v.accepted.timestamp <= cutoff]
    if basis == "public_availability":
        unknown = [v.vintage_id for v in candidates if v.public_available is None]
        if unknown:
            return {"status": "withheld_missing_publication_evidence", "selected": None, "unknown": unknown}
        candidates = [v for v in candidates if v.public_available and v.public_available.timestamp <= cutoff]
        # Availability gates eligibility; the explicit revision order chooses the
        # latest allocation. A delayed older disclosure must not roll it back.
    if not candidates:
        return {"status": "no_eligible_registered_filing", "selected": None}
    chosen = candidates[-1]
    return {
        "status": "accepted_filing_only" if basis == "acceptance" else "available_registered_filing",
        "selected": chosen.model_dump(mode="json"),
        "selected_sha256": fingerprint(chosen),
    }


def analyze_vintages(history: AllocationHistory) -> dict[str, Any]:
    original, revised = history.vintages
    old = {r.metric: r for r in original.rows}
    new = {r.metric: r for r in revised.rows}
    comparison = [
        {
            "metric": key,
            "label": row.label,
            "preliminary": str(row.reported_amount * original.unit_scale),
            "final": str(new[key].reported_amount * revised.unit_scale),
            "change": str((new[key].reported_amount - row.reported_amount) * original.unit_scale),
        }
        for key, row in old.items()
    ]
    cutoffs = (
        original.accepted.timestamp - timedelta(seconds=1),
        original.accepted.timestamp,
        revised.accepted.timestamp - timedelta(seconds=1),
        revised.accepted.timestamp,
    )
    return {
        "classification": history.classification,
        "history_sha256": fingerprint(history),
        "history": history.model_dump(mode="json"),
        "comparison": comparison,
        "reconciliations": {v.vintage_id: "components_equal_net_assets" for v in history.vintages},
        "cutoffs": [
            {
                "cutoff": cutoff.isoformat(),
                "acceptance_selection": select_vintage(history, cutoff, basis="acceptance"),
                "publication_selection": select_vintage(history, cutoff, basis="public_availability"),
            }
            for cutoff in cutoffs
        ],
        "point_in_time_claim": "withheld"
        if any(v.public_available is None for v in history.vintages)
        else "registered_sources_only",
        "limitations": [
            "Retrospective comparison of two registered annual filings; intermediate disclosures and earlier publication elsewhere are not surveyed.",
            "Acceptance order is not proof of exact public availability. Missing availability evidence blocks that selection.",
            "The issuer describes measurement-period adjustments, not an accounting-error restatement.",
            "Purchase-price allocation changes do not establish operating EBITDA, cash savings or investment returns.",
            "Current-vintage LSEG/WRDS data does not become point-in-time evidence through this comparison.",
        ],
    }
