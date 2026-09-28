"""Reproduce the explicitly constructed operating exercise. No customer/vendor data."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pe_value_os.diligence.underwriting import UnderwritingCase, month_start


def example() -> UnderwritingCase:
    scenarios = []
    # These are deliberately judgmental cases, not a probability distribution or issuer forecast.
    choices = [
        ("downside", ".03", ".25", ".02", ".20", ".35", "0", ".05", "100000", "9000", "2027-03-01", "2027-04-01"),
        ("base", ".06", ".65", ".005", ".35", ".60", "18000", ".15", "60000", "6500", "2027-01-01", "2026-12-15"),
        ("upside", ".08", ".80", ".002", ".50", ".80", "30000", ".25", "55000", "6500", "2026-12-01", "2026-12-01"),
    ]
    for (
        name,
        uplift,
        capture,
        churn,
        coverage,
        resolution,
        action,
        accelerated,
        setup,
        fees,
        pricing_date,
        service_date,
    ) in choices:
        assumptions = []

        def add(key, value, unit, rationale, invalidated_by, target=assumptions):
            target.append(
                {
                    "assumption_id": key,
                    "value": value,
                    "unit": unit,
                    "rationale": rationale,
                    "owner": "Analyst-authored exercise",
                    "invalidated_by": invalidated_by,
                    "evidence_ids": ["constructed-inputs"],
                }
            )

        add(
            "eligible-revenue",
            "1000000",
            "currency",
            "Illustrative monthly renewal cohort; not extracted or inferred from Progress contracts.",
            "Contract-level eligibility and revenue reconciliation differ.",
        )
        add(
            "uplift",
            uplift,
            "fraction",
            "Assumed permissible price uplift before capture and incremental churn.",
            "Notice periods, caps or competitor pricing prevent the uplift.",
        )
        add(
            "capture",
            capture,
            "fraction",
            "Assumed share of the uplift captured after concessions; not a success probability.",
            "Signed renewal economics show lower net capture.",
        )
        add(
            "churn",
            churn,
            "fraction",
            "Incremental lost revenue relative to the otherwise unchanged counterfactual cohort.",
            "Retention/mix evidence cannot isolate this loss or shows a larger loss.",
        )
        add(
            "variable-cost-rate",
            ".20",
            "fraction",
            "Assumed genuinely variable servicing cost, including the symmetric cost reduction on lost revenue.",
            "Costs are fixed or cannot adjust with cohort revenue.",
        )
        add(
            "contacts",
            "20000",
            "count",
            "Illustrative monthly contact population; no actual Progress ticket data.",
            "Ticket scope, seasonality or data quality differs.",
        )
        add(
            "coverage",
            coverage,
            "fraction",
            "Eligible share of constructed contacts.",
            "Safety or complexity exclusions reduce the eligible population.",
        )
        add(
            "resolution",
            resolution,
            "fraction",
            "Assumed successful resolution after recontacts; not raw chatbot containment.",
            "Evaluation or repeat-contact measurement fails.",
        )
        add(
            "hours-per-contact",
            ".20",
            "hours",
            "Twelve net handling minutes per eligible successful contact.",
            "Time study shows shifted work or less net time avoided.",
        )
        add(
            "cost-per-hour",
            "35",
            "currency_per_hour",
            "Assumed avoidable vendor cost per hour, not salary converted automatically to savings.",
            "Vendor commitments or minimums prevent expense removal.",
        )
        add(
            "cost-action",
            action,
            "currency",
            "Explicit monthly vendor-spend action, capped by avoided work and addressable spend; zero in downside.",
            "No approved contract reduction or spend reduction is available.",
        )
        add(
            "addressable-spend",
            "100000",
            "currency",
            "Constructed monthly expense pool bounding modeled cost removal.",
            "Reconciled eligible spend is lower.",
        )
        add(
            "receivables",
            "1200000",
            "currency",
            "Constructed existing receivables; no new sales or bad-debt recovery assumed.",
            "Subledger reconciliation, terms or disputes do not support the balance.",
        )
        add(
            "accelerated",
            accelerated,
            "fraction",
            "Share collected early; incremental cash reverses on the counterfactual collection date.",
            "Balances are uncollectible or would already have been paid.",
        )
        add(
            "setup",
            setup,
            "currency",
            "Temporary implementation expense paid before benefits; scenario-specific overrun included.",
            "Vendor scope or implementation staffing changes.",
        )
        add(
            "service-fee",
            fees,
            "currency",
            "Monthly platform, QA and vendor fee from kickoff, including delayed/failed benefit months.",
            "Signed fees, usage or QA requirements differ.",
        )
        add(
            "pricing-fee",
            "2000",
            "currency",
            "Monthly governance and analysis expense from kickoff.",
            "Required operator effort or tooling changes.",
        )
        add(
            "foundation",
            "25000",
            "currency",
            "Committed shared data foundation expense retained even if all initiatives are excluded.",
            "Commitment can actually be canceled before payment.",
        )
        add(
            "capex",
            "15000",
            "currency",
            "Illustrative capitalized implementation outlay; not deducted again in EBITDA.",
            "Accounting review requires expense classification or a different asset amount.",
        )
        costs = [
            {
                "cost_id": "shared-foundation",
                "initiative_ids": ["pricing-renewals", "service-automation", "collections-timing"],
                "kind": "implementation",
                "amount": "foundation",
                "recognized_on": "2026-10-05",
                "paid_on": "2026-10-05",
                "retained_if_excluded": True,
            },
            {
                "cost_id": "service-setup",
                "initiative_ids": ["service-automation"],
                "kind": "implementation",
                "amount": "setup",
                "recognized_on": "2026-10-20",
                "paid_on": "2026-11-20",
                "retained_if_excluded": False,
            },
            {
                "cost_id": "service-capex",
                "initiative_ids": ["service-automation"],
                "kind": "capex",
                "amount": "capex",
                "recognized_on": "2026-11-15",
                "paid_on": "2026-11-15",
                "retained_if_excluded": False,
            },
        ]
        for index in range(24):
            day = month_start(date(2026, 10, 1), index).isoformat()
            for initiative, amount in (("pricing-renewals", "pricing-fee"), ("service-automation", "service-fee")):
                costs.append(
                    {
                        "cost_id": f"{initiative}-fee-{index + 1:02}",
                        "initiative_ids": [initiative],
                        "kind": "recurring",
                        "amount": amount,
                        "recognized_on": day,
                        "paid_on": day,
                        "retained_if_excluded": False,
                    }
                )
        scenarios.append(
            {
                "scenario_id": name,
                "assumptions": assumptions,
                "costs": costs,
                "drivers": [
                    {
                        "kind": "pricing",
                        "initiative_id": "pricing-renewals",
                        "title": "Constructed eligible renewal cohort",
                        "benefit_pool": "renewal-cohort",
                        "effective_on": pricing_date,
                        "monthly_eligible_revenue": "eligible-revenue",
                        "uplift": "uplift",
                        "capture": "capture",
                        "incremental_churn": "churn",
                        "variable_cost_rate": "variable-cost-rate",
                        "collection_lag_months": 1,
                        "variable_cost_payment_lag_months": 0,
                    },
                    {
                        "kind": "service",
                        "initiative_id": "service-automation",
                        "title": "Constructed support/vendor intervention",
                        "benefit_pool": "support-vendor-spend",
                        "effective_on": service_date,
                        "monthly_contacts": "contacts",
                        "coverage": "coverage",
                        "resolution": "resolution",
                        "hours_per_contact": "hours-per-contact",
                        "avoidable_cost_per_hour": "cost-per-hour",
                        "monthly_cost_action": "cost-action",
                        "monthly_addressable_spend": "addressable-spend",
                        "cost_action": "none" if action == "0" else "vendor_reduction",
                        "payment_lag_months": 0,
                    },
                    {
                        "kind": "collections",
                        "initiative_id": "collections-timing",
                        "title": "Constructed receivables timing exercise",
                        "benefit_pool": "existing-receivables",
                        "effective_on": "2027-01-05",
                        "receivables_balance": "receivables",
                        "accelerated_fraction": "accelerated",
                        "counterfactual_collection_on": "2027-03-15",
                    },
                ],
            }
        )
    return UnderwritingCase.model_validate(
        {
            "case_id": "progress-constructed-underwriting-v1",
            "company": "Progress Software reference case",
            "currency": "USD",
            "exercise": "constructed_operating_exercise",
            "start": "2026-10-01",
            "evidence": [
                {
                    "evidence_id": "constructed-inputs",
                    "classification": "constructed",
                    "locator": "scripts/build_underwriting_example.py: analyst-authored inputs; no actual operating records",
                },
                {
                    "evidence_id": "public-context",
                    "classification": "public_filing",
                    "locator": "data/public/progress/annual-facts.json: context only; no operating cohort derived from consolidated accounts",
                },
            ],
            "scenarios": scenarios,
            "multiples": ["6", "8", "10"],
            "multiple_rationale": "Arbitrary 6x/8x/10x sensitivity grid to demonstrate valuation dependence; not sourced comparable-company multiples or a fair-value range.",
        }
    )


if __name__ == "__main__":
    target = Path("data/constructed/progress/underwriting.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(example().model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote constructed operating exercise: {target}")
