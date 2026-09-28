"""Metric-specific peer context: selection judgments never become operating targets."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any, Literal, Self

from pydantic import Field, HttpUrl, model_validator

from .growth import Disclosure, fingerprint
from .models import FactBundle, FinancialFact, FiscalPeriod, Record

Metric = Literal["operating_margin", "cash_margin", "organic_growth", "arr_growth"]
METRICS: tuple[Metric, ...] = ("operating_margin", "cash_margin", "organic_growth", "arr_growth")
LABELS = {
    "operating_margin": "GAAP operating margin",
    "cash_margin": "CFO less PP&E purchases / revenue",
    "organic_growth": "Organic revenue growth",
    "arr_growth": "ARR growth",
}


class Eligibility(Record):
    metric: Metric
    status: Literal["strict", "context_only", "exclude"]
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class Candidate(Record):
    candidate_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    filing_index: HttpUrl
    selection_rationale: str = Field(min_length=1)
    facts: FactBundle | None = None
    disclosures: tuple[Disclosure, ...] = ()
    operating_expense_components: tuple[str, ...] = ()
    eligibility: tuple[Eligibility, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.filing_index.scheme != "https":
            raise ValueError("filing reference requires HTTPS")
        if len(self.eligibility) != len(METRICS) or {e.metric for e in self.eligibility} != set(METRICS):
            raise ValueError("each candidate needs exactly one decision per metric")
        ids = {d.evidence_id for d in self.disclosures}
        if len(ids) != len(self.disclosures):
            raise ValueError("duplicate disclosure IDs")
        if len(set(self.operating_expense_components)) != len(self.operating_expense_components):
            raise ValueError("duplicate operating expense components")
        if any(not set(e.evidence_ids) <= ids | {"filing_index"} for e in self.eligibility):
            raise ValueError("eligibility must reference registered evidence")
        if self.facts is None:
            if any(e.status != "exclude" for e in self.eligibility):
                raise ValueError("unverified source cannot enter a numeric cohort")
        elif (self.facts.entity_id, self.facts.company) != (self.entity_id, self.company):
            raise ValueError("candidate identity differs from its source bundle")
        elif len(self.facts.documents) != 1:
            raise ValueError("peer disclosures require one explicitly selected annual filing")
        if any(e.metric in ("organic_growth", "arr_growth") and e.status != "exclude" for e in self.eligibility):
            raise ValueError("growth definitions are not supported by this version")
        return self


class PeerContext(Record):
    schema_version: Literal[1] = 1
    financial_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    focal_cash_reconciliation: FactBundle
    anchor: FiscalPeriod
    selection_as_of: date
    selection_rules: tuple[str, ...] = Field(min_length=1)
    max_end_difference_days: Literal[183] = 183
    max_duration_difference_days: Literal[7] = 7
    minimum_median_count: Literal[3] = 3
    candidates: tuple[Candidate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> Self:
        if self.anchor.basis != "annual":
            raise ValueError("peer anchor must be annual")
        for field in ("candidate_id", "entity_id"):
            if len({getattr(c, field) for c in self.candidates}) != len(self.candidates):
                raise ValueError("duplicate peer identity")
        return self


def _measure(facts: list[FinancialFact], metric: Metric, components: tuple[str, ...] = ()) -> dict[str, Any]:
    by = {f.metric: f for f in facts}
    needed = {"revenue"}
    if metric == "operating_margin":
        needed |= {"cost_of_revenue", "gross_profit", "operating_income"}
        needed |= set(components) if components else {"operating_expense"}
    elif metric == "cash_margin":
        needed |= {"operating_cash_flow", "ppe_purchases", "net_income", "cash_flow_net_income"}
    else:
        return {
            "value": None,
            "blocked_by": ["Comparable growth definition and perimeter not established"],
            "evidence_ids": [],
        }
    missing = sorted(needed - by.keys())
    blockers = [f"Missing {m}" for m in missing]
    if not missing:
        if by["revenue"].amount <= 0:
            blockers.append("Revenue must be positive")
        if metric == "operating_margin":
            if by["revenue"].amount - by["cost_of_revenue"].amount != by["gross_profit"].amount:
                blockers.append("Revenue / gross profit reconciliation mismatch")
            opex = sum((by[m].amount for m in components), Decimal(0)) if components else by["operating_expense"].amount
            if by["gross_profit"].amount - opex != by["operating_income"].amount:
                blockers.append("Operating income reconciliation mismatch")
            numerator = by["operating_income"].amount
        else:
            if by["ppe_purchases"].amount > 0:
                blockers.append("PP&E purchases require a signed nonpositive outflow")
            if by["net_income"].amount != by["cash_flow_net_income"].amount:
                blockers.append("Cash flow net income reconciliation mismatch")
            numerator = by["operating_cash_flow"].amount + by["ppe_purchases"].amount
    return {
        "value": None if blockers else numerator / by["revenue"].amount,
        "blocked_by": blockers,
        "evidence_ids": [by[m].fact_id for m in sorted(needed) if m in by],
    }


def analyze_peers(bundle: FactBundle, context: PeerContext) -> dict[str, Any]:
    bundle.require_public()
    if fingerprint(bundle) != context.financial_input_sha256:
        raise ValueError("peer context requires the exact financial bundle")
    if context.selection_as_of != bundle.information_cutoff:
        raise ValueError("peer selection cutoff differs from focal cutoff")
    annual = [f.period for f in bundle.facts if f.period.basis == "annual"]
    if not annual or context.anchor != max(annual, key=lambda p: (p.end, p.start)):
        raise ValueError("peer anchor must match the latest sourced annual period")
    focal = [f for f in bundle.facts if f.period == context.anchor]
    supplement = context.focal_cash_reconciliation
    supplement.require_public()
    if (supplement.entity_id, supplement.information_cutoff) != (bundle.entity_id, bundle.information_cutoff):
        raise ValueError("focal cash reconciliation identity or cutoff mismatch")
    documents = {d.document_id: d for d in bundle.documents}
    for doc in supplement.documents:
        original = documents.get(doc.document_id)
        if original is None or any(
            getattr(doc, field) != getattr(original, field)
            for field in ("sha256", "url", "accession", "filed_on", "form")
        ):
            raise ValueError("focal cash reconciliation must use the exact registered filing")
    if any(f.metric != "cash_flow_net_income" or f.period not in annual for f in supplement.facts):
        raise ValueError("focal supplement may only add annual cash flow net income")
    additions = [f for f in supplement.facts if f.period == context.anchor]
    if any(f.metric == "cash_flow_net_income" for f in focal):
        existing = next(f for f in focal if f.metric == "cash_flow_net_income")
        if not additions or existing.amount != additions[0].amount or existing.currency != additions[0].currency:
            raise ValueError("focal cash reconciliation conflicts with original fact")
    else:
        focal += additions
    if {f.currency for f in focal} != {"USD"}:
        raise ValueError("this peer context requires a USD focal period")
    observations: list[dict[str, Any]] = []
    for candidate in context.candidates:
        if candidate.entity_id == bundle.entity_id:
            raise ValueError("focal company cannot be counted as its own peer")
        selected = None
        values: list[FinancialFact] = []
        technical = []
        if candidate.facts is None:
            technical.append("Source bytes and mapped facts not verified")
        else:
            peer = candidate.facts
            peer.require_public()
            if peer.information_cutoff != bundle.information_cutoff:
                raise ValueError("peer information cutoff differs from focal cutoff")
            if peer.documents[0].form not in ("10-K", "40-F"):
                raise ValueError("peer source must be an annual filing")
            periods = {(f.period.start, f.period.end): f.period for f in peer.facts if f.period.basis == "annual"}
            if periods:
                # Latest end wins an equal-distance tie; fiscal labels never select a period.
                selected = min(
                    periods.values(), key=lambda p: (abs((p.end - context.anchor.end).days), -p.end.toordinal())
                )
                values = [f for f in peer.facts if f.period == selected]
                if abs((selected.end - context.anchor.end).days) > context.max_end_difference_days:
                    technical.append("Annual end outside 183-day window")
                if (
                    abs((selected.end - selected.start).days - (context.anchor.end - context.anchor.start).days)
                    > context.max_duration_difference_days
                ):
                    technical.append("Annual duration differs by more than seven days")
                if {f.currency for f in values} != {"USD"}:
                    technical.append("Currency differs from USD focal period")
            else:
                technical.append("No annual facts")
        decisions = {}
        for decision in candidate.eligibility:
            calculation = _measure(values, decision.metric, candidate.operating_expense_components)
            blockers = technical + calculation["blocked_by"]
            if decision.status == "exclude":
                blockers.append("Excluded by recorded metric eligibility")
            decisions[decision.metric] = {
                **decision.model_dump(mode="json"),
                "value": None if blockers else calculation["value"],
                "blocked_by": blockers,
                "fact_ids": calculation["evidence_ids"],
            }
        observations.append(
            {
                "candidate_id": candidate.candidate_id,
                "company": candidate.company,
                "period": selected.model_dump(mode="json") if selected else None,
                "metrics": decisions,
            }
        )
    metrics = {}
    for metric in METRICS:
        cohorts = {}
        for name, allowed in (("all_eligible", {"strict", "context_only"}), ("strict", {"strict"})):
            members = [
                o
                for o in observations
                if o["metrics"][metric]["status"] in allowed and o["metrics"][metric]["value"] is not None
            ]
            vals = [o["metrics"][metric]["value"] for o in members]
            cohorts[name] = {
                "count": len(vals),
                "candidate_ids": [o["candidate_id"] for o in members],
                "median": median(vals) if len(vals) >= context.minimum_median_count else None,
                "withheld_reason": None
                if len(vals) >= context.minimum_median_count
                else "Fewer than three eligible observations",
            }
        metrics[metric] = {"label": LABELS[metric], "focal": _measure(focal, metric), "cohorts": cohorts}
    return {
        "analysis_version": "metric-peer-context/1",
        "financial_input_sha256": fingerprint(bundle),
        "context_sha256": hashlib.sha256(context.model_dump_json().encode()).hexdigest(),
        "anchor": context.anchor.model_dump(mode="json"),
        "metrics": metrics,
        "observations": observations,
        "context": context.model_dump(mode="json"),
        "operating_target": None,
        "limitation": "Descriptive sample, not a representative benchmark, valuation or executable savings estimate. Cash measure excludes acquisitions and financing and is not complete free cash flow.",
    }
