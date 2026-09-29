"""Explicit population allocation, mutual exclusion and cost explanations.

Allocation changes modeled exposure before rates, churn and spend caps apply.
It never assigns causal attribution or scales a cost commitment away.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .models import Record, SourceClass
from .underwriting import (
    ZERO,
    Collections,
    Driver,
    Entry,
    Pricing,
    Scenario,
    _legacy_ledger,
    _UnderwritingInputs,
    money,
    month_end,
    month_start,
)

POPULATION_FIELDS = {
    "pricing": ("monthly_eligible_revenue",),
    "service": ("monthly_contacts", "monthly_cost_action", "monthly_addressable_spend"),
    "collections": ("receivables_balance",),
}


class AllocationShare(Record):
    initiative_id: str = Field(min_length=1)
    share: Decimal = Field(gt=0, le=1)


class RuleBasis(Record):
    rationale: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    invalidated_by: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class PoolRule(RuleBasis):
    pool_id: str = Field(min_length=1)
    mode: Literal["exclusive", "partition"]
    initiative_ids: tuple[str, ...] = Field(min_length=1)
    shares: tuple[AllocationShare, ...] = ()

    @model_validator(mode="after")
    def scope(self) -> Self:
        if len(set(self.initiative_ids)) != len(self.initiative_ids):
            raise ValueError("a pool cannot repeat an initiative")
        ids = [s.initiative_id for s in self.shares]
        if self.mode == "exclusive":
            if self.shares:
                raise ValueError("exclusive alternatives do not have additive population shares")
        elif len(set(ids)) != len(ids) or set(ids) != set(self.initiative_ids):
            raise ValueError("partition shares must cover every pool initiative exactly once")
        if sum((s.share for s in self.shares), ZERO) > 1:
            raise ValueError("population shares cannot exceed the complete pool")
        return self


class CostAllocation(RuleBasis):
    cost_id: str = Field(min_length=1)
    shares: tuple[AllocationShare, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def scope(self) -> Self:
        if len({s.initiative_id for s in self.shares}) != len(self.shares):
            raise ValueError("cost allocation cannot repeat an owner")
        if sum((s.share for s in self.shares), ZERO) > 1:
            raise ValueError("cost allocation cannot exceed the posted commitment")
        return self


class InteractionPolicy(Record):
    classification: Literal["constructed_allocation_policy"]
    selected_initiatives: tuple[str, ...]
    selection_rationale: str = Field(min_length=1)
    pools: tuple[PoolRule, ...] = Field(min_length=1)
    cost_allocations: tuple[CostAllocation, ...] = ()

    @model_validator(mode="after")
    def identities(self) -> Self:
        if len(set(self.selected_initiatives)) != len(self.selected_initiatives):
            raise ValueError("selection cannot repeat an initiative")
        if len({p.pool_id for p in self.pools}) != len(self.pools):
            raise ValueError("each economic pool requires one rule")
        if len({c.cost_id for c in self.cost_allocations}) != len(self.cost_allocations):
            raise ValueError("each allocated cost requires one rule")
        return self


class InteractionCase(_UnderwritingInputs):
    schema_version: Literal[2]
    interaction_policy: InteractionPolicy

    @model_validator(mode="after")
    def interactions(self) -> Self:
        policy = self.interaction_policy
        rules = {p.pool_id: p for p in policy.pools}
        evidence = {e.evidence_id: e for e in self.evidence}
        for rule in (*policy.pools, *policy.cost_allocations):
            if not set(rule.evidence_ids) <= evidence.keys() or not any(
                evidence[key].classification == SourceClass.CONSTRUCTED for key in rule.evidence_ids
            ):
                raise ValueError("allocation rules require registered constructed evidence")
        for scenario in self.scenarios:
            values = {a.assumption_id: a.value for a in scenario.assumptions}
            if set(rules) != {d.benefit_pool for d in scenario.drivers}:
                raise ValueError("interaction policy must cover every economic pool")
            for pool_id, rule in rules.items():
                members = [d for d in scenario.drivers if d.benefit_pool == pool_id]
                if {d.initiative_id for d in members} != set(rule.initiative_ids):
                    raise ValueError("pool rule must bind its exact driver membership")
                if rule.mode == "partition":
                    if len({d.kind for d in members}) != 1:
                        raise ValueError("partitioned population must use one economic mechanism")
                    for field in POPULATION_FIELDS[members[0].kind]:
                        if len({values[getattr(d, field)] for d in members}) != 1:
                            raise ValueError("partition members must reference the same complete population and spend")
            costs = {c.cost_id: c for c in scenario.costs}
            for cost_rule in policy.cost_allocations:
                if cost_rule.cost_id not in costs or not {s.initiative_id for s in cost_rule.shares} <= set(
                    costs[cost_rule.cost_id].initiative_ids
                ):
                    raise ValueError("cost allocation must bind the commitment's declared owners")
        self.validate_selection(frozenset(policy.selected_initiatives))
        return self

    def validate_selection(self, selected: frozenset[str]) -> None:
        if not selected <= {d.initiative_id for d in self.scenarios[0].drivers}:
            raise ValueError("selection contains an unknown initiative")
        if any(
            p.mode == "exclusive" and len(set(p.initiative_ids) & selected) > 1 for p in self.interaction_policy.pools
        ):
            raise ValueError("mutually exclusive initiatives cannot be selected together")


@dataclass(frozen=True)
class Accrual:
    driver: Driver
    period: date
    first: date
    last: date
    component: str
    amount: Decimal
    cash_on: date | None
    reference: str | None = None


def apportion(values: list[Decimal]) -> list[Decimal]:
    """Conserve the rounded total with deterministic cumulative cent allocation."""
    previous = cumulative = ZERO
    result = []
    for value in values:
        cumulative += value
        rounded = money(cumulative)
        result.append(rounded - previous)
        previous = rounded
    return result


def population_shares(case: InteractionCase) -> dict[str, Decimal]:
    return {
        identity: (
            next(s.share for s in rule.shares if s.initiative_id == identity)
            if rule.mode == "partition"
            else Decimal(1)
        )
        for rule in case.interaction_policy.pools
        for identity in rule.initiative_ids
    }


def raw_accruals(
    case: InteractionCase,
    scenario: Scenario,
    selected: frozenset[str],
    blocked: frozenset[str],
    ends: dict[str, date],
) -> list[Accrual]:
    values = {a.assumption_id: a.value for a in scenario.assumptions}
    shares = population_shares(case)
    result = []
    for driver in sorted(scenario.drivers, key=lambda d: d.initiative_id):
        if driver.initiative_id not in selected or driver.initiative_id in blocked:
            continue
        share = shares[driver.initiative_id]
        if isinstance(driver, Collections):
            if driver.initiative_id in ends:
                raise ValueError("collection reversals cannot be truncated by a benefit end date")
            result.append(
                Accrual(
                    driver,
                    case.start,
                    driver.effective_on,
                    driver.counterfactual_collection_on,
                    "working_capital_cash",
                    values[driver.receivables_balance] * share * values[driver.accelerated_fraction],
                    None,
                )
            )
            continue
        for index in range(case.months):
            period = month_start(case.start, index)
            first = max(period, driver.effective_on)
            last = min(month_end(period), ends.get(driver.initiative_id, month_end(period)))
            if first > last:
                continue
            fraction = Decimal((last - first).days + 1) / calendar.monthrange(period.year, period.month)[1]
            amounts: tuple[tuple[str, Decimal, date | None], ...]
            if isinstance(driver, Pricing):
                baseline = values[driver.monthly_eligible_revenue] * share
                churn = values[driver.incremental_churn]
                gross = baseline * values[driver.uplift] * values[driver.capture] * (1 - churn)
                leakage = -baseline * churn
                variable = -(gross + leakage) * values[driver.variable_cost_rate]
                amounts = (
                    ("gross_price_benefit", gross, month_end(period, driver.collection_lag_months)),
                    ("revenue_leakage", leakage, month_end(period, driver.collection_lag_months)),
                    ("variable_cost", variable, month_end(period, driver.variable_cost_payment_lag_months)),
                )
            else:
                hours = (
                    values[driver.monthly_contacts]
                    * share
                    * values[driver.coverage]
                    * values[driver.resolution]
                    * values[driver.hours_per_contact]
                )
                removed = min(
                    hours * values[driver.avoidable_cost_per_hour],
                    values[driver.monthly_cost_action] * share,
                    values[driver.monthly_addressable_spend] * share,
                )
                amounts = (
                    ("capacity_hours", hours, None),
                    ("cost_removed", removed, month_end(period, driver.payment_lag_months)),
                )
            result.extend(
                Accrual(driver, period, first, last, component, amount * fraction, cash_on)
                for component, amount, cash_on in amounts
            )
    return result


def allocated_cost_entries(case: InteractionCase, costs: tuple[Entry, ...]) -> list[dict[str, Any]]:
    rules = {r.cost_id: r for r in case.interaction_policy.cost_allocations}
    result = []
    for entry in costs:
        rule = rules.get(entry.reference)
        if rule is None:
            result.append({**entry.model_dump(mode="json"), "allocation_basis": "original_ledger_owner"})
            continue
        shares = sorted(rule.shares, key=lambda s: s.initiative_id)
        residual = Decimal(1) - sum((s.share for s in shares), ZERO)
        owners = [s.initiative_id for s in shares] + (["shared"] if residual else [])
        weights = [s.share for s in shares] + ([residual] if residual else [])
        amounts = apportion([entry.amount * w for w in weights])
        if sum(amounts, ZERO) != entry.amount:
            raise ValueError("cost allocation must reconcile to the posted amount")
        result.extend(
            {
                **entry.model_dump(mode="json"),
                "initiative_id": owner,
                "amount": amount,
                "allocation_basis": "authored_cost_allocation",
                "share": weight,
            }
            for owner, amount, weight in zip(owners, amounts, weights, strict=True)
        )
    return result


def settle_accruals(accruals: list[Accrual]) -> tuple[list[Entry], list[dict[str, Any]]]:
    """Round each source/pool component once, then conserve every dated posting."""
    groups: dict[tuple[str, date, str, str], list[Accrual]] = defaultdict(list)
    for item in sorted(accruals, key=lambda a: (a.driver.initiative_id, a.first, a.last)):
        groups[(item.driver.benefit_pool, item.period, item.component, item.reference or "")].append(item)
    entries: list[Entry] = []
    checks = []
    for (pool, period, component, reference), items in sorted(groups.items()):
        amounts = apportion([item.amount for item in items])
        raw_total = sum((item.amount for item in items), ZERO)
        checks.append(
            {
                "pool_id": pool,
                **({"source_reference": reference} if reference else {}),
                "period": period,
                "component": component,
                "raw_total": raw_total,
                "rounded_total": sum(amounts, ZERO),
                "rounding_difference": sum(amounts, ZERO) - raw_total,
                "members": [
                    {"initiative_id": item.driver.initiative_id, "raw_amount": item.amount, "amount": amount}
                    for item, amount in zip(items, amounts, strict=True)
                ],
            }
        )
        for item, amount in zip(items, amounts, strict=True):

            def post(
                day: date,
                component: str,
                value: Decimal,
                identity: str = item.driver.initiative_id,
                source: str = item.reference or item.driver.initiative_id,
            ) -> None:
                entries.append(
                    Entry(
                        day=day,
                        initiative_id=identity,
                        component=component,
                        amount=value,
                        reference=source,
                    )
                )

            if component == "working_capital_cash":
                post(item.first, component, amount)
                post(item.last, component, -amount)
            else:
                days = (item.last - item.first).days + 1
                previous = ZERO
                for offset in range(days):
                    cumulative = money(amount * Decimal(offset + 1) / days)
                    post(item.first + timedelta(days=offset), component, cumulative - previous)
                    previous = cumulative
                if item.cash_on is not None:
                    post(item.cash_on, "operating_cash", amount)
    return entries, checks


def calculate_interaction(
    case: InteractionCase,
    scenario: Scenario,
    selected: frozenset[str],
    blocked: frozenset[str] = frozenset(),
    *,
    benefit_end_dates: dict[str, date] | None = None,
) -> tuple[tuple[Entry, ...], dict[str, Any]]:
    case.require_public()
    case.validate_selection(selected)
    ids = {d.initiative_id for d in case.scenarios[0].drivers}
    if {d.initiative_id for d in scenario.drivers} != ids or scenario not in case.scenarios:
        raise ValueError(
            "interaction calculation requires the complete scenario; source rows need an explicit pool adapter"
        )
    ends = benefit_end_dates or {}
    if not set(ends) <= ids or not blocked <= ids:
        raise ValueError("benefit control references an unknown initiative")
    entries, checks = settle_accruals(raw_accruals(case, scenario, selected, blocked, ends))
    # Commitments are posted by the same implementation used by legacy cases.
    costs = _legacy_ledger(case, scenario.model_copy(update={"drivers": ()}), selected)
    entries.extend(costs)
    shares = population_shares(case)
    pools = [
        {
            "pool_id": rule.pool_id,
            "mode": rule.mode,
            "selected_members": sorted(set(rule.initiative_ids) & selected),
            "blocked_members": sorted(set(rule.initiative_ids) & selected & blocked),
            "members": [
                {"initiative_id": identity, "population_share": shares[identity], "selected": identity in selected}
                for identity in rule.initiative_ids
            ],
            "unselected_or_unassigned_share": Decimal(1)
            - sum((shares[i] for i in rule.initiative_ids if i in selected), ZERO),
        }
        for rule in case.interaction_policy.pools
    ]
    return tuple(sorted(entries, key=lambda e: (e.day, e.initiative_id, e.component, e.reference))), {
        "version": "benefit-pool-allocation/1",
        "pools": pools,
        "rounding_checks": checks,
        "cost_allocation_entries": allocated_cost_entries(case, costs),
        "financial_attribution": None,
        "authority": "Authored population allocation and mutual exclusion. Shares are not probabilities, confidence or causal attribution. Excluded and blocked shares are not redistributed. Cost explanations reconcile to commitments posted once, including retained costs owned by unselected initiatives.",
    }
