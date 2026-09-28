"""Financial-statement contracts. Amounts retain source currency, in millions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Statement(ResearchModel):
    entity_id: str = Field(min_length=1)
    ticker: str = Field(pattern=r"^[A-Z0-9.\-]{1,15}$")
    company: str = Field(min_length=1)
    period: Literal["annual", "quarterly"]
    period_end: date
    fiscal_year: int = Field(ge=1900, le=2200)
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit: Literal["millions"] = "millions"
    revenue: Decimal = Field(gt=0)
    cogs: Decimal | None = None
    sga: Decimal | None = None
    research_development: Decimal | None = None
    operating_income: Decimal | None = None
    source: Literal["comp.funda", "comp.fundq"]
    source_file: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_row: int = Field(ge=0)
    vintage: AwareDatetime
    available_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid_period(self) -> Statement:
        if (self.period == "quarterly") != (self.fiscal_quarter is not None):
            raise ValueError("quarterly statements require a quarter; annual statements must omit it")
        if self.source != ("comp.funda" if self.period == "annual" else "comp.fundq"):
            raise ValueError("source table must match reporting period")
        return self


class Peer(ResearchModel):
    ticker: str = Field(pattern=r"^[A-Z0-9.\-]{1,15}$")
    rationale: str = Field(min_length=10)
    limitation: str = Field(min_length=10)


class Reconciliation(ResearchModel):
    ticker: str
    period_end: date
    metric: Literal["revenue", "cogs", "sga", "operating_income"]
    reported_millions: Decimal
    bridge_millions: Decimal = Decimal(0)
    explanation: str = Field(min_length=10)
    source_url: str = Field(pattern=r"^https://")
    source_locator: str = Field(min_length=1)
    # This is a documented source comparison, never a human acceptance receipt.


class PilotBundle(ResearchModel):
    schema_version: Literal[1] = 1
    classification: Literal["licensed_private", "synthetic"]
    research_mode: Literal["retrospective_current_vintage"] = "retrospective_current_vintage"
    as_of: AwareDatetime
    focal_ticker: str
    anchor_period_end: date
    first_year: int = Field(ge=1900, le=2200)
    peers: list[Peer] = Field(min_length=3, max_length=30)
    statements: list[Statement] = Field(min_length=1, max_length=20000)
    reconciliations: list[Reconciliation] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_scope(self) -> PilotBundle:
        tickers = [p.ticker for p in self.peers]
        if len(set(tickers)) != len(tickers) or self.focal_ticker in tickers:
            raise ValueError("peers must be unique and exclude the focal company")
        if self.anchor_period_end > self.as_of.date() or self.first_year > self.anchor_period_end.year:
            raise ValueError("invalid analysis dates")
        scope = {*tickers, self.focal_ticker}
        identities: dict[str, set[str]] = {}
        for row in self.statements:
            if row.ticker not in scope:
                raise ValueError("statement outside the selected company scope")
            identities.setdefault(row.ticker, set()).add(row.entity_id)
        if any(len(ids) > 1 for ids in identities.values()):
            raise ValueError("ticker maps to multiple entities; resolve the identity mapping first")
        return self


def revision_key(row: Statement) -> tuple[datetime, str, int]:
    return row.vintage, row.source_sha256, row.source_row
