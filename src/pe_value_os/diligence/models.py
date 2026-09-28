"""Typed, versioned financial facts; reported values stay distinct from derived measures."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceClass(StrEnum):
    PUBLIC_FILING = "public_filing"
    CONSTRUCTED = "constructed"
    LICENSED_PRIVATE = "licensed_private"
    PERMISSIONED_PRIVATE = "permissioned_private"


class SourceDocument(Record):
    document_id: str = Field(min_length=1)
    classification: SourceClass
    entity_id: str
    title: str
    url: HttpUrl
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: Literal["10-K", "10-Q"]
    filed_on: date
    retrieved_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_version: str

    @model_validator(mode="after")
    def chronology(self) -> Self:
        if self.url.scheme != "https":
            raise ValueError("source references must use HTTPS")
        if self.retrieved_at.tzinfo is None or self.filed_on > self.retrieved_at.date():
            raise ValueError("retrieval must be timezone-aware and not precede filing")
        return self


class FiscalPeriod(Record):
    start: date
    end: date
    basis: Literal["annual", "discrete_quarter", "year_to_date"]

    @model_validator(mode="after")
    def duration(self) -> Self:
        days = (self.end - self.start).days + 1
        limits = {"annual": (330, 400), "discrete_quarter": (70, 110), "year_to_date": (70, 310)}
        low, high = limits[self.basis]
        if not low <= days <= high:
            raise ValueError("unsupported financial duration; review fiscal stubs explicitly")
        return self


class FinancialFact(Record):
    fact_id: str
    document_id: str
    entity_id: str
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    period: FiscalPeriod
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reported_amount: Decimal
    unit_scale: Literal[1, 1000, 1000000]
    accounting_basis: Literal["US_GAAP"] = "US_GAAP"
    pdf_page: int = Field(ge=1)
    printed_page: str
    row_label: str
    column_label: str
    source_row: str

    @property
    def amount(self) -> Decimal:
        """Native currency units, retaining the original reported amount and scale."""
        return self.reported_amount * self.unit_scale


class FactBundle(Record):
    schema_version: Literal[1] = 1
    company: str
    entity_id: str
    ticker: str
    information_cutoff: date
    documents: tuple[SourceDocument, ...]
    facts: tuple[FinancialFact, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        documents = {d.document_id: d for d in self.documents}
        if len(documents) != len(self.documents) or not documents:
            raise ValueError("source document IDs must be unique and nonempty")
        if any(d.entity_id != self.entity_id or d.filed_on > self.information_cutoff for d in self.documents):
            raise ValueError("source entity or information cutoff mismatch")
        seen: set[tuple[str, date, date, str]] = set()
        ids: set[str] = set()
        for fact in self.facts:
            if fact.document_id not in documents or fact.entity_id != self.entity_id:
                raise ValueError("fact must reference a same-entity document")
            if fact.period.end > documents[fact.document_id].filed_on:
                raise ValueError("financial period cannot end after its filing")
            key = fact.metric, fact.period.start, fact.period.end, fact.period.basis
            if key in seen or fact.fact_id in ids:
                raise ValueError("duplicate financial fact; source revisions need explicit selection")
            seen.add(key)
            ids.add(fact.fact_id)
        if not self.facts:
            raise ValueError("at least one sourced fact is required")
        return self

    def require_public(self) -> None:
        if any(d.classification != SourceClass.PUBLIC_FILING for d in self.documents):
            raise ValueError("public filing export rejects private and constructed sources")
