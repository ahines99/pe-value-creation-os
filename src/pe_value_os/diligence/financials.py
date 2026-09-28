"""Reconcile reported statements before deriving explicitly named earnings and cash measures."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, TypedDict

from .models import FactBundle, FinancialFact

ANALYSIS_VERSION = "public-financial-baseline/2"

# Signs are the filing's displayed signs. Interest expense and PP&E purchases are negative.
RECONCILIATIONS = {
    "gross_profit": {"revenue": 1, "cost_of_revenue": -1},
    "operating_income": {"gross_profit": 1, "operating_expense": -1},
    "pretax_income": {"operating_income": 1, "other_expense_net": 1},
    "net_income": {"pretax_income": 1, "income_tax_expense": -1},
    "other_expense_net": {"interest_expense": 1, "interest_income_other": 1, "fx_loss": 1},
    "intangible_amortization": {"amortization_cost_of_revenue": 1, "amortization_operating_expense": 1},
}


class MeasureSpec(TypedDict):
    label: str
    formula: dict[str, int]
    definition: str
    blocking_checks: tuple[str, ...]


DERIVED: dict[str, MeasureSpec] = {
    "ebitda": {
        "blocking_checks": (
            "revenue",
            "gross_profit",
            "operating_income",
            "pretax_income",
            "net_income",
            "other_expense_net",
            "intangible_amortization",
            "cash_flow_net_income",
        ),
        "label": "Calculated EBITDA (not issuer-adjusted EBITDA)",
        "formula": {
            "net_income": 1,
            "income_tax_expense": 1,
            "interest_expense": -1,
            "ppe_depreciation": 1,
            "intangible_amortization": 1,
        },
        "definition": "Net income plus tax provision, interest expense and operating depreciation/amortization. Debt discount amortization is already within interest expense and is not added twice. Other non-operating income/loss remains included. No restructuring, acquisition, stock-compensation or cyber adjustment is added.",
    },
    "operating_income_before_da": {
        "blocking_checks": ("revenue", "gross_profit", "operating_income", "intangible_amortization"),
        "label": "Operating income plus operating D&A",
        "formula": {"operating_income": 1, "ppe_depreciation": 1, "intangible_amortization": 1},
        "definition": "A separate operating earnings bridge; differs from the net-income-based EBITDA measure by non-interest, non-tax non-operating items.",
    },
    "cfo_less_ppe": {
        "blocking_checks": ("cash_flow_net_income",),
        "label": "Reported operating cash flow less PP&E purchases",
        "formula": {"operating_cash_flow": 1, "ppe_purchases": 1},
        "definition": "Historical reported CFO plus the signed PP&E cash outflow. Excludes acquisitions and financing; not a complete discretionary-cash or initiative-savings measure.",
    },
}


def analyze_facts(bundle: FactBundle) -> dict[str, Any]:
    bundle.require_public()
    groups: dict[tuple[str, str, str], list[FinancialFact]] = defaultdict(list)
    for fact in bundle.facts:
        groups[(fact.period.start.isoformat(), fact.period.end.isoformat(), fact.period.basis)].append(fact)
    periods = []
    for (start, end, basis), facts in sorted(groups.items()):
        if len({f.currency for f in facts}) != 1 or len({f.accounting_basis for f in facts}) != 1:
            raise ValueError("a financial bridge cannot combine currencies or accounting bases")
        by_metric = {f.metric: f for f in facts}
        for metric in ("interest_expense", "ppe_purchases"):
            if metric in by_metric and by_metric[metric].amount > 0:
                raise ValueError(f"{metric} requires a signed nonpositive outflow; review source mapping")
        checks = []
        rules = dict(RECONCILIATIONS)
        if "cash_flow_net_income" in by_metric:
            rules["cash_flow_net_income"] = {"net_income": 1}
        if {"software_license_revenue", "maintenance_saas_services_revenue"} <= by_metric.keys():
            rules["revenue"] = {"software_license_revenue": 1, "maintenance_saas_services_revenue": 1}
        for target, operands in rules.items():
            missing = sorted(({target} | set(operands)) - by_metric.keys())
            delta = (
                None
                if missing
                else by_metric[target].amount - sum(by_metric[m].amount * s for m, s in operands.items())
            )
            checks.append(
                {
                    "target": target,
                    "missing": missing,
                    "difference": delta,
                    "status": "unavailable" if missing else "matched" if delta == 0 else "mismatch",
                }
            )
        # Block dependent measures; an amortization definition dispute is not a cash-flow dispute.
        mismatches = [c["target"] for c in checks if c["status"] == "mismatch"]
        derived = {}
        for name, spec in DERIVED.items():
            operands = spec["formula"]
            missing = sorted(set(operands) - by_metric.keys())
            blocked = [m for m in mismatches if m in spec["blocking_checks"]]
            value = (
                None if missing or blocked else sum((by_metric[m].amount * s for m, s in operands.items()), Decimal(0))
            )
            derived[name] = {
                **spec,
                "value": value,
                "classification": "calculated_from_public_facts",
                "missing": missing,
                "blocked_by": blocked,
                "evidence_ids": [by_metric[m].fact_id for m in operands if m in by_metric],
            }
        periods.append(
            {
                "start": start,
                "end": end,
                "basis": basis,
                "currency": facts[0].currency,
                "reported": {m: {"value": f.amount, "fact_id": f.fact_id} for m, f in by_metric.items()},
                "reconciliations": checks,
                "derived": derived,
            }
        )
    return {
        "analysis_version": ANALYSIS_VERSION,
        "input_sha256": hashlib.sha256(bundle.model_dump_json().encode()).hexdigest(),
        "company": bundle.company,
        "ticker": bundle.ticker,
        "entity_id": bundle.entity_id,
        "information_cutoff": bundle.information_cutoff.isoformat(),
        "mode": "public_filing_diligence",
        "financial_review": "not independently reviewed",
        "operating_opportunities": "not sized from consolidated statements",
        "periods": periods,
        "documents": [d.model_dump(mode="json") for d in bundle.documents],
    }
