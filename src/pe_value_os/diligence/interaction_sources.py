"""Source pools constrain selected alternatives without duplicating physical records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .interactions import (
    Accrual,
    InteractionCase,
    calculate_interaction,
    population_shares,
    raw_accruals,
    settle_accruals,
)
from .operating_sources import AllocatedSourceBook, Invoice, Renewal, ServiceMonth, operating_records
from .scheduling import OperatingPlan, evaluate_plan, fingerprint
from .underwriting import ZERO, Driver, Pricing, Scenario, Service, cash_profile, month_end, month_start, totals

VERSION = "operating-source-forecast/3"


def project_record(
    case: InteractionCase,
    scenario: Scenario,
    driver: Driver,
    overrides: dict[str, Decimal],
    first: date,
    last: date | None,
    reference: str,
) -> list[Accrual]:
    """Apply the already-validated fixed pool share to one source-bound exposure.

    This internal projection intentionally does not call the public full-scenario
    ledger. Complete record ownership and pool membership are checked by the book.
    The same unrounded mechanism and settlement routines serve both forecasts.
    """
    projected = scenario.model_copy(
        update={
            "drivers": (driver.model_copy(update={"effective_on": first}),),
            "costs": (),
            "assumptions": tuple(
                a.model_copy(update={"value": overrides.get(a.assumption_id, a.value)}) for a in scenario.assumptions
            ),
        }
    )
    return [
        replace(a, reference=reference)
        for a in raw_accruals(
            case,
            projected,
            frozenset({driver.initiative_id}),
            frozenset(),
            {} if last is None else {driver.initiative_id: last},
        )
    ]


def allocated_source_forecast(book: AllocatedSourceBook, case: InteractionCase, plan: OperatingPlan) -> dict[str, Any]:
    book.bind(case, plan)
    records = book.records
    sources = operating_records(records)
    proposed = evaluate_plan(plan, case)
    selected = frozenset(case.interaction_policy.selected_initiatives)
    shares = population_shares(case)
    tasks = {t["task_id"]: t for t in proposed["tasks"]}
    readiness = {
        g.initiative_id: tasks[g.task_id]["benefit_ready_on"] for g in plan.benefit_gates if g.task_id in tasks
    }
    horizon_end = month_end(case.start, case.months - 1)
    scenarios = []
    for scenario in case.scenarios:
        values = {a.assumption_id: a.value for a in scenario.assumptions}
        ids = frozenset(d.initiative_id for d in scenario.drivers)
        costs, cost_explanation = calculate_interaction(case, scenario, selected, ids)
        accruals: list[Accrual] = []
        decisions: list[dict[str, Any]] = []
        for driver in scenario.drivers:
            share = shares[driver.initiative_id]
            included = driver.initiative_id in selected
            ready = readiness.get(driver.initiative_id)
            exposure = share if included else ZERO
            for assignment in book.assignments:
                if assignment.pool_id != driver.benefit_pool:
                    continue
                row = sources[(assignment.kind, assignment.record_id)]
                reference = assignment.kind + ":" + assignment.record_id
                common = {
                    "initiative_id": driver.initiative_id,
                    "pool_id": driver.benefit_pool,
                    "record_sha256": assignment.record_sha256,
                    "population_share": share,
                    "selected": included,
                    "source_reference": reference,
                }
                if isinstance(driver, Pricing):
                    assert isinstance(row, Renewal)
                    notice = max(row.planned_notice_on, records.cutoff, ready) if ready is not None else None
                    deadline = row.renewal_on - timedelta(days=row.notice_days)
                    reason = (
                        "Excluded by the recorded selection"
                        if not included
                        else "No feasible acceptance gate"
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
                            **common,
                            "kind": "renewal",
                            "record_id": row.record_id,
                            "eligible": eligible,
                            "reason": reason,
                            "notice_on": notice,
                            "notice_deadline": deadline,
                            "monthly_revenue": row.monthly_revenue * exposure,
                            "complete_record_monthly_revenue": row.monthly_revenue,
                            "renewal_on": row.renewal_on,
                            "term_ends_on": row.term_ends_on,
                            "evidence_locator": row.evidence_locator,
                        }
                    )
                    if eligible:
                        assert row.uplift_cap is not None
                        accruals.extend(
                            project_record(
                                case,
                                scenario,
                                driver,
                                {
                                    driver.monthly_eligible_revenue: row.monthly_revenue,
                                    driver.uplift: min(values[driver.uplift], row.uplift_cap),
                                },
                                row.renewal_on,
                                row.term_ends_on,
                                reference,
                            )
                        )
                elif isinstance(driver, Service):
                    assert isinstance(row, ServiceMonth)
                    decision = {**common, "kind": "service", "month": row.month, "eligible": False}
                    if not included or ready is None:
                        decisions.append(
                            {
                                **decision,
                                "reason": "Excluded by the recorded selection"
                                if not included
                                else "No feasible acceptance gate",
                            }
                        )
                        continue
                    first = max(row.month, ready, driver.effective_on)
                    quality_contacts = sum(
                        q.eligible_contacts for q in row.queues if q.quality_review == "passed" and q.sample_count
                    )
                    coverage = (
                        min(Decimal(1), row.contacts_control * values[driver.coverage] / quality_contacts)
                        if quality_contacts
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
                            for q in row.queues
                            if q.quality_review == "passed" and q.sample_count
                        ),
                        ZERO,
                    )
                    hours = max(ZERO, gross_hours - row.qa_hours)
                    action = min(values[driver.monthly_cost_action], row.vendor_spend - row.vendor_minimum)
                    if row.release_on is None or driver.cost_action == "none":
                        action = ZERO
                    overrides = {
                        driver.monthly_contacts: Decimal(1),
                        driver.coverage: Decimal(1),
                        driver.resolution: Decimal(1),
                        driver.hours_per_contact: hours,
                        driver.avoidable_cost_per_hour: row.avoidable_hourly_rate,
                        driver.monthly_cost_action: ZERO,
                        driver.monthly_addressable_spend: row.vendor_spend,
                    }
                    accruals.extend(
                        project_record(case, scenario, driver, overrides, first, month_end(row.month), reference)
                    )
                    financial_first = max(first, row.release_on) if row.release_on is not None else first
                    overrides[driver.monthly_cost_action] = action
                    accruals.extend(
                        a
                        for a in project_record(
                            case, scenario, driver, overrides, financial_first, month_end(row.month), reference
                        )
                        if a.component != "capacity_hours"
                    )
                    decisions.append(
                        {
                            **decision,
                            "eligible": first <= month_end(row.month),
                            "reason": "Allocated capacity requires quality evidence; allocated spend additionally requires a release",
                            "net_full_month_hours": hours * share,
                            "quality_eligible_contacts": quality_contacts * share,
                            "qa_hours_allocated": row.qa_hours * share,
                            "vendor_spend_allocated": row.vendor_spend * share,
                            "vendor_minimum_allocated": row.vendor_minimum * share,
                            "excluded_queues": [
                                q.queue_id for q in row.queues if q.quality_review != "passed" or not q.sample_count
                            ],
                            "monthly_cost_action_cap": action * share,
                            "benefit_from": first,
                            "spend_release_from": financial_first if action else None,
                        }
                    )
                else:
                    assert isinstance(row, Invoice)
                    first = max(ready, driver.effective_on, row.accelerated_on) if ready is not None else None
                    balance = row.open_amount - row.disputed
                    eligible = included and first is not None and first < row.counterfactual_on and balance > 0
                    decisions.append(
                        {
                            **common,
                            "kind": "invoice",
                            "record_id": row.record_id,
                            "eligible": eligible,
                            "reason": "Excluded by the recorded selection"
                            if not included
                            else "Undisputed balance can move earlier"
                            if eligible
                            else "No eligible balance or acceleration window",
                            "open_balance": row.open_amount * exposure,
                            "disputed": row.disputed * exposure,
                            "eligible_balance": balance * exposure,
                            "complete_record_open_balance": row.open_amount,
                            "accelerated_on": first,
                            "counterfactual_on": row.counterfactual_on,
                            "evidence_locator": row.evidence_locator,
                        }
                    )
                    if eligible:
                        assert first is not None
                        revised = driver.model_copy(update={"counterfactual_collection_on": row.counterfactual_on})
                        accruals.extend(
                            project_record(
                                case, scenario, revised, {driver.receivables_balance: balance}, first, None, reference
                            )
                        )
            if isinstance(driver, Service):
                present = {a.record_id for a in book.assignments if a.pool_id == driver.benefit_pool}
                decisions.extend(
                    {
                        "kind": "service",
                        "month": month_start(case.start, m),
                        "initiative_id": driver.initiative_id,
                        "pool_id": driver.benefit_pool,
                        "eligible": False,
                        "reason": "Missing service month",
                        "selected": included,
                        "population_share": share,
                    }
                    for m in range(case.months)
                    if str(month_start(case.start, m)) not in present
                )
        entries, checks = settle_accruals(accruals)
        dated = tuple(sorted((*entries, *costs), key=lambda e: (e.day, e.initiative_id, e.component, e.reference)))
        reference_scenario = next(
            s for s in proposed["scheduled_financials"]["scenarios"] if s["scenario_id"] == scenario.scenario_id
        )
        scenarios.append(
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
                "year_two": totals(dated, month_start(case.start, 12), horizon_end),
                "total": totals(dated, case.start, horizon_end),
                "cash_settlement_after_horizon": totals(
                    dated, horizon_end + timedelta(days=1), month_end(horizon_end, 12)
                )["pre_tax_cash_proxy"],
                **cash_profile(dated, case.start, horizon_end),
                "entries": [e.model_dump(mode="json") for e in dated],
                "interaction": {
                    **reference_scenario["interaction"],
                    "rounding_checks": checks,
                    "cost_allocation_entries": cost_explanation["cost_allocation_entries"],
                },
            }
        )
    return {
        "version": VERSION,
        "classification": records.classification,
        "book_sha256": fingerprint(book),
        "underwriting_sha256": fingerprint(case),
        "plan_sha256": fingerprint(plan),
        "report_sha256": hashlib.sha256(
            json.dumps(
                {"book": fingerprint(book), "case": fingerprint(case), "plan": fingerprint(plan), "version": VERSION},
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "case_id": case.case_id,
        "company": case.company,
        "currency": case.currency,
        "scenarios": scenarios,
        "source_book": book.model_dump(mode="json"),
        "reference_forecast": proposed["scheduled_financials"],
        "schedule": proposed,
        "missing_service_months": [
            month_start(case.start, m)
            for m in range(case.months)
            if month_start(case.start, m) not in {r.month for r in records.service_months}
        ],
        "interaction_policy": case.interaction_policy.model_dump(mode="json"),
        "selection_basis": proposed["scheduled_financials"]["selection_basis"],
        "selected_initiatives": sorted(selected),
        "unrepresented_pools": sorted(set(book.pool_ids) - {a.pool_id for a in book.assignments}),
        "actual_company_realized_value": None,
        "limitation": "Constructed source records belong to one economic pool each. Fixed population shares also allocate QA, vendor spend and vendor minimums before rates and caps; exclusions, failed gates and missing evidence never redistribute shares. Source records replace the reference exposure rather than adding to it. This is a prospective forecast, not measured company impact, causal attribution or maintainable exit earnings.",
    }
