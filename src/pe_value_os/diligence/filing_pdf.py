"""Extract an explicitly mapped filing table; fail closed on changed source bytes or row shape.

This is a reviewed table adapter, not a generic financial-statement inference model.
Mappings and raw source documents have separate fingerprints. No network request is
made by extraction; callers retrieve the public source through an authorized route.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, HttpUrl, model_validator

from .models import FactBundle, FinancialFact, FiscalPeriod, Record, SourceClass, SourceDocument

EXTRACTION_VERSION = "filing-pdf/1"


class Column(Record):
    label: str
    period: FiscalPeriod


class Row(Record):
    metric: str
    label: str
    occurrence: int = Field(default=0, ge=0)


class Table(Record):
    pdf_page: int = Field(ge=1)
    printed_page: str
    heading: str
    unit_heading: str
    columns: tuple[Column, ...] = Field(min_length=1)
    rows: tuple[Row, ...] = Field(min_length=1)


class FilingMap(Record):
    company: str
    entity_id: str
    ticker: str
    title: str
    url: HttpUrl
    accession: str
    form: Literal["10-K", "10-Q"]
    filed_on: date
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1, 1000, 1000000]
    entity_heading: str
    tables: tuple[Table, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def table_identity(self) -> Self:
        for table in self.tables:
            unit_text = table.unit_heading.lower()
            if "thousands" in unit_text and self.unit_scale != 1000:
                raise ValueError("source heading in thousands requires a scale of 1000")
            if "millions" in unit_text and self.unit_scale != 1000000:
                raise ValueError("source heading in millions requires a scale of 1000000")
        keys = [(r.metric, c.period.start, c.period.end) for t in self.tables for r in t.rows for c in t.columns]
        if len(keys) != len(set(keys)):
            raise ValueError("a mapping must not emit duplicate facts")
        return self


def table_values(text: str, table: Table) -> dict[str, tuple[Decimal, ...]]:
    """Exact row labels plus full numeric tail avoid matching neighboring rows or shifted columns."""
    normalized = "\n".join(" ".join(line.split()) for line in text.splitlines())
    if table.heading not in normalized or table.unit_heading not in normalized:
        raise ValueError("statement heading or unit heading does not match the reviewed mapping")
    positions = [normalized.find(column.label) for column in table.columns]
    if any(p < 0 for p in positions) or positions != sorted(set(positions)):
        raise ValueError("period columns missing, duplicated or reordered")
    result = {}
    for row in table.rows:
        matches = [line for line in normalized.splitlines() if line.startswith(row.label + " ")]
        if len(matches) <= row.occurrence:
            raise ValueError(f"mapped financial row missing: {row.metric}")
        tail = matches[row.occurrence][len(row.label) :].replace("$", "").strip()
        tokens = tail.split()
        if len(tokens) != len(table.columns):
            raise ValueError(f"financial column count changed: {row.metric}")
        values = []
        for token in tokens:
            number = r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
            if not re.fullmatch(rf"(?:{number}|\({number}\))", token):
                raise ValueError(f"ambiguous or missing financial value: {row.metric}")
            negative = token.startswith("(")
            value = Decimal(token.strip("()").replace(",", ""))
            values.append(-value if negative else value)
        result[row.metric] = tuple(values)
    return result


def extract_filing(pdf: Path, mapping: FilingMap, retrieved_at: datetime, cutoff: date) -> FactBundle:
    from pypdf import PdfReader

    raw = pdf.read_bytes()
    if hashlib.sha256(raw).hexdigest() != mapping.source_sha256:
        raise ValueError("source PDF hash differs from the reviewed mapping")
    reader = PdfReader(pdf)
    document_id = f"{mapping.entity_id}:{mapping.accession}"
    source = SourceDocument(
        document_id=document_id,
        classification=SourceClass.PUBLIC_FILING,
        entity_id=mapping.entity_id,
        title=mapping.title,
        url=mapping.url,
        accession=mapping.accession,
        form=mapping.form,
        filed_on=mapping.filed_on,
        retrieved_at=retrieved_at,
        sha256=mapping.source_sha256,
        mapping_sha256=hashlib.sha256(mapping.model_dump_json().encode()).hexdigest(),
        extraction_version=EXTRACTION_VERSION,
    )
    facts = []
    for table in mapping.tables:
        if table.pdf_page > len(reader.pages):
            raise ValueError("mapped page does not exist")
        text = reader.pages[table.pdf_page - 1].extract_text()
        if mapping.entity_heading not in text or text.rstrip().splitlines()[-1] != table.printed_page:
            raise ValueError("entity or printed page does not match the reviewed mapping")
        values = table_values(text, table)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        for row in table.rows:
            source_row = [line for line in lines if line.startswith(row.label + " ")][row.occurrence]
            for column, amount in zip(table.columns, values[row.metric], strict=True):
                facts.append(
                    FinancialFact(
                        fact_id=f"{document_id}:{column.period.end}:{row.metric}",
                        document_id=document_id,
                        entity_id=mapping.entity_id,
                        metric=row.metric,
                        period=column.period,
                        currency=mapping.currency,
                        reported_amount=amount,
                        unit_scale=mapping.unit_scale,
                        pdf_page=table.pdf_page,
                        printed_page=table.printed_page,
                        row_label=row.label,
                        column_label=column.label,
                        source_row=source_row,
                    )
                )
    return FactBundle(
        company=mapping.company,
        entity_id=mapping.entity_id,
        ticker=mapping.ticker,
        information_cutoff=cutoff,
        documents=(source,),
        facts=tuple(facts),
    )
