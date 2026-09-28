"""Point-in-time filing facts, with an exact-date PDF adapter and no duration fiction."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from .filing_pdf import Row
from .models import Record, SourceClass, SourceDocument


class BalanceFact(Record):
    fact_id: str
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    as_of: date
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
        return self.reported_amount * self.unit_scale


class BalanceBundle(Record):
    schema_version: Literal[1] = 1
    company: str
    entity_id: str
    ticker: str
    information_cutoff: date
    document: SourceDocument
    facts: tuple[BalanceFact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.document.entity_id != self.entity_id or self.document.filed_on > self.information_cutoff:
            raise ValueError("balance source identity or cutoff mismatch")
        if self.document.form not in ("10-K", "10-Q", "40-F"):
            raise ValueError("balance source must be a financial filing")
        keys = [(f.metric, f.as_of) for f in self.facts]
        if len(keys) != len(set(keys)) or len({f.fact_id for f in self.facts}) != len(self.facts):
            raise ValueError("duplicate point-in-time fact")
        if any(f.as_of > self.document.filed_on for f in self.facts):
            raise ValueError("balance date cannot follow its filing")
        return self

    def require_public(self) -> None:
        if self.document.classification != SourceClass.PUBLIC_FILING:
            raise ValueError("public balance export rejects nonpublic sources")


class BalanceColumn(Record):
    label: str = Field(min_length=1)
    as_of: date
    occurrence: int = Field(default=0, ge=0)


class BalanceTable(Record):
    pdf_page: int = Field(ge=1)
    printed_page: str
    heading: str = Field(min_length=1)
    unit_heading: str = Field(min_length=1)
    columns: tuple[BalanceColumn, ...] = Field(min_length=1)
    selected_column: int = Field(ge=0)
    rows: tuple[Row, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def selected(self) -> Self:
        if self.selected_column >= len(self.columns):
            raise ValueError("selected balance column is missing")
        if len({c.as_of for c in self.columns}) != len(self.columns):
            raise ValueError("duplicate balance dates")
        return self


class BalanceMap(Record):
    company: str
    entity_id: str
    ticker: str
    # Retain the previously registered source identity; adapter hash/version are replaced on extraction.
    registered_document: SourceDocument
    information_cutoff: date
    entity_heading: str = Field(min_length=1)
    entity_page: int = Field(default=1, ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_scale: Literal[1, 1000, 1000000]
    tables: tuple[BalanceTable, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def units_and_keys(self) -> Self:
        if not self.entity_heading.strip():
            raise ValueError("balance entity heading cannot be blank")
        for table in self.tables:
            text = table.unit_heading.lower()
            if ("thousands" in text and self.unit_scale != 1000) or ("millions" in text and self.unit_scale != 1000000):
                raise ValueError("balance unit scale differs from source heading")
        keys = [(r.metric, t.columns[t.selected_column].as_of) for t in self.tables for r in t.rows]
        if len(keys) != len(set(keys)):
            raise ValueError("mapping would duplicate a balance fact")
        return self


def balance_values(text: str, table: BalanceTable) -> dict[str, tuple[Decimal, str]]:
    """Validate all comparative columns; a dash outside the selected date never becomes zero."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    normalized = "\n".join(lines)
    if table.heading not in normalized or table.unit_heading not in normalized:
        raise ValueError("balance heading or units differ from mapping")
    section = normalized[normalized.index(table.heading) :]
    if table.unit_heading not in section:
        raise ValueError("balance units must follow the table heading")
    section = section[section.index(table.unit_heading) :]
    lines = section.splitlines()
    first = min(
        (section.find(r.label + " ") for r in table.rows if section.find(r.label + " ") >= 0), default=len(section)
    )
    header = section[:first]
    positions = []
    for column in table.columns:
        hits = list(re.finditer(re.escape(column.label), header))
        positions.append(hits[column.occurrence].start() if len(hits) > column.occurrence else -1)
    if any(p < 0 for p in positions) or positions != sorted(set(positions)):
        raise ValueError("balance date columns missing, duplicated or reordered")
    result = {}
    for row in table.rows:
        matches = [line for line in lines if line.startswith(row.label + " ")]
        if len(matches) <= row.occurrence:
            raise ValueError("mapped balance row missing")
        source_row = matches[row.occurrence]
        tokens = source_row[len(row.label) :].replace("$", "").split()
        if len(tokens) != len(table.columns):
            raise ValueError("balance column count changed")
        values: list[Decimal | None] = []
        for cell in tokens:
            number = r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
            if cell == "—":
                values.append(None)
            elif re.fullmatch(rf"(?:{number}|\({number}\))", cell):
                values.append(Decimal(cell.strip("()").replace(",", "")) * (-1 if cell.startswith("(") else 1))
            else:
                raise ValueError("ambiguous balance cell")
        selected = values[table.selected_column]
        if selected is None:
            raise ValueError("selected balance value is missing; dash is not zero")
        result[row.metric] = (selected, source_row)
    return result


def extract_balances(pdf: Path, mapping: BalanceMap) -> BalanceBundle:
    from pypdf import PdfReader

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != mapping.registered_document.sha256:
        raise ValueError("balance PDF hash differs from registered source")
    reader = PdfReader(pdf)
    if (
        mapping.entity_page > len(reader.pages)
        or mapping.entity_heading not in reader.pages[mapping.entity_page - 1].extract_text()
    ):
        raise ValueError("balance entity identity page differs")
    source = SourceDocument.model_validate(
        {
            **mapping.registered_document.model_dump(),
            "mapping_sha256": hashlib.sha256(mapping.model_dump_json().encode()).hexdigest(),
            "extraction_version": "balance-pdf/1",
        }
    )
    facts = []
    for table in mapping.tables:
        if table.pdf_page > len(reader.pages):
            raise ValueError("mapped balance page does not exist")
        text = reader.pages[table.pdf_page - 1].extract_text()
        if not text.strip() or text.rstrip().splitlines()[-1].strip() != table.printed_page:
            raise ValueError("printed balance page differs")
        values = balance_values(text, table)
        column = table.columns[table.selected_column]
        for row in table.rows:
            value, source_row = values[row.metric]
            facts.append(
                BalanceFact(
                    fact_id=f"{source.document_id}:{column.as_of}:instant:{row.metric}",
                    metric=row.metric,
                    as_of=column.as_of,
                    currency=mapping.currency,
                    reported_amount=value,
                    unit_scale=mapping.unit_scale,
                    pdf_page=table.pdf_page,
                    printed_page=table.printed_page,
                    row_label=row.label,
                    column_label=column.label,
                    source_row=source_row,
                )
            )
    bundle = BalanceBundle(
        company=mapping.company,
        entity_id=mapping.entity_id,
        ticker=mapping.ticker,
        information_cutoff=mapping.information_cutoff,
        document=source,
        facts=tuple(facts),
    )
    bundle.require_public()
    return bundle
