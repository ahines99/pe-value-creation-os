"""Opportunity proposers.

`RuleBasedProposer` turns screening-threshold breaches into proposals using policy defaults (PVC-043). The
model-backed proposer in `pe_value_os.llm.proposer` implements the same protocol (PVC-072). Proposers only
name baseline metrics and propose scenario rates; the server derives baseline values and flow-through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from ..domain.ai_ops import AiAssessment
from ..domain.metrics import SaasMetrics
from ..domain.models import Confidence, FindingType
from ..domain.pricing import PriceWaterfall
from ..domain.project_models import Lever, OpportunityProposal
from ..domain.retention import RetentionAnalysis
from ..policy import PolicyConfig


@dataclass
class DraftFinding:
    """A finding before it is persisted; the step assigns ids and run context."""

    key: str
    finding_type: FindingType
    title: str
    statement: str
    confidence: Confidence
    evidence_ids: list[str]
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BranchContext:
    analysis: str
    company_id: str
    policy: PolicyConfig
    result: Any  # SaasMetrics | PriceWaterfall | RetentionAnalysis | AiAssessment
    findings: list[DraftFinding]
    evidence_ids: list[str]
    documents: list[dict[str, str]] = field(default_factory=list)  # untrusted text, delimited by the model layer
    report: dict[str, Any] = field(default_factory=dict)  # proposer diagnostics (rejections, usage) for audit


class Proposer(Protocol):
    name: str

    def propose(self, ctx: BranchContext) -> list[OpportunityProposal]: ...


def _pct(x: Decimal | None) -> str:
    return "n/a" if x is None else f"{(x * 100).quantize(Decimal('0.1'))}%"


def _proposal(policy: PolicyConfig, template: str, **kw: Any) -> OpportunityProposal:
    low, base, high = policy.proposal_defaults[template].scenarios()
    cost = policy.proposal_costs[template]
    return OpportunityProposal(
        low=low, base=base, high=high, annual_run_cost=cost.annual_run, one_time_cost=cost.one_time, **kw
    )


# --- findings: deterministic observations from each analysis --------------------------------------------------
def unit_economics_findings(m: SaasMetrics, policy: PolicyConfig) -> list[DraftFinding]:
    s = policy.screening
    out: list[DraftFinding] = []

    def ev(name: str) -> list[str]:
        return m.metrics[name].evidence_ids

    payback = m.value("cac_payback_months")
    if payback is not None and payback > s.cac_payback_months_max:
        out.append(
            DraftFinding(
                "cac_payback",
                FindingType.OBSERVATION,
                "CAC payback above policy threshold",
                f"CAC payback is {payback:.1f} months against a policy maximum of {s.cac_payback_months_max}.",
                Confidence.MEDIUM,
                ev("cac_payback_months"),
            )
        )
    magic = m.value("magic_number")
    if magic is not None and magic < s.magic_number_min:
        out.append(
            DraftFinding(
                "magic_number",
                FindingType.OBSERVATION,
                "Magic number below policy threshold",
                f"Magic number is {magic} against a policy minimum of {s.magic_number_min}.",
                Confidence.MEDIUM,
                ev("magic_number"),
            )
        )
    gm = m.value("subscription_gross_margin")
    if gm is not None and gm < s.subscription_gross_margin_min:
        out.append(
            DraftFinding(
                "gross_margin",
                FindingType.OBSERVATION,
                "Subscription gross margin below policy",
                f"Subscription gross margin is {_pct(gm)} against a policy minimum of "
                f"{_pct(s.subscription_gross_margin_min)}.",
                Confidence.MEDIUM,
                ev("subscription_gross_margin"),
            )
        )
    for name in ("grr", "nrr", "rule_of_40", "burn_multiple"):
        mv = m.metrics[name]
        if mv.value is not None:
            out.append(
                DraftFinding(
                    f"metric_{name}",
                    FindingType.OBSERVATION,
                    f"{name.upper()} (trailing 12 months)",
                    f"{name} = {mv.value} ({mv.variant}).",
                    Confidence.HIGH,
                    mv.evidence_ids,
                )
            )
    return out


def pricing_findings(pw: PriceWaterfall, policy: PolicyConfig) -> list[DraftFinding]:
    s = policy.screening
    out: list[DraftFinding] = []
    ev = pw.evidence_ids
    t = pw.total
    out.append(
        DraftFinding(
            "waterfall",
            FindingType.OBSERVATION,
            "Price waterfall (trailing 12 months)",
            f"On-invoice leakage {_pct(t.on_invoice_leakage_rate)} and off-invoice leakage "
            f"{_pct(t.off_invoice_leakage_rate)} of list; pocket price realization "
            f"{_pct(t.pocket_price_realization)}.",
            Confidence.HIGH,
            ev,
        )
    )
    hd = pw.highest_dispersion()
    if hd and hd.discount_sd is not None and hd.discount_sd > s.discount_sd_max:
        out.append(
            DraftFinding(
                "dispersion",
                FindingType.OBSERVATION,
                f"Wide discount dispersion in {hd.segment.replace('_', '-')}",
                f"New-deal discount standard deviation in {hd.segment.replace('_', '-')} is {_pct(hd.discount_sd)} "
                f"(mean {_pct(hd.mean_discount_rate)}, {hd.lines} deals) against a policy maximum "
                f"of {_pct(s.discount_sd_max)}.",
                Confidence.HIGH,
                ev,
                metadata={"segment": hd.segment},
            )
        )
    if pw.quarter_end_discount_gap is not None and pw.quarter_end_discount_gap > s.quarter_end_discount_gap_max:
        out.append(
            DraftFinding(
                "quarter_end",
                FindingType.OBSERVATION,
                "Quarter-end discounting",
                f"New deals closed in the second half of quarter-end months carry "
                f"{_pct(pw.quarter_end_discount_gap)} more discount than comparable deals.",
                Confidence.MEDIUM,
                ev,
            )
        )
    rr = pw.renewal_realization
    if rr.realization_ratio is not None and rr.realization_ratio < s.renewal_uplift_realization_min:
        out.append(
            DraftFinding(
                "renewal_uplift",
                FindingType.OBSERVATION,
                "Renewal uplifts largely waived",
                f"Realized renewal uplift averaged {_pct(rr.mean_realized_uplift)} against "
                f"{_pct(rr.mean_contracted_uplift)} contracted ({rr.renewals} renewals; realization "
                f"{_pct(rr.realization_ratio)}).",
                Confidence.HIGH,
                ev,
            )
        )
    if pw.legacy.legacy_arr_share is not None and pw.legacy.legacy_arr_share > s.legacy_arr_share_max:
        out.append(
            DraftFinding(
                "legacy",
                FindingType.OBSERVATION,
                "ARR on legacy price books",
                f"{_pct(pw.legacy.legacy_arr_share)} of ARR is billed on legacy price books.",
                Confidence.HIGH,
                ev,
            )
        )
    if not pw.contract_constraints.available:
        out.append(
            DraftFinding(
                "contracts_missing",
                FindingType.DATA_GAP,
                "Contract terms unavailable",
                "Contract terms (caps, MFN, notice periods) are not in evidence; price-increase "
                "opportunities cannot be sized.",
                Confidence.HIGH,
                [],
            )
        )
    return out


def retention_findings(ra: RetentionAnalysis, policy: PolicyConfig) -> list[DraftFinding]:
    s = policy.screening
    out: list[DraftFinding] = []
    ev = ra.evidence_ids
    out.append(
        DraftFinding(
            "headline",
            FindingType.OBSERVATION,
            "Retention headline (trailing 12 months)",
            f"GRR {_pct(ra.grr)}, NRR {_pct(ra.nrr)}, logo retention {_pct(ra.logo_retention)}.",
            Confidence.HIGH,
            ev,
        )
    )
    ws = ra.worst_segment()
    total_opening = sum((x.opening_arr for x in ra.segments if x.dimension == "segment"), Decimal(0))
    material = bool(ws and total_opening and ws.opening_arr / total_opening >= s.segment_min_arr_share)
    if ws and material and ra.grr is not None and ws.grr is not None and (ra.grr - ws.grr) > s.segment_grr_gap_max:
        out.append(
            DraftFinding(
                "worst_segment",
                FindingType.OBSERVATION,
                f"Churn concentrated in {ws.value}",
                f"{ws.value} GRR is {_pct(ws.grr)} against {_pct(ra.grr)} company-wide.",
                Confidence.HIGH,
                ev,
                metadata={"segment": ws.value},
            )
        )
    if ra.early_life_churn_overrepresentation is not None and ra.early_life_churn_overrepresentation > 1:
        out.append(
            DraftFinding(
                "front_loaded",
                FindingType.HYPOTHESIS,
                "Churn is front-loaded at first renewal",
                f"First-renewal customers are {ra.early_life_churn_overrepresentation}x over-"
                "represented in voluntary churn relative to their share of the base; consistent "
                "with an onboarding or fit problem.",
                Confidence.MEDIUM,
                ev,
            )
        )
    if ra.involuntary_payment_share is not None and ra.involuntary_payment_share > s.involuntary_churn_share_max:
        out.append(
            DraftFinding(
                "involuntary",
                FindingType.OBSERVATION,
                "Material failed-payment churn",
                f"{_pct(ra.involuntary_payment_share)} of churned ARR was lost to failed payments.",
                Confidence.HIGH,
                ev,
            )
        )
    for li in ra.leading_indicators:
        if li.signal:
            out.append(
                DraftFinding(
                    f"li_{li.name}",
                    FindingType.OBSERVATION,
                    f"Leading indicator: {li.name}",
                    f"Churned customers averaged {li.churned_value} on {li.name} in the "
                    f"{li.lead_months} months before churn versus {li.retained_value} for retained "
                    "customers.",
                    Confidence.MEDIUM,
                    li.evidence_ids,
                )
            )
    return out


def ai_findings(ai: AiAssessment, policy: PolicyConfig) -> list[DraftFinding]:
    out: list[DraftFinding] = []
    for c in ai.candidates:
        if c.sizeable:
            out.append(
                DraftFinding(
                    f"ai_{c.workflow}",
                    FindingType.OBSERVATION,
                    f"Automation candidate: {c.workflow}",
                    f"{c.workflow}: {c.annual_volume} tickets per year, annual cost {c.annual_cost}, "
                    f"addressable share {_pct(c.addressable_share)}.",
                    Confidence.MEDIUM,
                    c.evidence_ids,
                    metadata={"scores": c.scores},
                )
            )
        else:
            out.append(
                DraftFinding(
                    f"ai_{c.workflow}",
                    FindingType.DATA_GAP,
                    f"{c.workflow.replace('_', ' ').capitalize()} not sized",
                    f"Data needed: {'; '.join(c.data_needed)}.",
                    Confidence.LOW,
                    [],
                )
            )
    return out


# --- rule-based proposer -------------------------------------------------------------------------------------
class RuleBasedProposer:
    name = "rules"

    def propose(self, ctx: BranchContext) -> list[OpportunityProposal]:
        fn = {
            "unit_economics": self._unit_economics,
            "pricing": self._pricing,
            "retention": self._retention,
            "ai_opportunity": self._ai,
        }[ctx.analysis]
        return fn(ctx)

    @staticmethod
    def _keys(ctx: BranchContext) -> dict[str, DraftFinding]:
        return {f.key: f for f in ctx.findings}

    def _pricing(self, ctx: BranchContext) -> list[OpportunityProposal]:
        f, p, ev = self._keys(ctx), ctx.policy, ctx.evidence_ids
        out: list[OpportunityProposal] = []
        if "dispersion" in f or "quarter_end" in f:
            seg = f["dispersion"].metadata["segment"] if "dispersion" in f else None
            reasons = [f[k].statement for k in ("dispersion", "quarter_end") if k in f]
            where = f" in {seg.replace('_', '-')}" if seg else ""
            out.append(
                _proposal(
                    p,
                    "discount_governance",
                    lever=Lever.PRICING,
                    baseline_metric="discounted_arr",
                    title=f"Discount governance{where}",
                    confidence=Confidence.MEDIUM,
                    rationale=" ".join(reasons),
                    evidence_ids=ev,
                    metric_params={"segment": seg} if seg else {},
                    assumptions=[
                        "Improvement is the reduction in average discount as a share of list price",
                        "Realization reflects sales adoption of the approval policy",
                    ],
                )
            )
        if "renewal_uplift" in f:
            out.append(
                _proposal(
                    p,
                    "renewal_uplift",
                    lever=Lever.PRICING,
                    baseline_metric="renewing_arr",
                    title="Enforce contracted renewal uplifts",
                    confidence=Confidence.MEDIUM,
                    rationale=f["renewal_uplift"].statement,
                    evidence_ids=ev,
                    assumptions=[
                        "Customer churn and downgrade response is captured in the realization rate",
                        "Only renewals in the next 12 months realize in year one",
                        "Overlaps with discount governance on the same ARR; sized independently",
                    ],
                )
            )
        if "legacy" in f:
            out.append(
                _proposal(
                    p,
                    "legacy_migration",
                    lever=Lever.PRICING,
                    baseline_metric="legacy_price_book_arr",
                    title="Migrate legacy price-book customers",
                    confidence=Confidence.MEDIUM,
                    rationale=f["legacy"].statement,
                    evidence_ids=ev,
                    assumptions=[
                        "Improvement is the price increase achieved on migration",
                        "Realization is the share of legacy ARR migrated net of churn",
                    ],
                )
            )
        return out

    def _retention(self, ctx: BranchContext) -> list[OpportunityProposal]:
        f, p, ev = self._keys(ctx), ctx.policy, ctx.evidence_ids
        out: list[OpportunityProposal] = []
        grr = ctx.result.grr if isinstance(ctx.result, RetentionAnalysis) else None
        company_wide = grr is not None and grr < p.screening.grr_min
        if "worst_segment" in f or company_wide:
            # Company GRR below policy -> program covers all voluntary churn; otherwise target the worst segment.
            seg = f["worst_segment"].metadata["segment"] if "worst_segment" in f and not company_wide else None
            signals = [k for k in f if k.startswith("li_")]
            li_ev = sorted({e for k in signals for e in f[k].evidence_ids})
            out.append(
                _proposal(
                    p,
                    "voluntary_churn_reduction",
                    lever=Lever.RETENTION,
                    baseline_metric="addressable_churned_arr",
                    title="Reduce voluntary churn" + (f" in {seg.replace('_', '-')}" if seg else ""),
                    confidence=Confidence.MEDIUM if signals else Confidence.LOW,
                    rationale=" ".join(f[k].statement for k in ["worst_segment", "front_loaded", *signals] if k in f)
                    or f"Company GRR {grr} is below policy minimum {p.screening.grr_min}.",
                    evidence_ids=sorted(set(ev) | set(li_ev)),
                    metric_params={"segment": seg} if seg else {},
                    assumptions=[
                        "Program cost (customer-success capacity, health scoring) is in annual run cost",
                        "Causal drivers are hypotheses until corroborated by exit interviews",
                    ],
                )
            )
        if "involuntary" in f:
            out.append(
                _proposal(
                    p,
                    "involuntary_churn_recovery",
                    lever=Lever.RETENTION,
                    baseline_metric="failed_payment_churned_arr",
                    title="Recover failed-payment churn (dunning and card updater)",
                    confidence=Confidence.MEDIUM,
                    rationale=f["involuntary"].statement,
                    evidence_ids=ev,
                    assumptions=["Recovery share from a standard dunning sequence and card-updater service"],
                )
            )
        return out

    def _unit_economics(self, ctx: BranchContext) -> list[OpportunityProposal]:
        f, p = self._keys(ctx), ctx.policy
        out: list[OpportunityProposal] = []
        if "cac_payback" in f or "magic_number" in f:
            keys = [k for k in ("cac_payback", "magic_number") if k in f]
            out.append(
                _proposal(
                    p,
                    "sales_efficiency",
                    lever=Lever.SALES_EFFICIENCY,
                    baseline_metric="s_and_m_expense",
                    title="Improve sales and marketing efficiency",
                    confidence=Confidence.LOW,
                    rationale=" ".join(f[k].statement for k in keys),
                    evidence_ids=sorted({e for k in keys for e in f[k].evidence_ids}),
                    assumptions=[
                        "Savings at constant new ARR",
                        "Check pricing leakage before attributing to GTM spend",
                    ],
                )
            )
        if "gross_margin" in f:
            out.append(
                _proposal(
                    p,
                    "hosting_optimization",
                    lever=Lever.GROSS_MARGIN,
                    baseline_metric="hosting_cost",
                    title="Optimise hosting cost",
                    confidence=Confidence.LOW,
                    rationale=f["gross_margin"].statement,
                    evidence_ids=f["gross_margin"].evidence_ids,
                    assumptions=["Savings from commitment discounts and right-sizing; no product change"],
                )
            )
        return out

    def _ai(self, ctx: BranchContext) -> list[OpportunityProposal]:
        p = ctx.policy
        ai: AiAssessment = ctx.result
        out: list[OpportunityProposal] = []
        for c in ai.candidates:
            if not (c.sizeable and c.baseline_metric):
                continue
            if ai.tier1_cost_share is None or ai.tier1_cost_share < p.screening.support_tier1_cost_share_min:
                continue
            out.append(
                _proposal(
                    p,
                    "support_automation",
                    lever=Lever.AI_AUTOMATION,
                    baseline_metric=c.baseline_metric,
                    title="Deflect tier-1 support with AI self-service",
                    confidence=Confidence.LOW,
                    rationale=f"Tier-1 support is {_pct(ai.tier1_cost_share)} of support cost; "
                    f"{_pct(c.addressable_share)} of tickets fall in tier-1 categories.",
                    evidence_ids=c.evidence_ids,
                    assumptions=[
                        "Deflection rate is an assumption until a company pilot measures it",
                        "Savings are capacity; any headcount change requires approval and HR/legal review",
                    ],
                )
            )
        return out
