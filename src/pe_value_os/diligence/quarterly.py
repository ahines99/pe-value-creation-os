"""Derived discrete-quarter cash components with explicit cross-filing lineage.

Never create reported FinancialFacts from a subtraction. Require adjacent periods
and reproduce reported quarter income before accepting mixed-filing cash inputs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .financials import DERIVED, analyze_facts
from .models import FactBundle, FinancialFact

VERSION = "quarterly-difference/1"
CASH_METRICS = (
    "ppe_depreciation",
    "intangible_amortization",
    "debt_amortization",
    "stock_compensation",
    "operating_cash_flow",
    "ppe_purchases",
    "cash_flow_net_income",
)
COMPARABILITY = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expense",
    "operating_income",
    "interest_expense",
    "other_expense_net",
    "pretax_income",
    "income_tax_expense",
    "net_income",
    "amortization_cost_of_revenue",
    "amortization_operating_expense",
)


def derive_quarters(bundle: FactBundle) -> dict[str, Any]:
    bundle.require_public()
    groups: dict[tuple[date, date, str], dict[str, FinancialFact]] = defaultdict(dict)
    for fact in bundle.facts:
        groups[(fact.period.start, fact.period.end, fact.period.basis)][fact.metric] = fact
    source_checks = {(p["start"], p["end"], p["basis"]): p["reconciliations"] for p in analyze_facts(bundle)["periods"]}
    quarters = []
    for (start, end, basis), quarter in sorted(groups.items()):
        if basis != "discrete_quarter" or "operating_cash_flow" in quarter:
            continue
        cumulative = [
            (key, facts)
            for key, facts in groups.items()
            if key[1] == end and key[0] < start and key[2] == "year_to_date"
        ]
        if len(cumulative) != 1:
            quarters.append(
                {
                    "start": start,
                    "end": end,
                    "status": "unavailable",
                    "reason": "exactly one matching cumulative period is required",
                    "components": {},
                    "measures": {},
                    "checks": [],
                }
            )
            continue
        cumulative_key, ytd = cumulative[0]
        year_start = cumulative_key[0]
        priors = [
            (key, facts)
            for key, facts in groups.items()
            if key[0] == year_start
            and key[1] == start - timedelta(days=1)
            and key[2] in {"discrete_quarter", "year_to_date"}
        ]
        if len(priors) != 1:
            quarters.append(
                {
                    "start": start,
                    "end": end,
                    "status": "unavailable",
                    "reason": "exactly one contiguous prior period is required",
                    "components": {},
                    "measures": {},
                    "checks": [],
                }
            )
            continue
        prior_key, prior = priors[0]
        inputs = [*quarter.values(), *ytd.values(), *prior.values()]
        if len({(f.currency, f.accounting_basis) for f in inputs}) != 1:
            raise ValueError("quarter subtraction cannot mix currencies or accounting bases")
        checks = []
        for metric in COMPARABILITY:
            facts = [g.get(metric) for g in (ytd, prior, quarter)]
            difference = (
                None
                if any(f is None for f in facts)
                else ytd[metric].amount - prior[metric].amount - quarter[metric].amount
            )
            checks.append(
                {
                    "metric": metric,
                    "difference": difference,
                    "status": "unavailable" if difference is None else "matched" if difference == 0 else "mismatch",
                    "evidence_ids": [f.fact_id for f in facts if f is not None],
                }
            )
        for period_key in ((start, end, basis), cumulative_key, prior_key):
            key = (period_key[0].isoformat(), period_key[1].isoformat(), period_key[2])
            for check in source_checks[key]:
                if check["target"] != "intangible_amortization" and check["status"] != "matched":
                    checks.append(
                        {
                            "metric": f"source {key}: {check['target']}",
                            "difference": check["difference"],
                            "status": check["status"],
                            "evidence_ids": [f.fact_id for f in groups[period_key].values()],
                        }
                    )
        comparable = all(c["status"] == "matched" for c in checks)
        components: dict[str, dict[str, Any]] = {}
        for metric in CASH_METRICS:
            component_missing = metric not in ytd or metric not in prior
            value = None if component_missing or not comparable else ytd[metric].amount - prior[metric].amount
            components[metric] = {
                "value": value,
                "classification": "calculated_from_public_facts",
                "formula": "year_to_date minus contiguous prior period",
                "evidence_ids": [g[metric].fact_id for g in (ytd, prior) if metric in g],
                "status": "available" if value is not None else "unavailable",
            }
        values = {metric: f.amount for metric, f in quarter.items()}
        values.update({metric: item["value"] for metric, item in components.items() if item["value"] is not None})
        # Same definition check as annual/Q1: cash-flow 'and other' must not be silently called acquired-intangible D&A.
        amort_difference = (
            None
            if not {"intangible_amortization", "amortization_cost_of_revenue", "amortization_operating_expense"}
            <= values.keys()
            else values["intangible_amortization"]
            - values["amortization_cost_of_revenue"]
            - values["amortization_operating_expense"]
        )
        cf_income_difference = (
            None
            if not {"cash_flow_net_income", "net_income"} <= values.keys()
            else values["cash_flow_net_income"] - values["net_income"]
        )
        measures = {}
        for name, spec in DERIVED.items():
            missing = sorted(set(spec["formula"]) - values.keys())
            blocked = []
            if not comparable:
                blocked.append("cross_filing_comparability")
            if "intangible_amortization" in spec["blocking_checks"] and amort_difference not in (None, Decimal(0)):
                blocked.append("intangible_amortization")
            if cf_income_difference not in (None, Decimal(0)):
                blocked.append("cash_flow_net_income")
            for metric in spec["formula"]:
                if metric in values and (
                    (metric == "ppe_purchases" and values[metric] > 0)
                    or (metric in {"ppe_depreciation", "intangible_amortization"} and values[metric] < 0)
                ):
                    blocked.append(f"{metric}_direction")
            evidence: list[str] = []
            for metric in spec["formula"]:
                evidence.extend(
                    components[metric]["evidence_ids"]
                    if metric in components
                    else [quarter[metric].fact_id]
                    if metric in quarter
                    else []
                )
            measures[name] = {
                **spec,
                "value": None
                if missing or blocked
                else sum((values[m] * sign for m, sign in spec["formula"].items()), Decimal(0)),
                "missing": missing,
                "blocked_by": blocked,
                "evidence_ids": evidence,
                "classification": "calculated_from_public_facts",
            }
        quarters.append(
            {
                "start": start,
                "end": end,
                "status": "matched" if comparable else "blocked",
                "reason": "Cross-filing arithmetic agrees; this does not independently certify accounting perimeter or absence of reclassifications."
                if comparable
                else "Reported quarter cannot be reproduced from supplied cumulative/prior facts.",
                "currency": inputs[0].currency,
                "checks": checks,
                "components": components,
                "amortization_difference": amort_difference,
                "cash_flow_net_income_difference": cf_income_difference,
                "measures": measures,
            }
        )
    return {"calculation_version": VERSION, "quarters": quarters}
