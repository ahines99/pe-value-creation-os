"""A constructed investment-level exit sensitivity, separate from scoped operating claims."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .balances import BalanceBundle
from .models import FactBundle, Record
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import SourceCasePayload
from .underwriting import money, month_end
from .underwriting_models import UnderwritingModel
from .valuation import ValuationSpec, analyze_valuation


class ExitAssumptions(Record):
    schema_version: Literal[1] = 1
    classification: Literal["constructed_exit_sensitivity"]
    case_id: str = Field(min_length=1)
    reference_company_label: str = Field(min_length=1)
    public_entity_id: str = Field(min_length=1)
    financial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    balances_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_valuation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exit_on: date
    entry_multiple: Decimal = Field(gt=0)
    terminal_multiples: tuple[Decimal, ...] = Field(min_length=1)
    terminal_earnings_factors: tuple[Decimal, ...] = Field(min_length=1)
    historical_claim_scenario: str = Field(min_length=1)
    multiple_rationale: str = Field(min_length=1)
    earnings_rationale: str = Field(min_length=1)
    capital_structure_treatment: Literal["hold_historical_claims_constant"]
    capital_structure_rationale: str = Field(min_length=1)
    operating_scope_treatment: Literal["do_not_add_scoped_operating_forecast"]
    operating_scope_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def finite_scenarios(self) -> Self:
        if not self.entry_multiple.is_finite() or any(not m.is_finite() or m <= 0 for m in self.terminal_multiples):
            raise ValueError("exit multiples must be positive and finite")
        if any(not f.is_finite() for f in self.terminal_earnings_factors):
            raise ValueError("exit earnings factors must be finite")
        if len(set(self.terminal_multiples)) != len(self.terminal_multiples) or len(
            set(self.terminal_earnings_factors)
        ) != len(self.terminal_earnings_factors):
            raise ValueError("exit sensitivity coordinates must be unique")
        return self


class ExitReviewPayload(Record):
    # Composition preserves every signed v1/v2 payload byte. Nothing is added to
    # old contracts, and the full public/constructed inputs remain distinguishable.
    schema_version: Literal[3]
    source_basis: SourceCasePayload
    public_facts: FactBundle
    public_balances: BalanceBundle
    historical_valuation: ValuationSpec
    exit_assumptions: ExitAssumptions

    @property
    def underwriting(self) -> UnderwritingModel:
        return self.source_basis.underwriting

    @property
    def operating_plan(self) -> OperatingPlan:
        return self.source_basis.operating_plan

    @model_validator(mode="after")
    def scope(self) -> Self:
        self.public_facts.require_public()
        self.public_balances.require_public()
        spec = self.exit_assumptions
        if (
            self.underwriting.case_id != spec.case_id
            or self.underwriting.currency != self.historical_valuation.currency
        ):
            raise ValueError("exit assumptions must retain the case and currency")
        if (
            spec.reference_company_label != self.underwriting.company
            or spec.public_entity_id != self.public_facts.entity_id
        ):
            raise ValueError("exit public reference must match the underwriting reference company")
        if (
            fingerprint(self.public_facts),
            fingerprint(self.public_balances),
            fingerprint(self.historical_valuation),
        ) != (spec.financial_sha256, spec.balances_sha256, spec.historical_valuation_sha256):
            raise ValueError("exit assumptions must bind exact public inputs")
        if spec.exit_on != month_end(self.underwriting.start, self.underwriting.months - 1):
            raise ValueError("constructed exit must use the existing comparison horizon end")
        if self.historical_valuation.historical_date >= self.underwriting.start:
            raise ValueError("historical anchor must precede the constructed operating calendar")
        if spec.entry_multiple not in self.historical_valuation.multiples:
            raise ValueError("entry multiple must be present in the historical sensitivity")
        if spec.historical_claim_scenario not in {s.scenario_id for s in self.historical_valuation.scenarios}:
            raise ValueError("exit requires an explicit historical claim scenario")
        # Validates identity and hashes; missing or mismatched facts remain visible
        # as blocked calculations rather than being invented to complete a matrix.
        analyze_valuation(self.public_facts, self.public_balances, self.historical_valuation)
        return self


def exit_payload(payload: Any) -> ExitReviewPayload | None:
    if isinstance(payload, ExitReviewPayload):
        return payload
    nested = getattr(payload, "exit_basis", None)
    return nested if isinstance(nested, ExitReviewPayload) else None


def evaluate_exit(payload: ExitReviewPayload, financial: dict[str, Any]) -> dict[str, Any]:
    """Decompose the enterprise mark; retain historical claims and unavailable proceeds."""
    spec = payload.exit_assumptions
    public = analyze_valuation(payload.public_facts, payload.public_balances, payload.historical_valuation)
    claim_case = next(s for s in public["scenarios"] if s["scenario_id"] == spec.historical_claim_scenario)
    anchor = next(r for r in claim_case["rows"] if Decimal(str(r["multiple"])) == spec.entry_multiple)
    rows = []
    for factor in spec.terminal_earnings_factors:
        for multiple in spec.terminal_multiples:
            blockers = list(public["blocked_by"])
            starting = public["earnings"]["value"]
            terminal = None if starting is None else money(starting * factor)
            if terminal is not None and terminal <= 0:
                blockers.append("Nonpositive terminal earnings do not support this multiple valuation")
            row: dict[str, Any] = {
                "earnings_factor": factor,
                "multiple": multiple,
                "terminal_ebitda_sensitivity": terminal,
                "enterprise_value_sensitivity": None,
                "equity_sensitivity": None,
                "ev_change": None,
                "decomposition": None,
                "blocked_by": blockers,
            }
            if not blockers:
                assert starting is not None and terminal is not None
                change = terminal - starting
                multiple_change = multiple - spec.entry_multiple
                ev = money(terminal * multiple)
                delta = ev - anchor["enterprise_value"]
                parts = {
                    "earnings_change_at_entry_multiple": money(change * spec.entry_multiple),
                    "multiple_change_on_starting_earnings": money(starting * multiple_change),
                    "earnings_multiple_interaction": money(change * multiple_change),
                }
                parts["rounding_residual"] = delta - sum(parts.values(), Decimal(0))
                claims = {
                    k: anchor[k]
                    for k in (
                        "cash_added",
                        "nonoperating_assets_added",
                        "debt_principal_deducted",
                        "lease_claim_deducted",
                        "other_claims_deducted",
                        "transaction_costs_deducted",
                    )
                }
                equity = money(
                    ev
                    + claims["cash_added"]
                    + claims["nonoperating_assets_added"]
                    - sum(
                        claims[k]
                        for k in (
                            "debt_principal_deducted",
                            "lease_claim_deducted",
                            "other_claims_deducted",
                            "transaction_costs_deducted",
                        )
                    )
                )
                row.update(
                    enterprise_value_sensitivity=ev,
                    equity_sensitivity=equity,
                    ev_change=delta,
                    decomposition=parts,
                    claims=claims,
                    equity_change=equity - anchor["equity_sensitivity"],
                )
            rows.append(row)
    operating = []
    for scenario in financial["scenarios"]:
        terminal_month = scenario["monthly"][-1]
        operating.append(
            {
                "scenario_id": scenario["scenario_id"],
                "terminal_month": terminal_month,
                "included_in_company_exit_earnings": False,
                "maintainable_annual_uplift": None,
                "reason": "A scoped constructed forecast is not a consolidated maintainable-earnings bridge. No continuation beyond contract terms or supported vendor release is inferred.",
            }
        )
    return {
        "calculation_version": "constructed-exit-review/1",
        "classification": spec.classification,
        "payload_sha256": fingerprint(payload),
        "assumptions_sha256": fingerprint(spec),
        "historical_reference": public,
        "entry_anchor": anchor,
        "claim_scenario": claim_case,
        "assumptions": spec.model_dump(mode="json"),
        "rows": rows,
        "operating_scope_review": operating,
        "transaction_proceeds": None,
        "shareholder_distributions": None,
        "actual_exit_date": None,
        "current_company_valuation": None,
        "investment_return": None,
        "authority": "Constructed investment-level sensitivity with historical public anchors and analyst-assumed earnings/multiples. No transaction, sale decision, actual investment return or company endorsement.",
        "limitations": [
            "The FY2025 anchor predates Domo; no future consolidated perimeter or capital structure has been projected.",
            "Earnings factors are authored sensitivity inputs, not probabilities, forecasts or observed operating improvements.",
            "Historical debt, cash, lease and other-claim assumptions are held constant; scoped cash generation does not pay down debt or increase available cash here.",
            "Multiple effects and interaction are investment-level arithmetic and are never attributed to operating initiatives.",
            "Exit consideration, settlement terms, ownership/dilution, fees, taxes and distribution evidence are required before any proceeds or return claim.",
        ],
    }
