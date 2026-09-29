"""A sourced accounting correction with a non-reliance interval, not a backtest."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from .models import Record
from .scheduling import fingerprint
from .vintages import TimestampEvidence

Metric = Literal[
    "revenue",
    "cost_of_revenue",
    "operating_expenses",
    "operating_income",
    "other_income",
    "pretax_income",
    "income_tax",
    "net_income",
    "cash",
    "short_term_investments",
    "cash_and_investments",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_cash",
    "change_in_cash",
    "opening_cash",
]
METRICS = {
    "revenue",
    "cost_of_revenue",
    "operating_expenses",
    "operating_income",
    "other_income",
    "pretax_income",
    "income_tax",
    "net_income",
    "cash",
    "short_term_investments",
    "cash_and_investments",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_cash",
    "change_in_cash",
    "opening_cash",
}


class FilingSnapshot(Record):
    snapshot_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    classification: Literal["public_filing"]
    form: Literal["10-K", "10-K/A"]
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    filed_on: date
    url: HttpUrl
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: AwareDatetime
    period_start: date
    period_end: date
    currency: Literal["USD"]
    unit_scale: Literal[1000]
    rows: tuple[StatementRow, ...]

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        if self.url.scheme != "https":
            raise ValueError("source requires HTTPS")
        if not self.period_start < self.period_end <= self.filed_on <= self.retrieved_at.date():
            raise ValueError("invalid snapshot chronology")
        if len(self.rows) != len(METRICS) or {r.metric for r in self.rows} != METRICS:
            raise ValueError("snapshot requires each financial metric exactly once")
        v = {r.metric: r.amount for r in self.rows}
        checks = (
            v["revenue"] - v["cost_of_revenue"] - v["operating_expenses"] == v["operating_income"],
            v["operating_income"] + v["other_income"] == v["pretax_income"],
            v["pretax_income"] - v["income_tax"] == v["net_income"],
            v["cash"] + v["short_term_investments"] == v["cash_and_investments"],
            sum(v[k] for k in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "fx_cash"))
            == v["change_in_cash"],
            v["opening_cash"] + v["change_in_cash"] == v["cash"],
        )
        if not all(checks):
            raise ValueError("snapshot financial statements do not reconcile")
        return self


class StatementRow(Record):
    metric: Metric
    label: str = Field(min_length=1)
    amount: Decimal
    pdf_page: int = Field(ge=1)
    printed_page: str = Field(min_length=1)
    column: str = Field(min_length=1)


class CorrectionRow(Record):
    metric: Metric
    originally_reported: Decimal
    adjustment: Decimal
    restated: Decimal
    pdf_page: int = Field(ge=1)


class IncomeCorrection(Record):
    additional_stock_compensation: Decimal = Field(ge=0)
    additional_payroll_withholding: Decimal = Field(ge=0)
    income_tax_benefit: Decimal = Field(ge=0)
    pdf_page: int = Field(ge=1)


EventKind = Literal["original_filing", "non_reliance", "restatement_announcement", "amended_filing"]


class DisclosureEvent(Record):
    event_id: str = Field(min_length=1)
    kind: EventKind
    reported_on: date
    date_basis: Literal["filing_metadata", "issuer_release_date"]
    source_url: HttpUrl
    locator: str = Field(min_length=1)
    accepted: TimestampEvidence | None = None
    public_available: TimestampEvidence | None = None

    @model_validator(mode="after")
    def timing(self) -> Self:
        if self.source_url.scheme != "https":
            raise ValueError("event source requires HTTPS")
        expected = "filing_metadata" if self.kind in ("original_filing", "amended_filing") else "issuer_release_date"
        if self.date_basis != expected:
            raise ValueError("event date basis does not match its source kind")
        if self.accepted and self.date_basis != "filing_metadata":
            raise ValueError("issuer release date is not SEC acceptance")
        if self.accepted and self.public_available and self.public_available.timestamp < self.accepted.timestamp:
            raise ValueError("registered filing availability cannot precede acceptance")
        return self


class RestatementHistory(Record):
    schema_version: Literal[1] = 1
    classification: Literal["public_accounting_restatement"]
    revision_kind: Literal["accounting_error_restatement"]
    scope: str = Field(min_length=1)
    original: FilingSnapshot
    amended: FilingSnapshot
    corrections: tuple[CorrectionRow, ...]
    net_income_bridge: IncomeCorrection
    events: tuple[DisclosureEvent, DisclosureEvent, DisclosureEvent, DisclosureEvent]
    timing_limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        old, new = self.original, self.amended
        if old.form != "10-K" or new.form != "10-K/A":
            raise ValueError("preserve original 10-K and amended 10-K/A independently")
        if any(
            getattr(old, k) != getattr(new, k)
            for k in ("entity_id", "period_start", "period_end", "currency", "unit_scale")
        ):
            raise ValueError("snapshot entity, period or units differ")
        if (
            old.filed_on >= new.filed_on
            or old.snapshot_id == new.snapshot_id
            or old.accession == new.accession
            or old.sha256 == new.sha256
        ):
            raise ValueError("restatement requires two distinct source snapshots in order")
        expected = ("original_filing", "non_reliance", "restatement_announcement", "amended_filing")
        if tuple(e.kind for e in self.events) != expected or len({e.event_id for e in self.events}) != 4:
            raise ValueError("retain the original, non-reliance, announcement and amended events in order")
        dates = [e.reported_on for e in self.events]
        if dates != sorted(dates) or dates[0] != old.filed_on or dates[-1] != new.filed_on:
            raise ValueError("event chronology must agree with the source filings")
        retrieved = max(old.retrieved_at, new.retrieved_at)
        if any(t.timestamp > retrieved for e in self.events for t in (e.accepted, e.public_available) if t):
            raise ValueError("timestamp evidence cannot follow retrieval")
        if len(self.corrections) != len(METRICS) or {r.metric for r in self.corrections} != METRICS:
            raise ValueError("each metric requires an explicit correction row")
        original = {r.metric: r.amount for r in old.rows}
        amended = {r.metric: r.amount for r in new.rows}
        for row in self.corrections:
            if row.originally_reported != original[row.metric] or row.restated != amended[row.metric]:
                raise ValueError("correction must tie to both independent source snapshots")
            if row.originally_reported + row.adjustment != row.restated:
                raise ValueError("correction does not reconcile")
        bridge = self.net_income_bridge
        if (
            original["net_income"]
            - bridge.additional_stock_compensation
            - bridge.additional_payroll_withholding
            + bridge.income_tax_benefit
            != amended["net_income"]
        ):
            raise ValueError("net income correction components do not reconcile")
        return self


def _selection(history: RestatementHistory, events: list[DisclosureEvent], basis: str) -> dict[str, Any]:
    # An announcement carries no fully mapped annual filing. Keep non-reliance
    # until the independently registered amended filing becomes eligible.
    kind = events[-1].kind if events else None
    snapshot = history.amended if kind == "amended_filing" else history.original if kind == "original_filing" else None
    return {
        "basis": basis,
        "status": kind or "no_registered_disclosure",
        "selected": snapshot.model_dump(mode="json") if snapshot else None,
        "selected_sha256": fingerprint(snapshot) if snapshot else None,
        "eligible_event_ids": [e.event_id for e in events],
    }


def select_by_disclosed_date(history: RestatementHistory, cutoff: date) -> dict[str, Any]:
    """Retrospective calendar chronology; deliberately not public-availability proof."""
    if isinstance(cutoff, datetime):
        raise ValueError("calendar chronology accepts a date, not an intraday cutoff")
    return _selection(history, [e for e in history.events if e.reported_on <= cutoff], "reported_date_only")


def select_by_publication(history: RestatementHistory, cutoff: datetime) -> dict[str, Any]:
    """Fail closed for missing times, including notices that may invalidate numbers."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("publication cutoff requires an explicit timezone")
    # Date metadata and today's retrieval do not bound first public availability.
    # Without times for all registered events, do not certify an information set.
    unknown = [e.event_id for e in history.events if e.public_available is None]
    if unknown:
        return {
            "basis": "public_availability",
            "status": "withheld_missing_publication_evidence",
            "selected": None,
            "unknown": unknown,
        }
    eligible = [e for e in history.events if e.public_available and e.public_available.timestamp <= cutoff]
    # Keep semantic revision order even if an older source was published later.
    return _selection(history, eligible, "public_availability")


def analyze_restatement(history: RestatementHistory) -> dict[str, Any]:
    labels = {r.metric: r.label for r in history.original.rows}
    dates = sorted({d for e in history.events for d in (e.reported_on - timedelta(days=1), e.reported_on)})
    return {
        "schema_version": "accounting-restatement-review/1",
        "history_sha256": fingerprint(history),
        "history": history.model_dump(mode="json"),
        "comparison": [
            {
                "metric": r.metric,
                "label": labels[r.metric],
                "original": str(r.originally_reported * 1000),
                "adjustment": str(r.adjustment * 1000),
                "restated": str(r.restated * 1000),
            }
            for r in history.corrections
        ],
        "date_replay": [{"cutoff": d.isoformat(), **select_by_disclosed_date(history, d)} for d in dates],
        "public_availability": select_by_publication(history, history.amended.retrieved_at),
        "limitations": [
            *history.timing_limitations,
            "Calendar reconstruction is retrospective source chronology, not a trading backtest or first-publication claim.",
            "This is a narrow FY2005 statement comparison, not an exhaustive reconstruction of all contemporaneous disclosures.",
            "Original numbers are historical records, not current reliable statements; non-reliance suppresses numeric selection until the mapped amendment.",
            "No EBITDA add-back, operating benefit, cash savings, investment return or current-company conclusion is inferred from this correction.",
        ],
    }
