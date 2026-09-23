"""Schemas for source-system data consumed by adapters (PVC-012).

Every record carries `company_id`. Money is Decimal in the record's currency. Months are the first day
of the month. `as_of` lives on the dataset (one per source file or API pull), not on each row.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator


class PnLAccount(StrEnum):
    REVENUE_SUBSCRIPTION = "revenue_subscription"
    REVENUE_SERVICES = "revenue_services"
    COGS_HOSTING = "cogs_hosting"
    COGS_THIRD_PARTY = "cogs_third_party"
    COGS_SUPPORT = "cogs_support"
    COGS_SERVICES = "cogs_services"
    SALES_MARKETING = "sales_marketing"
    RESEARCH_DEVELOPMENT = "research_development"
    GENERAL_ADMIN = "general_admin"


class ChurnType(StrEnum):
    VOLUNTARY = "voluntary"
    INVOLUNTARY_PAYMENT = "involuntary_payment"
    INVOLUNTARY_OTHER = "involuntary_other"


class ConcessionType(StrEnum):
    CREDIT = "credit"
    FREE_MONTHS = "free_months"
    EXTENDED_TERMS = "extended_terms"
    REBATE = "rebate"
    UNCHARGED_SERVICES = "uncharged_services"


class _Record(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    company_id: str = Field(min_length=1)


def _first_of_month(v: date) -> date:
    if v.day != 1:
        raise ValueError("must be the first day of a month")
    return v


class CompanyProfile(BaseModel):
    company_id: str
    name: str
    business_model: str
    vertical: str
    currency: str = Field(pattern="^[A-Z]{3}$")
    fiscal_year_start_month: int = Field(ge=1, le=12)
    deal_thesis: str | None = None
    arr_definition: str = "Contracted recurring subscription revenue, annualised; excludes services and one-time fees"


class PnLLine(_Record):
    month: date
    account: PnLAccount
    amount: Decimal
    currency: str = Field(pattern="^[A-Z]{3}$")

    _month = field_validator("month")(_first_of_month)


class Customer(_Record):
    customer_id: str
    name: str
    segment: str
    size_band: str
    acquisition_channel: str
    first_contract_date: date
    crm_account_id: str | None = None
    billing_account_id: str | None = None
    domain: str | None = None


class CustomerArrMonth(_Record):
    customer_id: str
    month: date
    arr: Decimal = Field(ge=0)
    product: str
    price_book_id: str

    _month = field_validator("month")(_first_of_month)


class ChurnEvent(_Record):
    customer_id: str
    month: date
    churn_type: ChurnType
    reason_code: str | None = None
    notes: str | None = None

    _month = field_validator("month")(_first_of_month)


class PriceBook(_Record):
    price_book_id: str
    product: str
    list_price_per_unit: Decimal = Field(gt=0)
    effective_from: date
    effective_to: date | None = None
    is_current: bool


class InvoiceLine(_Record):
    invoice_id: str
    line_id: str
    customer_id: str
    invoice_date: date
    product: str
    price_book_id: str
    quantity: Decimal = Field(gt=0)
    list_price_per_unit: Decimal = Field(gt=0)
    on_invoice_discount: Decimal = Field(ge=0)
    net_amount: Decimal = Field(ge=0)
    currency: str = Field(pattern="^[A-Z]{3}$")
    deal_size_band: str


class Concession(_Record):
    customer_id: str
    concession_date: date
    concession_type: ConcessionType
    amount: Decimal = Field(ge=0)


class ContractTerm(_Record):
    contract_id: str
    customer_id: str
    start_date: date
    end_date: date
    contracted_uplift_rate: Decimal = Field(ge=0, le=1)
    price_cap_rate: Decimal | None = Field(default=None, ge=0, le=1)
    cpi_linked: bool = False
    mfn_clause: bool = False
    notice_days: int = Field(ge=0)
    termination_for_convenience: bool = False


class SupportTicket(_Record):
    ticket_id: str
    customer_id: str
    created_at: datetime
    category: str
    severity: str
    tier: str
    handle_minutes: Decimal = Field(ge=0)
    csat: int | None = Field(default=None, ge=1, le=5)


class UsageMonth(_Record):
    customer_id: str
    month: date
    active_users: int = Field(ge=0)
    licensed_users: int = Field(ge=0)
    feature: str
    events: int = Field(ge=0)

    _month = field_validator("month")(_first_of_month)


class CrmOpportunity(_Record):
    opportunity_id: str
    customer_id: str
    created_date: date
    close_date: date | None = None
    stage: str = Field(pattern="^(won|lost|open)$")
    opportunity_type: str = Field(pattern="^(new|expansion|renewal)$")
    amount: Decimal = Field(ge=0)


class HeadcountMonth(_Record):
    month: date
    function: str
    fte: Decimal = Field(ge=0)
    fully_loaded_annual_cost_per_fte: Decimal = Field(ge=0)

    _month = field_validator("month")(_first_of_month)


class Document(_Record):
    document_id: str
    title: str
    doc_type: str
    text: str


class DatasetKind(StrEnum):
    PNL = "pnl"
    CUSTOMERS = "customers"
    ARR = "arr"
    CHURN = "churn"
    PRICE_BOOKS = "price_books"
    INVOICES = "invoices"
    CONCESSIONS = "concessions"
    CONTRACTS = "contracts"
    SUPPORT = "support"
    USAGE = "usage"
    CRM_OPPORTUNITIES = "crm_opportunities"
    HEADCOUNT = "headcount"
    DOCUMENTS = "documents"


RECORD_TYPES: dict[DatasetKind, type[_Record]] = {
    DatasetKind.PNL: PnLLine,
    DatasetKind.CUSTOMERS: Customer,
    DatasetKind.ARR: CustomerArrMonth,
    DatasetKind.CHURN: ChurnEvent,
    DatasetKind.PRICE_BOOKS: PriceBook,
    DatasetKind.INVOICES: InvoiceLine,
    DatasetKind.CONCESSIONS: Concession,
    DatasetKind.CONTRACTS: ContractTerm,
    DatasetKind.SUPPORT: SupportTicket,
    DatasetKind.USAGE: UsageMonth,
    DatasetKind.CRM_OPPORTUNITIES: CrmOpportunity,
    DatasetKind.HEADCOUNT: HeadcountMonth,
    DatasetKind.DOCUMENTS: Document,
}


@dataclass(frozen=True)
class RowError:
    source: str
    row: int
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.source} row {self.row} field '{self.field}': {self.message}"


class SourceValidationError(ValueError):
    def __init__(self, errors: list[RowError]):
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors[:10]))


@dataclass
class Dataset:
    kind: DatasetKind
    records: list[Any]
    evidence_id: str
    as_of: datetime
    source_uri: str
    row_errors: list[RowError] = field(default_factory=list)


R = TypeVar("R", bound=_Record)


def parse_rows(
    record_type: type[R], rows: Iterable[dict[str, Any]], source: str, *, strict: bool = False
) -> tuple[list[R], list[RowError]]:
    """Validate rows. Returns (valid records, errors). Rows are numbered from 2 (row 1 is the header).

    With strict=True any error raises SourceValidationError instead of being returned.
    """
    records: list[R] = []
    errors: list[RowError] = []
    for i, raw in enumerate(rows, start=2):
        cleaned = {k: (None if v == "" else v) for k, v in raw.items() if k is not None}
        try:
            records.append(record_type.model_validate(cleaned))
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "<row>"
                errors.append(RowError(source=source, row=i, field=loc, message=err["msg"]))
    if strict and errors:
        raise SourceValidationError(errors)
    return records, errors


def parse_csv(record_type: type[R], text: str, source: str, *, strict: bool = False) -> tuple[list[R], list[RowError]]:
    return parse_rows(record_type, csv.DictReader(io.StringIO(text)), source, strict=strict)


def to_csv(records: Sequence[BaseModel]) -> str:
    if not records:
        return ""
    fields = list(type(records[0]).model_fields)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for r in records:
        row = r.model_dump(mode="json")
        writer.writerow({k: "" if row[k] is None else row[k] for k in fields})
    return buf.getvalue()
