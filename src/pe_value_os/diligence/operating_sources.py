"""Constructed operating records constrain the existing dated financial engine.

This is a prospective source-to-forecast exercise, not an actuals adapter. It does
not mutate stored underwriting, acceptance receipts or financial claims.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .models import Record
from .scheduling import OperatingPlan, evaluate_plan, fingerprint
from .underwriting import (
    EXPECTED_UNITS,
    Driver,
    Entry,
    Pricing,
    Scenario,
    Service,
    UnderwritingCase,
    cash_profile,
    ledger,
    month_end,
    month_start,
    totals,
)

VERSION = "operating-source-forecast/1"
ZERO = Decimal(0)


class Renewal(Record):
    record_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    monthly_revenue: Decimal = Field(ge=0)
    renewal_on: date
    term_ends_on: date
    notice_days: int = Field(ge=0, le=365)
    planned_notice_on: date
    permitted: Literal["yes", "no", "unknown"]
    uplift_cap: Decimal | None = Field(ge=0, le=1)
    evidence_locator: str = Field(min_length=1)

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.term_ends_on < self.renewal_on:
            raise ValueError("renewal term ends before it begins")
        return self


class Queue(Record):
    queue_id: str = Field(min_length=1)
    contacts: int = Field(ge=0)
    eligible_contacts: int = Field(ge=0)
    handling_minutes: Decimal = Field(ge=0)
    sample_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    recontact_count: int = Field(ge=0)
    quality_review: Literal["passed", "failed", "missing"]
    evidence_locator: str = Field(min_length=1)

    @model_validator(mode="after")
    def counts(self) -> Self:
        if self.eligible_contacts > self.contacts:
            raise ValueError("eligible contacts exceed the queue population")
        if not self.recontact_count <= self.resolved_count <= self.sample_count:
            raise ValueError("quality counts do not reconcile")
        return self


class ServiceMonth(Record):
    month: date
    contacts_control: int = Field(ge=0)
    queues: tuple[Queue, ...] = Field(min_length=1)
    qa_hours: Decimal = Field(ge=0)
    vendor_spend: Decimal = Field(ge=0)
    vendor_minimum: Decimal = Field(ge=0)
    avoidable_hourly_rate: Decimal = Field(ge=0)
    release_on: date | None
    release_evidence: str | None = Field(min_length=1)

    @model_validator(mode="after")
    def controls(self) -> Self:
        if self.month.day != 1:
            raise ValueError("service month must start on day one")
        if len({q.queue_id for q in self.queues}) != len(self.queues):
            raise ValueError("duplicate queue in service month")
        if sum(q.contacts for q in self.queues) != self.contacts_control:
            raise ValueError("service contacts do not reconcile to the declared control")
        if self.vendor_minimum > self.vendor_spend:
            raise ValueError("vendor minimum exceeds addressable vendor spend")
        if (self.release_on is None) != (self.release_evidence is None):
            raise ValueError("vendor release date and evidence must be supplied together")
        return self


class Invoice(Record):
    record_id: str = Field(min_length=1)
    invoice_id: str = Field(min_length=1)
    issued_on: date
    due_on: date
    amount: Decimal = Field(ge=0)
    credited: Decimal = Field(ge=0)
    paid_at_cutoff: Decimal = Field(ge=0)
    disputed: Decimal = Field(ge=0)
    accelerated_on: date
    counterfactual_on: date
    evidence_locator: str = Field(min_length=1)

    @property
    def open_amount(self) -> Decimal:
        return self.amount - self.credited - self.paid_at_cutoff

    @model_validator(mode="after")
    def balances(self) -> Self:
        if self.open_amount < 0 or self.disputed > self.open_amount:
            raise ValueError("invoice credits, payments or dispute exceed the balance")
        if not self.issued_on <= self.due_on <= self.counterfactual_on:
            raise ValueError("invoice chronology is inconsistent")
        if not self.issued_on <= self.accelerated_on < self.counterfactual_on:
            raise ValueError("acceleration must precede counterfactual collection")
        return self


class OperatingSourceBook(Record):
    schema_version: Literal[1] = 1
    classification: Literal["constructed_operating_records"]
    book_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    underwriting_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cutoff: date
    renewal_monthly_revenue_control: Decimal = Field(ge=0)
    invoice_open_balance_control: Decimal = Field(ge=0)
    scope_description: str = Field(min_length=1)
    renewals: tuple[Renewal, ...] = Field(min_length=1)
    service_months: tuple[ServiceMonth, ...]
    invoices: tuple[Invoice, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        for rows, key in (
            (self.renewals, "record_id"),
            (self.renewals, "contract_id"),
            (self.invoices, "record_id"),
            (self.invoices, "invoice_id"),
        ):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError(f"duplicate source {key}; overlapping populations cannot be summed")
        if len({row.month for row in self.service_months}) != len(self.service_months):
            raise ValueError("duplicate service month")
        if sum((r.monthly_revenue for r in self.renewals), ZERO) != self.renewal_monthly_revenue_control:
            raise ValueError("renewal revenue does not reconcile to its declared scope")
        if sum((r.open_amount for r in self.invoices), ZERO) != self.invoice_open_balance_control:
            raise ValueError("invoice open balances do not reconcile to their declared scope")
        if any(r.issued_on > self.cutoff for r in self.invoices):
            raise ValueError("invoice did not exist at the source cutoff")
        return self

    def bind(self, case: UnderwritingCase, plan: OperatingPlan) -> None:
        self.bind_scope(case, plan)
        for scenario in case.scenarios:
            if sorted(d.kind for d in scenario.drivers) != ["collections", "pricing", "service"]:
                raise ValueError("this source adapter requires one pricing, service and collections driver")

    def bind_scope(self, case: UnderwritingCase, plan: OperatingPlan) -> None:
        """Shared scope checks; the v1 adapter additionally requires one driver of each kind."""
        plan.bind(case)
        case.require_public()
        if (self.case_id, self.company, self.currency, self.underwriting_sha256, self.plan_sha256) != (
            case.case_id,
            case.company,
            case.currency,
            fingerprint(case),
            fingerprint(plan),
        ):
            raise ValueError("source book requires its exact case, currency and operating plan")
        if self.cutoff != case.start:
            raise ValueError("source cutoff must equal the constructed model start")
        end = month_end(case.start, case.months - 1)
        if any(not case.start <= r.renewal_on <= end for r in self.renewals):
            raise ValueError("renewal must begin inside the explicit horizon")
        if any(not case.start <= r.month <= end for r in self.service_months):
            raise ValueError("service month lies outside the explicit horizon")
        if any(not case.start <= r.accelerated_on < r.counterfactual_on <= end for r in self.invoices):
            raise ValueError("both invoice cash dates must fit inside the explicit horizon")
        for scenario in case.scenarios:
            for driver in scenario.drivers:
                references = [getattr(driver, field) for field in EXPECTED_UNITS if hasattr(driver, field)]
                if len(set(references)) != len(references):
                    raise ValueError("source projection requires distinct assumption references within each driver")
                if isinstance(driver, Service) and driver.cost_action not in {"none", "vendor_reduction"}:
                    raise ValueError("vendor records cannot support a different type of cost action")


class RecordAssignment(Record):
    kind: Literal["renewal", "service_month", "invoice"]
    record_id: str = Field(min_length=1)
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initiative_id: str = Field(min_length=1)


def operating_records(book: OperatingSourceBook) -> dict[tuple[str, str], Record]:
    return {
        **{("renewal", r.record_id): r for r in book.renewals},
        **{("invoice", r.record_id): r for r in book.invoices},
        **{("service_month", str(r.month)): r for r in book.service_months},
    }


class PartitionedSourceBook(Record):
    """One owner per complete source record; no fractional duplication of vendor commitments."""

    schema_version: Literal[2]
    records: OperatingSourceBook
    assignments: tuple[RecordAssignment, ...] = Field(min_length=1)
    partition_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def complete_partition(self) -> Self:
        rows = operating_records(self.records)
        keys = [(a.kind, a.record_id) for a in self.assignments]
        if len(set(keys)) != len(keys) or set(keys) != set(rows):
            raise ValueError("partition must assign every source record exactly once")
        if any(fingerprint(rows[(a.kind, a.record_id)]) != a.record_sha256 for a in self.assignments):
            raise ValueError("partition must bind each exact source record")
        return self

    def bind(self, case: UnderwritingCase, plan: OperatingPlan) -> None:
        self.records.bind_scope(case, plan)
        kinds = {d.initiative_id: d.kind for d in case.scenarios[0].drivers}
        expected = {"renewal": "pricing", "service_month": "service", "invoice": "collections"}
        if {a.initiative_id for a in self.assignments} != set(kinds):
            raise ValueError("partition requires source records for every current initiative and no unknown owners")
        if any(kinds[a.initiative_id] != expected[a.kind] for a in self.assignments):
            raise ValueError("partition source kind must match its initiative mechanism")


OperatingBook = OperatingSourceBook | PartitionedSourceBook


def source_records(book: OperatingBook) -> OperatingSourceBook:
    return book.records if isinstance(book, PartitionedSourceBook) else book


def _row_ledger(
    case: UnderwritingCase,
    scenario: Scenario,
    driver: Driver,
    values: dict[str, Decimal],
    effective: date,
    end: date | None,
    reference: str,
) -> tuple[Entry, ...]:
    # Reuse the existing Decimal price/churn, cost-cap, accrual and settlement
    # formulas; only source-bound driver inputs and the recognition window differ.
    revised = scenario.model_copy(
        update={
            "drivers": (driver.model_copy(update={"effective_on": effective}),),
            "costs": (),
            "assumptions": tuple(
                a.model_copy(update={"value": values.get(a.assumption_id, a.value)}) for a in scenario.assumptions
            ),
        }
    )
    entries = ledger(
        case,
        revised,
        frozenset({driver.initiative_id}),
        benefit_end_dates={} if end is None else {driver.initiative_id: end},
    )
    return tuple(e.model_copy(update={"reference": reference}) for e in entries)


def source_forecast(book: OperatingBook, case: UnderwritingCase, plan: OperatingPlan) -> dict[str, Any]:
    book.bind(case, plan)
    records = source_records(book)
    partitioned = isinstance(book, PartitionedSourceBook)
    owners: dict[tuple[str, str], str] = (
        {(a.kind, a.record_id): a.initiative_id for a in book.assignments}
        if isinstance(book, PartitionedSourceBook)
        else {}
    )

    def owns(driver: Driver, kind: str, record_id: str) -> bool:
        return not partitioned or owners[(kind, record_id)] == driver.initiative_id

    version = "operating-source-forecast/2" if partitioned else VERSION
    proposed = evaluate_plan(plan, case)
    tasks = {t["task_id"]: t for t in proposed["tasks"]}
    readiness = {g.initiative_id: tasks[g.task_id]["benefit_ready_on"] for g in plan.benefit_gates}
    result = []
    end = month_end(case.start, case.months - 1)
    for scenario in case.scenarios:
        values = {a.assumption_id: a.value for a in scenario.assumptions}
        ids = frozenset(d.initiative_id for d in scenario.drivers)
        # Every original cost survives missing or ineligible operating evidence.
        entries = list(ledger(case, scenario, ids, ids))
        decisions: list[dict[str, Any]] = []
        for driver in scenario.drivers:
            ready = readiness[driver.initiative_id]
            decision_start = len(decisions)
            if isinstance(driver, Pricing):
                for row in records.renewals:
                    if not owns(driver, "renewal", row.record_id):
                        continue
                    notice = max(row.planned_notice_on, records.cutoff, ready) if ready is not None else None
                    deadline = row.renewal_on - timedelta(days=row.notice_days)
                    reason = (
                        "No feasible acceptance gate"
                        if ready is None
                        else "Contract permission absent"
                        if row.permitted != "yes"
                        else "Contractual cap missing"
                        if row.uplift_cap is None
                        else "No positive permissible uplift"
                        if min(row.uplift_cap, values[driver.uplift]) <= 0
                        else "Notice deadline missed"
                        if notice is None or notice > deadline
                        else "Economic launch misses this renewal"
                        if driver.effective_on > row.renewal_on
                        else "Eligible for this declared renewal term"
                    )
                    eligible = reason == "Eligible for this declared renewal term"
                    decisions.append(
                        {
                            "kind": "renewal",
                            "record_id": row.record_id,
                            "eligible": eligible,
                            "reason": reason,
                            "notice_on": notice,
                            "notice_deadline": deadline,
                            "monthly_revenue": row.monthly_revenue,
                            "renewal_on": row.renewal_on,
                            "term_ends_on": row.term_ends_on,
                            "evidence_locator": row.evidence_locator,
                        }
                    )
                    if eligible:
                        assert row.uplift_cap is not None
                        overrides = {
                            driver.monthly_eligible_revenue: row.monthly_revenue,
                            driver.uplift: min(values[driver.uplift], row.uplift_cap),
                        }
                        entries.extend(
                            _row_ledger(
                                case, scenario, driver, overrides, row.renewal_on, row.term_ends_on, row.record_id
                            )
                        )
            elif isinstance(driver, Service):
                months = {item.month: item for item in records.service_months}
                for index in range(case.months):
                    month = month_start(case.start, index)
                    service_row = months.get(month)
                    if service_row is not None and not owns(driver, "service_month", str(month)):
                        continue
                    if service_row is None or ready is None:
                        decisions.append(
                            {
                                "kind": "service",
                                "month": month,
                                "eligible": False,
                                "reason": "Missing service month"
                                if service_row is None
                                else "No feasible acceptance gate",
                            }
                        )
                        continue
                    first = max(month, ready, driver.effective_on)
                    eligible_contacts = sum(
                        q.eligible_contacts
                        for q in service_row.queues
                        if q.quality_review == "passed" and q.sample_count
                    )
                    coverage = (
                        min(Decimal(1), service_row.contacts_control * values[driver.coverage] / eligible_contacts)
                        if eligible_contacts
                        else ZERO
                    )
                    gross_hours = sum(
                        (
                            q.eligible_contacts
                            * coverage
                            * min(
                                values[driver.resolution],
                                Decimal(q.resolved_count - q.recontact_count) / q.sample_count,
                            )
                            * q.handling_minutes
                            / 60
                            for q in service_row.queues
                            if q.quality_review == "passed" and q.sample_count
                        ),
                        ZERO,
                    )
                    hours = max(ZERO, gross_hours - service_row.qa_hours)
                    action = min(
                        values[driver.monthly_cost_action], service_row.vendor_spend - service_row.vendor_minimum
                    )
                    if service_row.release_on is None or driver.cost_action == "none":
                        action = ZERO
                    overrides = {
                        driver.monthly_contacts: Decimal(1),
                        driver.coverage: Decimal(1),
                        driver.resolution: Decimal(1),
                        driver.hours_per_contact: hours,
                        driver.avoidable_cost_per_hour: service_row.avoidable_hourly_rate,
                        driver.monthly_cost_action: ZERO,
                        driver.monthly_addressable_spend: service_row.vendor_spend,
                    }
                    reference = "service:" + month.isoformat()
                    entries.extend(_row_ledger(case, scenario, driver, overrides, first, month_end(month), reference))
                    financial_first = (
                        max(first, service_row.release_on) if service_row.release_on is not None else first
                    )
                    overrides[driver.monthly_cost_action] = action
                    entries.extend(
                        e
                        for e in _row_ledger(
                            case, scenario, driver, overrides, financial_first, month_end(month), reference
                        )
                        if e.component != "capacity_hours"
                    )
                    decisions.append(
                        {
                            "kind": "service",
                            "month": month,
                            "eligible": first <= month_end(month),
                            "reason": "Capacity requires quality evidence; spend additionally requires a release",
                            "net_full_month_hours": hours,
                            "quality_eligible_contacts": eligible_contacts,
                            "excluded_queues": [
                                q.queue_id
                                for q in service_row.queues
                                if q.quality_review != "passed" or not q.sample_count
                            ],
                            "monthly_cost_action_cap": action,
                            "benefit_from": first,
                            "spend_release_from": financial_first if action else None,
                        }
                    )
            else:
                for invoice in records.invoices:
                    if not owns(driver, "invoice", invoice.record_id):
                        continue
                    first = max(ready, driver.effective_on, invoice.accelerated_on) if ready is not None else None
                    eligible_balance = invoice.open_amount - invoice.disputed
                    eligible = first is not None and first < invoice.counterfactual_on and eligible_balance > 0
                    decisions.append(
                        {
                            "kind": "invoice",
                            "record_id": invoice.record_id,
                            "eligible": eligible,
                            "reason": "Undisputed balance can move earlier"
                            if eligible
                            else "No eligible balance or acceleration window",
                            "open_balance": invoice.open_amount,
                            "disputed": invoice.disputed,
                            "eligible_balance": eligible_balance,
                            "accelerated_on": first,
                            "counterfactual_on": invoice.counterfactual_on,
                            "evidence_locator": invoice.evidence_locator,
                        }
                    )
                    if eligible:
                        assert first is not None
                        revised = driver.model_copy(update={"counterfactual_collection_on": invoice.counterfactual_on})
                        entries.extend(
                            _row_ledger(
                                case,
                                scenario,
                                revised,
                                {driver.receivables_balance: eligible_balance},
                                first,
                                None,
                                invoice.record_id,
                            )
                        )
            if partitioned:
                for disposition in decisions[decision_start:]:
                    disposition["initiative_id"] = driver.initiative_id
        dated = tuple(sorted(entries, key=lambda e: (e.day, e.initiative_id, e.component, e.reference)))
        result.append(
            {
                "scenario_id": scenario.scenario_id,
                "decisions": decisions,
                "monthly": [
                    {
                        "start": month_start(case.start, m),
                        "end": month_end(case.start, m),
                        **totals(dated, month_start(case.start, m), month_end(case.start, m)),
                    }
                    for m in range(case.months)
                ],
                "day_100": totals(dated, case.start, case.start + timedelta(days=99)),
                "year_one": totals(dated, case.start, month_end(case.start, 11)),
                "year_two": totals(dated, month_start(case.start, 12), end),
                "total": totals(dated, case.start, end),
                "cash_settlement_after_horizon": totals(dated, end + timedelta(days=1), month_end(end, 12))[
                    "pre_tax_cash_proxy"
                ],
                **cash_profile(dated, case.start, end),
                "entries": [e.model_dump(mode="json") for e in dated],
            }
        )
    return {
        "version": version,
        "classification": records.classification,
        "book_sha256": fingerprint(book),
        "underwriting_sha256": fingerprint(case),
        "plan_sha256": fingerprint(plan),
        "report_sha256": hashlib.sha256(
            json.dumps(
                {"book": fingerprint(book), "case": fingerprint(case), "plan": fingerprint(plan), "version": version},
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "case_id": case.case_id,
        "company": case.company,
        "currency": case.currency,
        "scenarios": result,
        "source_book": book.model_dump(mode="json"),
        "reference_forecast": proposed["scheduled_financials"],
        "missing_service_months": [
            month_start(case.start, m)
            for m in range(case.months)
            if month_start(case.start, m) not in {r.month for r in records.service_months}
        ],
        "schedule": proposed,
        "actual_company_realized_value": None,
        "limitation": "Prospective constructed source schedule, not company records or measured savings. Missing months block service benefit and retain costs. Declared controls reconcile only the authored scope, not Progress consolidated accounts. No vendor data, actual approvals, calibrated probabilities, private-data ingestion or maintainable exit valuation is represented.",
    }
