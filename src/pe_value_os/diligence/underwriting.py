"""Dated incremental management model, separate from the released screening calculator.

All money is in the case currency. Drivers accrue ratably within calendar months;
cash settlements and implementation costs occur on their explicit dates. This is
a partial, pre-tax operating cash proxy, never a statutory cash-flow statement.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from .models import Record, SourceClass

VERSION = "monthly-underwriting/1"
ZERO = Decimal(0)
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def month_start(day: date, offset: int = 0) -> date:
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def month_end(day: date, offset: int = 0) -> date:
    return month_start(day, offset + 1) - timedelta(days=1)


class EvidenceRef(Record):
    evidence_id: str = Field(min_length=1)
    classification: SourceClass
    locator: str = Field(min_length=1)


class Assumption(Record):
    assumption_id: str = Field(min_length=1)
    value: Decimal = Field(ge=0)
    unit: Literal["currency", "fraction", "count", "hours", "currency_per_hour", "multiple"]
    rationale: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    invalidated_by: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unit_range(self) -> Self:
        if self.unit == "fraction" and self.value > 1:
            raise ValueError("fraction assumptions must be between zero and one")
        if self.unit == "multiple" and self.value <= 0:
            raise ValueError("valuation multiple must be positive")
        return self


class DriverBase(Record):
    initiative_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    benefit_pool: str = Field(min_length=1)
    effective_on: date


class Pricing(DriverBase):
    kind: Literal["pricing"] = "pricing"
    monthly_eligible_revenue: str
    uplift: str
    capture: str
    incremental_churn: str
    variable_cost_rate: str
    collection_lag_months: int = Field(ge=0, le=12)
    variable_cost_payment_lag_months: int = Field(ge=0, le=12)


class Service(DriverBase):
    kind: Literal["service"] = "service"
    monthly_contacts: str
    coverage: str
    resolution: str
    hours_per_contact: str
    avoidable_cost_per_hour: str
    monthly_cost_action: str
    monthly_addressable_spend: str
    cost_action: Literal["none", "vendor_reduction", "overtime_reduction", "avoided_hire"]
    payment_lag_months: int = Field(ge=0, le=12)


class Collections(DriverBase):
    kind: Literal["collections"] = "collections"
    receivables_balance: str
    accelerated_fraction: str
    counterfactual_collection_on: date

    @model_validator(mode="after")
    def later_baseline_collection(self) -> Self:
        if self.counterfactual_collection_on <= self.effective_on:
            raise ValueError("counterfactual collection must follow accelerated collection")
        return self


Driver = Annotated[Pricing | Service | Collections, Field(discriminator="kind")]


class Cost(Record):
    cost_id: str = Field(min_length=1)
    initiative_ids: tuple[str, ...] = Field(min_length=1)
    kind: Literal["recurring", "implementation", "capex"]
    amount: str
    recognized_on: date
    paid_on: date
    retained_if_excluded: bool


class Scenario(Record):
    scenario_id: Literal["downside", "base", "upside"]
    assumptions: tuple[Assumption, ...]
    drivers: tuple[Driver, ...]
    costs: tuple[Cost, ...]


EXPECTED_UNITS = {
    "monthly_eligible_revenue": "currency",
    "uplift": "fraction",
    "capture": "fraction",
    "incremental_churn": "fraction",
    "variable_cost_rate": "fraction",
    "monthly_contacts": "count",
    "coverage": "fraction",
    "resolution": "fraction",
    "hours_per_contact": "hours",
    "avoidable_cost_per_hour": "currency_per_hour",
    "monthly_cost_action": "currency",
    "monthly_addressable_spend": "currency",
    "receivables_balance": "currency",
    "accelerated_fraction": "fraction",
}


class UnderwritingCase(Record):
    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    exercise: Literal["constructed_operating_exercise"]
    start: date
    months: Literal[24] = 24
    evidence: tuple[EvidenceRef, ...]
    scenarios: tuple[Scenario, ...]
    multiples: tuple[Decimal, ...] = Field(min_length=1)
    multiple_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.start.day != 1:
            raise ValueError("model starts on the first day of a calendar month")
        if any(m <= 0 or not m.is_finite() for m in self.multiples):
            raise ValueError("multiples must be finite and positive")
        if len(set(self.multiples)) != len(self.multiples):
            raise ValueError("multiples must be unique")
        evidence = {e.evidence_id: e for e in self.evidence}
        if len(evidence) != len(self.evidence) or not evidence:
            raise ValueError("evidence IDs must be unique and nonempty")
        if {s.scenario_id for s in self.scenarios} != {"downside", "base", "upside"} or len(self.scenarios) != 3:
            raise ValueError("exactly one downside, base and upside scenario is required")
        expected_ids: set[tuple[str, str, str]] | None = None
        end = month_start(self.start, self.months)
        for scenario in self.scenarios:
            assumptions = {a.assumption_id: a for a in scenario.assumptions}
            if len(assumptions) != len(scenario.assumptions):
                raise ValueError("duplicate assumption ID")
            for assumption in scenario.assumptions:
                if any(e not in evidence for e in assumption.evidence_ids):
                    raise ValueError("assumption references unknown evidence")
                if not any(evidence[e].classification == SourceClass.CONSTRUCTED for e in assumption.evidence_ids):
                    raise ValueError("operating assumptions require explicit constructed evidence")
            ids = {d.initiative_id for d in scenario.drivers}
            if not ids or len(ids) != len(scenario.drivers):
                raise ValueError("initiative IDs must be unique and nonempty")
            if "shared" in ids:
                raise ValueError("shared is reserved for costs belonging to multiple initiatives")
            identities: set[tuple[str, str, str]] = {
                (d.initiative_id, d.kind, d.benefit_pool) for d in scenario.drivers
            }
            if expected_ids is not None and identities != expected_ids:
                raise ValueError("scenarios must retain stable initiative identities")
            expected_ids = identities
            if len({d.benefit_pool for d in scenario.drivers}) != len(scenario.drivers):
                raise ValueError("overlapping benefit pools require a combined driver; independent sums are forbidden")
            for driver in scenario.drivers:
                if not self.start <= driver.effective_on < end:
                    raise ValueError("driver effective date must be inside model horizon")
                for field, unit in EXPECTED_UNITS.items():
                    reference = getattr(driver, field, None)
                    if reference is not None and (reference not in assumptions or assumptions[reference].unit != unit):
                        raise ValueError(f"invalid assumption reference or unit for {field}")
                if isinstance(driver, Service):
                    if driver.cost_action == "none" and assumptions[driver.monthly_cost_action].value != 0:
                        raise ValueError("no cost action cannot create financial savings")
                if isinstance(driver, Collections) and driver.counterfactual_collection_on >= end:
                    raise ValueError("collection timing reversal must be visible within the horizon")
            if len({c.cost_id for c in scenario.costs}) != len(scenario.costs):
                raise ValueError("duplicate cost ID")
            for cost in scenario.costs:
                if len(set(cost.initiative_ids)) != len(cost.initiative_ids):
                    raise ValueError("cost initiative references must be unique")
                if not set(cost.initiative_ids) <= ids:
                    raise ValueError("cost references unknown initiative")
                if cost.amount not in assumptions or assumptions[cost.amount].unit != "currency":
                    raise ValueError("cost requires a currency assumption")
                if not self.start <= cost.recognized_on < end or not self.start <= cost.paid_on < end:
                    raise ValueError("cost recognition and payment must be inside the explicit horizon")
        return self

    def require_public(self) -> None:
        if any(e.classification not in {SourceClass.PUBLIC_FILING, SourceClass.CONSTRUCTED} for e in self.evidence):
            raise ValueError("public exercise rejects private source material")


class Entry(Record):
    day: date
    initiative_id: str
    component: Literal[
        "gross_price_benefit",
        "revenue_leakage",
        "variable_cost",
        "cost_removed",
        "capacity_hours",
        "recurring_cost",
        "implementation_expense",
        "operating_cash",
        "working_capital_cash",
        "capex_cash",
    ]
    amount: Decimal
    reference: str


def _accrue(entries: list[Entry], driver: Driver, component: str, monthly: Decimal, period: date) -> Decimal:
    """Differences of rounded cumulative accruals conserve cents without negative residual days."""
    last = month_end(period)
    first = max(period, driver.effective_on)
    days = (last - first).days + 1
    if days <= 0:
        return ZERO
    full_days = Decimal(calendar.monthrange(period.year, period.month)[1])
    total = money(monthly * days / full_days)
    previous = ZERO
    for offset in range(days):
        cumulative = money(monthly * (offset + 1) / full_days)
        value = cumulative - previous
        entries.append(
            Entry(
                day=first + timedelta(days=offset),
                initiative_id=driver.initiative_id,
                component=component,
                amount=value,
                reference=driver.initiative_id,
            )
        )
        previous = cumulative
    return total


def ledger(case: UnderwritingCase, scenario: Scenario, selected: frozenset[str]) -> tuple[Entry, ...]:
    values = {a.assumption_id: a.value for a in scenario.assumptions}
    entries: list[Entry] = []
    for driver in scenario.drivers:
        if driver.initiative_id not in selected:
            continue
        if isinstance(driver, Collections):
            amount = money(values[driver.receivables_balance] * values[driver.accelerated_fraction])
            for day, signed in ((driver.effective_on, amount), (driver.counterfactual_collection_on, -amount)):
                entries.append(
                    Entry(
                        day=day,
                        initiative_id=driver.initiative_id,
                        component="working_capital_cash",
                        amount=signed,
                        reference=driver.initiative_id,
                    )
                )
            continue
        for index in range(case.months):
            period = month_start(case.start, index)
            if month_end(period) < driver.effective_on:
                continue
            if isinstance(driver, Pricing):
                baseline = values[driver.monthly_eligible_revenue]
                churn = values[driver.incremental_churn]
                gross = baseline * values[driver.uplift] * values[driver.capture] * (1 - churn)
                leakage = -baseline * churn
                variable = -(gross + leakage) * values[driver.variable_cost_rate]
                cash = sum(
                    (
                        _accrue(entries, driver, component, amount, period)
                        for component, amount in (("gross_price_benefit", gross), ("revenue_leakage", leakage))
                    ),
                    ZERO,
                )
                variable_cash = _accrue(entries, driver, "variable_cost", variable, period)
                entries.append(
                    Entry(
                        day=month_end(period, driver.variable_cost_payment_lag_months),
                        initiative_id=driver.initiative_id,
                        component="operating_cash",
                        amount=variable_cash,
                        reference=driver.initiative_id,
                    )
                )
                lag = driver.collection_lag_months
            else:
                hours = (
                    values[driver.monthly_contacts]
                    * values[driver.coverage]
                    * values[driver.resolution]
                    * values[driver.hours_per_contact]
                )
                removed = min(
                    hours * values[driver.avoidable_cost_per_hour],
                    values[driver.monthly_cost_action],
                    values[driver.monthly_addressable_spend],
                )
                _accrue(entries, driver, "capacity_hours", hours, period)
                cash = _accrue(entries, driver, "cost_removed", removed, period)
                lag = driver.payment_lag_months
            entries.append(
                Entry(
                    day=month_end(period, lag),
                    initiative_id=driver.initiative_id,
                    component="operating_cash",
                    amount=cash,
                    reference=driver.initiative_id,
                )
            )
    for cost in scenario.costs:
        if not (set(cost.initiative_ids) & selected) and not cost.retained_if_excluded:
            continue
        amount = money(values[cost.amount])
        # Shared costs are recorded once; no initiative is assigned someone else's commitment.
        owner = cost.initiative_ids[0] if len(cost.initiative_ids) == 1 else "shared"
        if cost.kind != "capex":
            component = "implementation_expense" if cost.kind == "implementation" else "recurring_cost"
            entries.append(
                Entry(
                    day=cost.recognized_on,
                    initiative_id=owner,
                    component=component,
                    amount=-amount,
                    reference=cost.cost_id,
                )
            )
        entries.append(
            Entry(
                day=cost.paid_on,
                initiative_id=owner,
                component="capex_cash" if cost.kind == "capex" else "operating_cash",
                amount=-amount,
                reference=cost.cost_id,
            )
        )
    return tuple(sorted(entries, key=lambda e: (e.day, e.initiative_id, e.component, e.reference)))


EBITDA_COMPONENTS = (
    "gross_price_benefit",
    "revenue_leakage",
    "variable_cost",
    "cost_removed",
    "recurring_cost",
    "implementation_expense",
)


def totals(entries: tuple[Entry, ...], start: date, end: date) -> dict[str, Decimal]:
    components: dict[str, Decimal] = defaultdict(Decimal)
    for entry in entries:
        if start <= entry.day <= end:
            components[entry.component] += entry.amount
    ebitda = sum((components[k] for k in EBITDA_COMPONENTS), ZERO)
    cash = components["operating_cash"] + components["working_capital_cash"] + components["capex_cash"]
    # Accrual adjustment covers operating settlement timing; existing receivables are separate.
    return {
        **{
            k: components[k]
            for k in (*EBITDA_COMPONENTS, "capacity_hours", "operating_cash", "working_capital_cash", "capex_cash")
        },
        "incremental_ebitda": ebitda,
        "recurring_contribution": ebitda - components["implementation_expense"],
        "operating_accrual_to_cash": components["operating_cash"] - ebitda,
        "pre_tax_cash_proxy": cash,
    }


def cash_profile(entries: tuple[Entry, ...], start: date, end: date) -> dict[str, Any]:
    """Funding and sustained recovery within the explicitly modeled, pre-tax cash horizon."""
    by_day: dict[date, Decimal] = defaultdict(Decimal)
    for entry in entries:
        if start <= entry.day <= end and entry.component in {"operating_cash", "working_capital_cash", "capex_cash"}:
            by_day[entry.day] += entry.amount
    cumulative = ZERO
    balances = []
    for day, value in sorted(by_day.items()):
        cumulative += value
        balances.append((day, cumulative))
    negative = [index for index, (_, balance) in enumerate(balances) if balance < 0]
    recovery = None
    state = "no_modeled_deficit"
    if negative:
        last = negative[-1]
        state = "not_recovered_within_horizon"
        if last + 1 < len(balances):
            recovery = balances[last + 1][0]
            state = "recovered_within_horizon"
    return {
        "maximum_dated_funding_need": -min((b for _, b in balances), default=ZERO) if negative else ZERO,
        "cash_proxy_recovery_date": recovery,
        "cash_proxy_recovery_state": state,
    }


def evaluate(case: UnderwritingCase, selected: frozenset[str] | None = None) -> dict[str, Any]:
    case.require_public()
    ids = frozenset(d.initiative_id for d in case.scenarios[0].drivers)
    if selected is None:
        selected = ids
    if not selected <= ids:
        raise ValueError("selection contains an unknown initiative")
    end = month_end(case.start, case.months - 1)
    scenarios = []
    for scenario in case.scenarios:
        entries = ledger(case, scenario, selected)
        monthly: list[dict[str, Any]] = [
            {
                "start": month_start(case.start, m),
                "end": month_end(case.start, m),
                **totals(entries, month_start(case.start, m), month_end(case.start, m)),
            }
            for m in range(case.months)
        ]
        tail = totals(entries, end + timedelta(days=1), month_end(end, 12))
        annual = totals(entries, month_start(case.start, 12), end)
        scenarios.append(
            {
                "scenario_id": scenario.scenario_id,
                "monthly": monthly,
                "day_100": totals(entries, case.start, case.start + timedelta(days=99)),
                "year_one": totals(entries, case.start, month_end(case.start, 11)),
                "year_two": annual,
                "total": totals(entries, case.start, end),
                "cash_settlement_after_horizon": tail["pre_tax_cash_proxy"],
                **cash_profile(entries, case.start, end),
                "valuation": [
                    {
                        "multiple": multiple,
                        "incremental_ev_sensitivity": money(annual["recurring_contribution"] * multiple),
                    }
                    for multiple in case.multiples
                ],
                "assumptions": [a.model_dump(mode="json") for a in scenario.assumptions],
                "drivers": [d.model_dump(mode="json") for d in scenario.drivers],
                "costs": [c.model_dump(mode="json") for c in scenario.costs],
            }
        )
    return {
        "calculation_version": VERSION,
        "input_sha256": hashlib.sha256(case.model_dump_json().encode()).hexdigest(),
        "case_id": case.case_id,
        "company": case.company,
        "currency": case.currency,
        "classification": case.exercise,
        "selected_initiatives": sorted(selected),
        "calculation_sha256": hashlib.sha256(
            json.dumps(
                {"case": case.model_dump(mode="json"), "selected": sorted(selected), "version": VERSION}, sort_keys=True
            ).encode()
        ).hexdigest(),
        "cash_definition": "Incremental pre-tax operating cash proxy; excludes tax, financing, nonmodeled working-capital accounts and terminal settlements shown separately.",
        "valuation_definition": "Year-two incremental recurring contribution multiplied by an assumed sensitivity multiple. Temporary implementation expense is excluded explicitly; no maintainability review, fair-value estimate, total company EV or equity proceeds is implied.",
        "multiple_rationale": case.multiple_rationale,
        "timing_convention": "Benefits accrue ratably by calendar day, using differences of rounded cumulative accruals to conserve cents; costs and cash occur on explicit dates. Day 100 includes the start date. Funding uses dated cash movements; recovery is the first nonnegative cumulative balance after the final modeled deficit, within the 24-month horizon only.",
        "scenarios": scenarios,
        "evidence": [e.model_dump(mode="json") for e in case.evidence],
        "review": "Constructed analytical exercise; no company approval or independent finance review.",
    }
