"""A sourced acquisition-contribution bridge, preserving residuals and research decisions."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .models import FactBundle, FinancialFact, Record

GROWTH_VERSION = "public-growth-bridge/1"
COMPONENTS = (
    "software_license_revenue",
    "maintenance_revenue",
    "saas_revenue",
    "professional_services_revenue",
)


class Disclosure(Record):
    evidence_id: str = Field(min_length=1)
    pdf_page: int = Field(ge=1)
    locator: str = Field(min_length=1)
    source_anchor: str = Field(min_length=1)
    classification: Literal["reported_disclosure", "unaudited_pro_forma_context"] = "reported_disclosure"
    reported_summary: str = Field(min_length=1)
    analytical_limit: str = Field(min_length=1)


class Contribution(Record):
    revenue_fact_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    reported_amount: Decimal = Field(ge=0)
    unit_scale: Literal[1, 1000, 1000000]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reported_resolution: Decimal = Field(gt=0)
    approximate: Literal[True] = True

    @model_validator(mode="after")
    def resolution(self) -> Self:
        if self.reported_amount % self.reported_resolution != 0:
            raise ValueError("contribution exceeds its declared source precision")
        return self

    @property
    def amount(self) -> Decimal:
        return self.reported_amount * self.unit_scale


class ResearchAssessment(Record):
    assessment_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    disposition: Literal["investigate", "defer", "reject"]
    rationale: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    population: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...] = Field(min_length=1)
    counterevidence_ids: tuple[str, ...] = Field(min_length=1)
    alternative_explanations: tuple[str, ...] = Field(min_length=1)
    evidence_needed: tuple[str, ...] = Field(min_length=1)
    falsification_or_reopen_test: str = Field(min_length=1)
    review_by: date
    author_role: Literal["research_author"] = "research_author"
    decision_scope: Literal["research_assessment_only"] = "research_assessment_only"


class GrowthContext(Record):
    schema_version: Literal[1] = 1
    financial_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquired_business: str = Field(min_length=1)
    acquired_on: date
    prior: Contribution
    current: Contribution
    revenue_mix: FactBundle
    disclosures: tuple[Disclosure, ...] = Field(min_length=1)
    assessments: tuple[ResearchAssessment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def references(self) -> Self:
        by_id = {d.evidence_id: d for d in self.disclosures}
        if len(by_id) != len(self.disclosures):
            raise ValueError("disclosure IDs must be unique")
        if len({a.assessment_id for a in self.assessments}) != len(self.assessments):
            raise ValueError("assessment IDs must be unique")
        for contribution in (self.prior, self.current):
            disclosure = by_id.get(contribution.evidence_id)
            if disclosure is None or disclosure.classification != "reported_disclosure":
                raise ValueError("acquired contribution needs reported evidence, not pro forma context")
        for assessment in self.assessments:
            if not set((*assessment.supporting_evidence_ids, *assessment.counterevidence_ids)) <= by_id.keys():
                raise ValueError("research assessment references unknown evidence")
            if assessment.review_by < self.revenue_mix.information_cutoff:
                raise ValueError("research assessment review date precedes the information cutoff")
        return self


def fingerprint(bundle: FactBundle) -> str:
    return hashlib.sha256(bundle.model_dump_json().encode()).hexdigest()


def analyze_growth(bundle: FactBundle, context: GrowthContext) -> dict[str, Any]:
    """Central-value arithmetic using disclosed rounded inputs; never an organic growth estimate."""
    bundle.require_public()
    mix = context.revenue_mix
    mix.require_public()
    if fingerprint(bundle) != context.financial_input_sha256:
        raise ValueError("growth context is bound to a different financial input revision")
    if (mix.entity_id, mix.ticker, mix.information_cutoff) != (
        bundle.entity_id,
        bundle.ticker,
        bundle.information_cutoff,
    ):
        raise ValueError("revenue mix entity or cutoff differs from the financial case")
    sources = {d.document_id: d for d in bundle.documents}
    source = sources.get(context.document_id)
    if source is None or source.sha256 != context.source_sha256:
        raise ValueError("growth disclosure source is not the registered document revision")
    if len(mix.documents) != 1 or mix.documents[0].document_id != context.document_id:
        raise ValueError("this growth exhibit requires a single reviewed annual filing")
    for doc in mix.documents:
        registered = sources.get(doc.document_id)
        if registered is None or (doc.entity_id, doc.accession, doc.sha256, doc.filed_on, doc.url) != (
            registered.entity_id,
            registered.accession,
            registered.sha256,
            registered.filed_on,
            registered.url,
        ):
            raise ValueError("revenue mix source differs from the registered filing")
    facts = {f.fact_id: f for f in bundle.facts}
    selected: list[FinancialFact] = []
    for contribution in (context.prior, context.current):
        fact = facts.get(contribution.revenue_fact_id)
        if fact is None or fact.metric != "revenue" or fact.period.basis != "annual":
            raise ValueError("growth bridge requires referenced annual reported revenue facts")
        if (
            fact.document_id != context.document_id
            or contribution.amount > fact.amount
            or fact.amount <= 0
            or contribution.currency != fact.currency
        ):
            raise ValueError("acquired contribution requires the same filing and cannot exceed revenue")
        if context.acquired_on > fact.period.end and contribution.amount != 0:
            raise ValueError("acquired contribution cannot precede the acquisition")
        selected.append(fact)
    prior, current = selected
    if current.period.start != prior.period.end + timedelta(days=1) or current.currency != prior.currency:
        raise ValueError("growth bridge requires consecutive same-currency annual periods")
    if context.acquired_on > source.filed_on:
        raise ValueError("acquisition occurs after the source filing")

    # The disaggregation remains a separate extraction with its own mapping hash.
    # Reconcile each period back to the original reported facts; never replace them.
    grouped: dict[tuple[date, date, str], list[FinancialFact]] = defaultdict(list)
    for fact in mix.facts:
        grouped[(fact.period.start, fact.period.end, fact.period.basis)].append(fact)
    mix_rows = []
    for key, rows in sorted(grouped.items()):
        by_metric = {f.metric: f for f in rows}
        if key[2] != "annual" or set(by_metric) != {"revenue", *COMPONENTS}:
            raise ValueError("revenue mix requires the complete annual four-component disaggregation")
        if len({f.currency for f in rows}) != 1 or any(f.amount < 0 for f in rows):
            raise ValueError("revenue mix requires nonnegative amounts and one currency")
        for row in rows:
            overlapping = [f for f in bundle.facts if f.metric == row.metric and f.period == row.period]
            if overlapping and (overlapping[0].amount, overlapping[0].currency) != (row.amount, row.currency):
                raise ValueError("revenue mix conflicts with an existing source fact")
        original = [
            f for f in bundle.facts if f.metric == "revenue" and (f.period.start, f.period.end, f.period.basis) == key
        ]
        total = by_metric["revenue"]
        if len(original) != 1 or (original[0].amount, original[0].currency, original[0].document_id) != (
            total.amount,
            total.currency,
            total.document_id,
        ):
            raise ValueError("revenue mix total does not match the original reported period")
        if total.amount <= 0 or sum(by_metric[m].amount for m in COMPONENTS) != total.amount:
            raise ValueError("revenue components do not reconcile to reported revenue")
        mix_rows.append(
            {
                "start": key[0],
                "end": key[1],
                "basis": key[2],
                "currency": total.currency,
                "total": total.amount,
                "original_revenue_fact_id": original[0].fact_id,
                "components": {
                    m: {
                        "amount": by_metric[m].amount,
                        "share": by_metric[m].amount / total.amount,
                        "fact_id": by_metric[m].fact_id,
                    }
                    for m in COMPONENTS
                },
            }
        )
    if not {prior.period.end, current.period.end} <= {r["end"] for r in mix_rows}:
        raise ValueError("revenue mix is missing a selected bridge period")

    acquired_change = context.current.amount - context.prior.amount
    reported_change = current.amount - prior.amount
    residual_prior = prior.amount - context.prior.amount
    residual_current = current.amount - context.current.amount
    return {
        "analysis_version": GROWTH_VERSION,
        "financial_input_sha256": fingerprint(bundle),
        "context_sha256": hashlib.sha256(context.model_dump_json().encode()).hexdigest(),
        "classification": "calculated_from_public_facts_and_rounded_disclosures",
        "currency": current.currency,
        "prior_period": prior.period.model_dump(mode="json"),
        "current_period": current.period.model_dump(mode="json"),
        "reported_prior": prior.amount,
        "reported_current": current.amount,
        "reported_change": reported_change,
        "reported_growth": reported_change / prior.amount,
        "acquired_prior": context.prior.amount,
        "acquired_current": context.current.amount,
        "acquired_change": acquired_change,
        "residual_prior": residual_prior,
        "residual_current": residual_current,
        "residual_change": residual_current - residual_prior,
        "residual_growth": (residual_current - residual_prior) / residual_prior if residual_prior > 0 else None,
        "organic_growth": None,
        "organic_growth_state": "unavailable: residual retains currency, other acquisitions, mix and timing",
        "acquired_earnings": None,
        "display_resolution": max(
            context.prior.reported_resolution * context.prior.unit_scale,
            context.current.reported_resolution * context.current.unit_scale,
        ),
        "precision_note": "Arithmetic uses published rounded inputs. Extra arithmetic digits are not additional source precision or confidence bounds.",
        "evidence_ids": [prior.fact_id, current.fact_id, context.prior.evidence_id, context.current.evidence_id],
        "revenue_mix": mix_rows,
        "context": context.model_dump(mode="json"),
    }


def verify_disclosure_source(pdf: Path, context: GrowthContext) -> None:
    """Optional offline source verification. Anchors locate reviewed prose, not inferred facts."""
    from pypdf import PdfReader

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != context.source_sha256:
        raise ValueError("disclosure PDF hash differs from the reviewed source")
    reader = PdfReader(pdf)
    for disclosure in context.disclosures:
        if disclosure.pdf_page > len(reader.pages):
            raise ValueError("disclosure page is absent")
        page = " ".join(reader.pages[disclosure.pdf_page - 1].extract_text().split())
        if " ".join(disclosure.source_anchor.split()) not in page:
            raise ValueError(f"reviewed disclosure anchor missing: {disclosure.evidence_id}")
