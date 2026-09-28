"""Historical enterprise-to-equity sensitivities with reconciled principal claims."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .balances import BalanceBundle
from .financials import analyze_facts
from .models import FactBundle, Record
from .scheduling import fingerprint
from .underwriting import money

REQUIRED = {
    "cash",
    "current_notes_net",
    "noncurrent_notes_net",
    "revolver",
    "current_notes_face",
    "noncurrent_notes_face",
    "long_term_face",
    "current_discount",
    "noncurrent_discount",
    "total_debt_net",
    "lease_current",
    "lease_noncurrent",
    "revolver_note",
}


class AssumedAmount(Record):
    amount: Decimal = Field(ge=0)
    classification: Literal["analyst_assumption"] = "analyst_assumption"
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def cents(self) -> Self:
        if self.amount != money(self.amount):
            raise ValueError("assumed currency amounts require whole-cent precision")
        return self


class EquityScenario(Record):
    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    label: str = Field(min_length=1)
    available_cash_fraction: Decimal = Field(ge=0, le=1)
    cash_rationale: str = Field(min_length=1)
    lease_treatment: Literal["exclude_after_rent_earnings", "deduct_as_sensitivity"]
    lease_rationale: str = Field(min_length=1)
    nonoperating_assets: AssumedAmount
    other_claims: AssumedAmount
    transaction_costs: AssumedAmount


class ValuationSpec(Record):
    schema_version: Literal[1] = 1
    classification: Literal["historical_public_facts_with_analyst_assumptions"]
    financial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    balances_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_date: date
    information_cutoff: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    earnings_measure: Literal["calculated_ebitda"]
    multiples: tuple[Decimal, ...] = Field(min_length=1)
    multiple_rationale: str = Field(min_length=1)
    convertible_settlement: Literal["cash_principal_only"]
    settlement_rationale: str = Field(min_length=1)
    unresolved_items: tuple[str, ...] = Field(min_length=1)
    scenarios: tuple[EquityScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if any(not m.is_finite() or m <= 0 for m in self.multiples) or len(set(self.multiples)) != len(self.multiples):
            raise ValueError("multiples must be positive, finite and unique")
        if len({s.scenario_id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("duplicate equity scenario")
        if self.historical_date > self.information_cutoff:
            raise ValueError("historical date exceeds information cutoff")
        return self


def analyze_valuation(facts: FactBundle, balances: BalanceBundle, spec: ValuationSpec) -> dict[str, Any]:
    facts.require_public()
    balances.require_public()
    if fingerprint(facts) != spec.financial_sha256 or fingerprint(balances) != spec.balances_sha256:
        raise ValueError("valuation requires the exact financial and balance revisions")
    if (facts.entity_id, facts.ticker, facts.information_cutoff) != (
        balances.entity_id,
        balances.ticker,
        balances.information_cutoff,
    ) or spec.information_cutoff != facts.information_cutoff:
        raise ValueError("valuation entity or information cutoff mismatch")
    original = next((d for d in facts.documents if d.document_id == balances.document.document_id), None)
    if original is None or any(
        getattr(original, k) != getattr(balances.document, k)
        for k in ("sha256", "url", "accession", "filed_on", "form")
    ):
        raise ValueError("valuation balances must use the exact registered financial filing")
    if {f.as_of for f in balances.facts} != {spec.historical_date} or {f.currency for f in balances.facts} != {
        spec.currency
    }:
        raise ValueError("valuation cannot mix balance dates or currencies")
    financial = analyze_facts(facts)
    matching = [p for p in financial["periods"] if p["basis"] == "annual" and p["end"] == str(spec.historical_date)]
    if len(matching) != 1 or matching[0]["currency"] != spec.currency:
        raise ValueError("valuation needs a same-date annual earnings anchor and currency")
    earnings = matching[0]["derived"]["ebitda"]
    by = {f.metric: f for f in balances.facts}
    missing = sorted(REQUIRED - by.keys())
    blockers = [f"Missing balance input: {m}" for m in missing]
    for metric, fact in by.items():
        if metric in REQUIRED and (
            (metric.endswith("discount") and fact.amount > 0) or (not metric.endswith("discount") and fact.amount < 0)
        ):
            blockers.append(f"Unexpected source sign: {metric}")
    rules = {
        "revolver": {"revolver_note": 1},
        "current_notes_net": {"current_notes_face": 1, "current_discount": 1},
        "noncurrent_notes_net": {"noncurrent_notes_face": 1, "noncurrent_discount": 1},
        "long_term_face": {"noncurrent_notes_face": 1, "revolver": 1},
        "total_debt_net": {"current_notes_net": 1, "noncurrent_notes_net": 1, "revolver": 1},
    }
    checks = []
    for target, operands in rules.items():
        absent = sorted(({target} | set(operands)) - by.keys())
        delta = (
            None
            if absent
            else by[target].amount - sum((by[m].amount * sign for m, sign in operands.items()), Decimal(0))
        )
        status = "unavailable" if absent else "matched" if delta == 0 else "mismatch"
        checks.append(
            {
                "target": target,
                "status": status,
                "difference": delta,
                "missing": absent,
                "fact_ids": [by[m].fact_id for m in (target, *operands) if m in by],
            }
        )
        if status != "matched":
            blockers.append(f"Debt reconciliation {status}: {target}")
    if earnings["value"] is None:
        blockers.append("Defined annual earnings bridge is unavailable")
    elif earnings["value"] <= 0:
        blockers.append("Positive earnings required for this multiple sensitivity")
    principal = None if missing else by["current_notes_face"].amount + by["long_term_face"].amount
    lease_total = None if missing else by["lease_current"].amount + by["lease_noncurrent"].amount
    scenarios = []
    for scenario in spec.scenarios:
        rows = []
        for multiple in spec.multiples:
            if blockers:
                rows.append(
                    {"multiple": multiple, "enterprise_value": None, "equity_sensitivity": None, "blocked_by": blockers}
                )
                continue
            assert principal is not None and lease_total is not None
            cash = money(by["cash"].amount * scenario.available_cash_fraction)
            leases = lease_total if scenario.lease_treatment == "deduct_as_sensitivity" else Decimal(0)
            ev = money(earnings["value"] * multiple)
            equity = (
                ev
                + cash
                + scenario.nonoperating_assets.amount
                - principal
                - leases
                - scenario.other_claims.amount
                - scenario.transaction_costs.amount
            )
            rows.append(
                {
                    "multiple": multiple,
                    "enterprise_value": ev,
                    "cash_added": cash,
                    "nonoperating_assets_added": scenario.nonoperating_assets.amount,
                    "debt_principal_deducted": principal,
                    "lease_claim_deducted": leases,
                    "other_claims_deducted": scenario.other_claims.amount,
                    "transaction_costs_deducted": scenario.transaction_costs.amount,
                    "equity_sensitivity": money(equity),
                    "blocked_by": [],
                }
            )
        scenarios.append({**scenario.model_dump(mode="json"), "rows": rows})
    return {
        "valuation_version": "historical-equity-bridge/1",
        "classification": spec.classification,
        "company": facts.company,
        "currency": spec.currency,
        "historical_date": spec.historical_date,
        "information_cutoff": spec.information_cutoff,
        "financial_sha256": fingerprint(facts),
        "balances_sha256": fingerprint(balances),
        "spec_sha256": fingerprint(spec),
        "earnings": earnings,
        "earnings_period": {k: matching[0][k] for k in ("start", "end", "basis")},
        "earnings_reconciliations": matching[0]["reconciliations"],
        "earnings_facts": [f.model_dump(mode="json") for f in facts.facts if f.fact_id in earnings["evidence_ids"]],
        "source_documents": [d.model_dump(mode="json") for d in facts.documents],
        "reconciliations": checks,
        "blocked_by": blockers,
        "debt_principal": principal,
        "debt_carrying_value": by["total_debt_net"].amount if "total_debt_net" in by else None,
        "lease_liabilities": lease_total,
        "scenarios": scenarios,
        "spec": spec.model_dump(mode="json"),
        "balances": balances.model_dump(mode="json"),
        "subsequent_events": [e.model_dump(mode="json") for e in facts.events if e.occurred_on > spec.historical_date],
        "current_equity_value": None,
        "per_share_value": None,
        "transaction_proceeds": None,
        "limitation": "Historical mechanical sensitivity assembled with later-filed information. Not a contemporaneous valuation, fair-value opinion, current share-price target or actual transaction. Operating initiative sensitivities are not added to reported company earnings.",
    }
