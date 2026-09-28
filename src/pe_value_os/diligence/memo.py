"""A version-bound executive packet assembled from the existing analytical engines."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .balances import BalanceBundle
from .financials import DERIVED, analyze_facts
from .growth import GrowthContext, analyze_growth
from .memo_review import MemoReviewContext, challenge_options
from .models import FactBundle, Record
from .peers import PeerContext, analyze_peers
from .scheduling import OperatingPlan, evaluate_plan, fingerprint
from .underwriting import UnderwritingCase
from .valuation import ValuationSpec, analyze_valuation


class ThesisPoint(Record):
    point_id: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    counterargument: str = Field(min_length=1)
    next_test: str = Field(min_length=1)


class AdjustmentReview(Record):
    fact_id: str = Field(min_length=1)
    disposition: Literal["retain_expense", "already_in_bridge", "scope_unresolved"]
    rationale: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)


class SequenceOption(Record):
    option_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    label: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority_order: tuple[str, ...] = Field(min_length=1)
    challenge: str = Field(min_length=1)


class DecisionBrief(Record):
    schema_version: Literal[2] = 2
    classification: Literal["public_research_with_constructed_exercise"]
    author_role: Literal["research_author"] = "research_author"
    as_of: date
    financial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    growth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    peers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    underwriting_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    balances_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    valuation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recommendation: str = Field(min_length=1)
    thesis: tuple[ThesisPoint, ...] = Field(min_length=1)
    adjustment_review: tuple[AdjustmentReview, ...] = Field(min_length=1)
    options: tuple[SequenceOption, ...] = Field(min_length=2)
    preferred_constructed_option: str
    conditional_choice_reason: str = Field(min_length=1)
    reopen_choice_if: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> Self:
        for values in (
            [p.point_id for p in self.thesis],
            [o.option_id for o in self.options],
            [a.fact_id for a in self.adjustment_review],
        ):
            if len(values) != len(set(values)):
                raise ValueError("brief record identities must be unique")
        if self.preferred_constructed_option not in {o.option_id for o in self.options}:
            raise ValueError("preferred option must be a registered constructed alternative")
        return self


def assemble_memo(
    brief: DecisionBrief,
    facts: FactBundle,
    growth: GrowthContext,
    peers: PeerContext,
    underwriting: UnderwritingCase,
    plan: OperatingPlan,
    balances: BalanceBundle,
    valuation: ValuationSpec,
    case_review: MemoReviewContext | None = None,
) -> dict[str, Any]:
    bindings = {
        "financial": facts,
        "growth": growth,
        "peers": peers,
        "underwriting": underwriting,
        "plan": plan,
        "balances": balances,
        "valuation": valuation,
    }
    for key, source in bindings.items():
        if getattr(brief, f"{key}_sha256") != fingerprint(source):
            raise ValueError(f"decision brief requires the exact {key} revision")
    if brief.as_of != facts.information_cutoff:
        raise ValueError("memo must retain the public information cutoff")
    if underwriting.start <= brief.as_of:
        raise ValueError("this proposed exercise must start after the public information cutoff")
    facts.require_public()
    underwriting.require_public()
    plan.bind(underwriting)
    financial = analyze_facts(facts)
    financial["context_events"] = [event.model_dump(mode="json") for event in facts.events]
    growth_result = analyze_growth(facts, growth)
    peer_result = analyze_peers(facts, peers)
    historical_valuation = analyze_valuation(facts, balances, valuation)
    by_fact = {f.fact_id: f for f in facts.facts}
    evidence = (
        set(by_fact)
        | {d.document_id for d in facts.documents}
        | {d.evidence_id for d in growth.disclosures}
        | {a.assessment_id for a in growth.assessments}
        | {"peer-context"}
    )
    for point in brief.thesis:
        if not set(point.evidence_ids) <= evidence:
            raise ValueError("thesis point references unregistered evidence")
    adjustments = []
    for item in brief.adjustment_review:
        if item.fact_id not in by_fact:
            raise ValueError("adjustment review references an unknown financial fact")
        fact = by_fact[item.fact_id]
        period = next(
            p
            for p in financial["periods"]
            if p["start"] == str(fact.period.start)
            and p["end"] == str(fact.period.end)
            and p["basis"] == fact.period.basis
        )
        if item.disposition == "already_in_bridge" and (
            fact.metric not in set(DERIVED["ebitda"]["formula"]) | {"debt_amortization"}
            or period["derived"]["ebitda"]["value"] is None
        ):
            raise ValueError("already-in-bridge treatment requires a supported component and available earnings bridge")
        if item.disposition == "scope_unresolved" and not any(
            c["target"] == fact.metric and c["status"] == "mismatch" for c in period["reconciliations"]
        ):
            raise ValueError("unresolved scope entry requires a recorded reconciliation mismatch")
        adjustments.append(
            {
                **item.model_dump(mode="json"),
                "metric": fact.metric,
                "period": fact.period.model_dump(mode="json"),
                "reported_amount": fact.amount,
                "currency": fact.currency,
                "pdf_page": fact.pdf_page,
                "document_id": fact.document_id,
                "accepted_addback": None,
            }
        )
    annual = [p for p in financial["periods"] if p["basis"] == "annual"]
    latest = annual[-1]
    if latest["currency"] != underwriting.currency:
        raise ValueError("memo currency must be consistent; no silent currency translation")
    options = []
    for option in brief.options:
        raw = plan.model_dump(mode="json")
        raw.update(
            priority_order=list(option.priority_order),
            revision_id=f"{plan.revision_id}:{option.option_id}",
            sequencing_rationale=option.rationale,
        )
        proposed = OperatingPlan.model_validate(raw)
        evaluated = evaluate_plan(proposed, underwriting)
        blocked = [t["task_id"] for t in evaluated["tasks"] if t["status"] == "blocked"]
        options.append(
            {
                **option.model_dump(mode="json"),
                "feasible": not blocked,
                "blocked_tasks": blocked,
                "plan": proposed.model_dump(mode="json"),
                "analysis": evaluated,
            }
        )
    preferred = next(o for o in options if o["option_id"] == brief.preferred_constructed_option)
    status = "conditional_research_preference" if preferred["feasible"] else "reopen_blocked_preference"
    review = challenge_options(case_review, underwriting, plan, options) if case_review is not None else None
    if review is not None:
        status = review["status"]
    # The reported and incremental layers are intentionally separate objects. No sum is emitted.
    return {
        "memo_version": "executive-decision-packet/4"
        if review and "exit_review" in review["latest_financials"]
        else "executive-decision-packet/3"
        if review
        else "executive-decision-packet/2",
        "brief_sha256": fingerprint(brief),
        "input_hashes": {
            **{k: fingerprint(v) for k, v in bindings.items()},
            **({"case_review": fingerprint(case_review)} if case_review else {}),
        },
        "classification": brief.classification,
        "company": facts.company,
        "as_of": brief.as_of,
        "brief": brief.model_dump(mode="json"),
        "public_financials": financial,
        "public_growth": growth_result,
        "public_peers": peer_result,
        "public_baseline": latest,
        "source_documents": [d.model_dump(mode="json") for d in facts.documents],
        "source_facts": {key: value.model_dump(mode="json") for key, value in by_fact.items()},
        "adjustment_review": adjustments,
        "normalized_ebitda": None,
        "company_equity_value": None,
        "historical_valuation": historical_valuation,
        "constructed_options": options,
        "preference_status": status,
        "source_review": review,
        "execution_authorized": False,
        "actual_realized_value": None,
        "authority": "Research-author judgment and constructed operating exercise; no company participation, management approval, independent practitioner review or actual financial result.",
        "valuation_limit": "Constructed year-two incremental EV sensitivities are separate from the historical company EV-to-equity sensitivity. Neither establishes current equity value, transaction proceeds or sourced market multiples; fictional operating uplift is never added to company earnings.",
    }
