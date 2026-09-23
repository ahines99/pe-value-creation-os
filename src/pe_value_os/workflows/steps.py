"""Step services for the primary diagnostic workflow (PVC-043, PVC-061).

Each step returns structured, JSON-serialisable artifacts. Heavy computation runs in a worker thread so step
timeouts are enforceable. Ids for findings and opportunities are deterministic (uuid5 of run and key), so a
re-executed step never duplicates records.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

import anyio

from .. import freshness, kpi
from ..adapters.base import SourceAdapter
from ..adapters.repositories import Repository
from ..content_safety import scan
from ..domain import ai_ops, sufficiency
from ..domain.baselines import MetricUnavailable, derive_baseline
from ..domain.calc import jsonable
from ..domain.dataset import CompanyData
from ..domain.metrics import compute_saas_metrics
from ..domain.models import Confidence, Finding, FindingType
from ..domain.policies import require_citations
from ..domain.pricing import price_waterfall
from ..domain.prioritization import prioritize
from ..domain.project_models import Opportunity, OpportunityProposal, Plan
from ..domain.retention import analyse_retention
from ..domain.runs import ApprovalDecision, PlanRecord, RunState, Status
from ..domain.services import size_value_case
from ..domain.source_models import DatasetKind
from ..llm.client import ModelUnavailable
from ..observability import get_logger
from ..policy import PolicyConfig
from .base import Rewind
from .planning import build_plan
from .proposals import (
    BranchContext,
    DraftFinding,
    Proposer,
    RuleBasedProposer,
    ai_findings,
    pricing_findings,
    retention_findings,
    unit_economics_findings,
)

log = get_logger(__name__)
NS = uuid.UUID("0b8f3f4e-5d1a-4c55-9a8c-7e2f6d4b3a10")


def stable_id(*parts: str) -> str:
    return str(uuid.uuid5(NS, ":".join(parts)))


@dataclass
class RunContext:
    repo: Repository
    adapter: SourceAdapter
    policy: PolicyConfig
    proposer: Proposer = field(default_factory=RuleBasedProposer)
    narrator: Callable[[Plan, list[Finding]], str | None] | None = None
    actor: str = "system:workflow"
    _data: dict[str, CompanyData] = field(default_factory=dict)

    def data(self, company_id: str) -> CompanyData:
        if company_id not in self._data:
            self._data[company_id] = self.adapter.load(company_id, sink=self.repo)
        return self._data[company_id]

    def reload(self, company_id: str) -> CompanyData:
        self._data.pop(company_id, None)
        return self.data(company_id)


async def _thread(fn: Callable[..., Any], *args: Any) -> Any:
    return await anyio.to_thread.run_sync(partial(fn, *args), abandon_on_cancel=True)


def _persist_findings(ctx: RunContext, state: RunState, branch: str, drafts: list[DraftFinding]) -> list[str]:
    ids = []
    for d in drafts:
        f = Finding(finding_id=stable_id(state.run_id, "finding", branch, d.key), run_id=state.run_id,
                    company_id=state.company_id, finding_type=d.finding_type, title=d.title, statement=d.statement,
                    confidence=d.confidence, evidence_ids=d.evidence_ids, assumptions=d.assumptions,
                    metadata={**d.metadata, "branch": branch})
        require_citations(f)
        ctx.repo.add_finding(f)
        ids.append(f.finding_id)
    return ids


# --- 1. intake ------------------------------------------------------------------------------------------------
def intake(ctx: RunContext, state: RunState) -> dict[str, Any]:
    data = ctx.reload(state.company_id)
    ctx.repo.upsert_company(data.profile)
    freshness.record(data, ctx.policy.freshness.max_age_days)
    if state.reference_date is None:
        state.reference_date = data.reference_date
    others = set(ctx.adapter.list_companies()) - {state.company_id}
    drafts: list[DraftFinding] = []
    docs_ds = data.datasets.get(DatasetKind.DOCUMENTS)
    for doc in data.records(DatasetKind.DOCUMENTS):
        det = scan(f"{doc.title}\n{doc.text}", others)
        if det.suspicious:
            drafts.append(DraftFinding(
                f"suspicious_doc_{doc.document_id}", FindingType.SUSPICIOUS_CONTENT,
                f"Suspicious instructions in document {doc.document_id}",
                "Document contains text addressed to an AI system or referencing another portfolio company. It was "
                "treated as data and not followed. Reasons: " + ", ".join(det.reasons) + ".", Confidence.HIGH,
                [docs_ds.evidence_id] if docs_ds else [], metadata={"document_id": doc.document_id,
                                                                    "reasons": list(det.reasons)}))
    churn_ds = data.datasets.get(DatasetKind.CHURN)
    for i, ev in enumerate(data.records(DatasetKind.CHURN)):
        if ev.notes:
            det = scan(ev.notes, others)
            if det.suspicious:
                drafts.append(DraftFinding(
                    f"suspicious_churn_note_{i}", FindingType.SUSPICIOUS_CONTENT,
                    "Suspicious instructions in a CRM churn note",
                    "A churn note contains text addressed to an AI system. It was treated as data and not followed. "
                    "Reasons: " + ", ".join(det.reasons) + ".", Confidence.HIGH,
                    [churn_ds.evidence_id] if churn_ds else [], metadata={"reasons": list(det.reasons)}))
    finding_ids = _persist_findings(ctx, state, "intake", drafts)
    return {
        "profile": data.profile.model_dump(mode="json"),
        "profile_evidence_id": data.profile_evidence_id,
        "reference_date": data.reference_date.isoformat(),
        "inventory": data.inventory(),
        "suspicious_content_findings": finding_ids,
    }


# --- 2. data sufficiency --------------------------------------------------------------------------------------
def data_sufficiency(ctx: RunContext, state: RunState) -> dict[str, Any]:
    data = ctx.data(state.company_id)
    results = sufficiency.check_all(data, ctx.policy)
    drafts = [
        DraftFinding(f"gap_{a}", FindingType.DATA_GAP, f"{a} analysis skipped: insufficient data",
                     "; ".join(g.detail for g in r.gaps if g.blocking), Confidence.HIGH, [])
        for a, r in results.items() if not r.sufficient
    ]
    _persist_findings(ctx, state, "data_sufficiency", drafts)
    sufficient = [a for a, r in results.items() if r.sufficient]
    artifact = {"results": {a: r.model_dump(mode="json") for a, r in results.items()}, "sufficient": sufficient}
    accept = bool(state.params.get("accept_gaps"))
    if len(sufficient) < ctx.policy.run.min_sufficient_analyses and not accept:
        state.status = Status.NEEDS_EVIDENCE
        state.pause_reason = {
            "reason": "insufficient_data",
            "detail": f"{len(sufficient)} of {len(results)} analyses have sufficient data; policy requires "
                      f"{ctx.policy.run.min_sufficient_analyses}",
            "gaps": [{"analysis": a, **g.model_dump()} for a, r in results.items() for g in r.gaps if g.blocking],
        }
    return artifact


# --- 3. diagnostics branches ------------------------------------------------------------------------------------
BRANCH_ANALYSIS: dict[str, tuple[Callable[..., Any], Callable[..., list[DraftFinding]]]] = {
    "unit_economics": (compute_saas_metrics, unit_economics_findings),
    "pricing": (price_waterfall, pricing_findings),
    "retention": (analyse_retention, retention_findings),
    "ai_opportunity": (ai_ops.assess, ai_findings),
}


def diagnostic_branch(ctx: RunContext, state: RunState, branch: str) -> dict[str, Any]:
    suff = state.artifacts.get("data_sufficiency", {}).get("sufficient", [])
    if branch not in suff:
        return {"skipped": True, "reason": "insufficient_data"}
    data = ctx.data(state.company_id)
    analyse, to_findings = BRANCH_ANALYSIS[branch]
    result = analyse(data)
    drafts = to_findings(result, ctx.policy)
    finding_ids = _persist_findings(ctx, state, branch, drafts)
    docs = [{"document_id": d.document_id, "title": d.title, "text": d.text}
            for d in data.records(DatasetKind.DOCUMENTS)]
    bctx = BranchContext(analysis=branch, company_id=state.company_id, policy=ctx.policy, result=result,
                         findings=drafts, evidence_ids=getattr(result, "evidence_ids", None)
                         or sorted({e for d in drafts for e in d.evidence_ids}), documents=docs)
    proposer_name = ctx.proposer.name
    model_unavailable = None
    try:
        proposals = ctx.proposer.propose(bctx)
    except ModelUnavailable as exc:
        if ctx.policy.model.on_unavailable == "rules":
            proposals, proposer_name = RuleBasedProposer().propose(bctx), "rules(fallback)"
            bctx.report["fallback_reason"] = str(exc)
        else:  # PVC-074: pause the run instead of guessing; diagnostics re-run on resume
            proposals, model_unavailable = [], str(exc)
    return {
        "skipped": False,
        "summary": jsonable(result),
        "finding_ids": finding_ids,
        "proposals": [p.model_dump(mode="json") for p in proposals],
        "proposer": proposer_name,
        "proposer_report": jsonable(bctx.report),
        "model_unavailable": model_unavailable,
    }


# --- 4. value modeling ------------------------------------------------------------------------------------------
def value_modeling(ctx: RunContext, state: RunState) -> dict[str, Any]:
    data = ctx.data(state.company_id)
    branches = state.artifacts.get("diagnostics", {}).get("results", {})
    sized, unsized = [], []
    for _branch, res in sorted(branches.items()):
        for raw in res.get("proposals", []):
            prop = OpportunityProposal.model_validate(raw)
            key = f"{prop.lever.value}:{prop.baseline_metric}:{sorted(prop.metric_params.items())}:{prop.title}"
            oid = stable_id(state.run_id, "opportunity", key)
            try:
                derived = derive_baseline(data, prop.lever, prop.baseline_metric, prop.metric_params, ctx.policy)
            except MetricUnavailable as exc:
                unsized.append({"opportunity_id": oid, "title": prop.title, "lever": prop.lever.value,
                                "reason": f"NEEDS_EVIDENCE: {exc}"})
                _persist_findings(ctx, state, "value_modeling", [DraftFinding(
                    f"unsized_{oid}", FindingType.DATA_GAP, f"Cannot size: {prop.title}",
                    f"NEEDS_EVIDENCE: {exc}", Confidence.HIGH, [])])
                continue
            evidence = sorted(set(prop.evidence_ids) | set(derived.evidence_ids))
            opp = Opportunity(
                opportunity_id=oid, run_id=state.run_id, company_id=state.company_id, lever=prop.lever,
                title=prop.title, baseline_metric=prop.baseline_metric, baseline_value=derived.baseline.value,
                ebitda_flow_through=derived.ebitda_flow_through, low=prop.low, base=prop.base, high=prop.high,
                annual_run_cost=prop.annual_run_cost, one_time_cost=prop.one_time_cost, confidence=prop.confidence,
                rationale=prop.rationale, assumptions=prop.assumptions, evidence_ids=evidence,
                metric_params=prop.metric_params,
            )
            ctx.repo.add_opportunity(opp, proposer=res.get("proposer", "rules"),
                                     flow_through_rule=derived.flow_through_rule)
            vc = size_value_case(opp)
            ctx.repo.save_value_case(state.company_id, state.run_id, vc, ctx.policy.version)
            _persist_findings(ctx, state, "value_modeling", [DraftFinding(
                f"opp_{oid}", FindingType.OPPORTUNITY, prop.title,
                f"{prop.title}: base-case annual run-rate EBITDA {vc.annual_ebitda_base} "
                f"(low {vc.annual_ebitda_low}, high {vc.annual_ebitda_high}) from {prop.baseline_metric} "
                f"{derived.baseline.value}.", prop.confidence, evidence,
                metadata={"opportunity_id": oid, "inputs_hash": vc.inputs_hash})])
            sized.append({"opportunity_id": oid, "title": prop.title, "lever": prop.lever.value,
                          "value_case": vc.model_dump(mode="json")})
    return {"sized": sized, "unsized": unsized}


# --- 5. evidence review -----------------------------------------------------------------------------------------
def evidence_review(ctx: RunContext, state: RunState) -> dict[str, Any]:
    opps = ctx.repo.list_opportunities(state.run_id)
    ref = state.reference_date or ctx.data(state.company_id).reference_date
    violations: list[str] = []
    warnings: list[str] = []
    for o in opps:
        if not o.evidence_ids:
            violations.append(f"{o.title}: no evidence")
            continue
        found = {e.evidence_id: e for e in ctx.repo.list_evidence(state.company_id, o.evidence_ids)}
        missing = set(o.evidence_ids) - set(found)
        if missing:
            violations.append(f"{o.title}: evidence not found {sorted(missing)}")
        for e in found.values():
            if e.as_of and (ref - e.as_of.date()).days > ctx.policy.freshness.max_age_days:
                violations.append(f"{o.title}: evidence {e.source_uri} is stale (as_of {e.as_of.date()})")
    seen: dict[tuple[str, str], str] = {}
    for o in opps:
        k = (o.baseline_metric, str(sorted(o.metric_params.items())))
        if k in seen:
            violations.append(f"{o.title}: double counts {seen[k]} (same baseline {o.baseline_metric})")
        seen[k] = o.title
    pricing_arr = [o for o in opps if o.lever.value == "pricing"]
    if len(pricing_arr) > 1:
        warnings.append("Pricing opportunities act on overlapping ARR and were sized independently; combined "
                        "effect may be lower than the sum")
    for f in ctx.repo.list_findings(state.run_id):
        if f.finding_type in (FindingType.VALUE_CLAIM, FindingType.OPPORTUNITY) and not f.evidence_ids:
            violations.append(f"Finding {f.title}: uncited value claim")
        if f.finding_type == FindingType.SUSPICIOUS_CONTENT:
            warnings.append(f"Suspicious content recorded for human review: {f.title}")
    if violations and not state.params.get("accept_gaps"):
        state.status = Status.NEEDS_EVIDENCE
        state.pause_reason = {"reason": "evidence_review", "violations": violations}
    return {"opportunities_checked": len(opps), "violations": violations, "warnings": warnings}


# --- 6. prioritization ------------------------------------------------------------------------------------------
def prioritization(ctx: RunContext, state: RunState) -> dict[str, Any]:
    excluded = set(state.params.get("excluded_opportunities", []))
    items = [(o, ctx.repo.get_value_case(state.company_id, o.opportunity_id))
             for o in ctx.repo.list_opportunities(state.run_id) if o.opportunity_id not in excluded]
    scores = prioritize(items, ctx.policy)
    ctx.repo.save_priorities(state.run_id, state.company_id, scores)
    return {"ranking": [s.model_dump(mode="json") for s in scores], "excluded_by_reviewer": sorted(excluded)}


# --- 7. 100-day roadmap -----------------------------------------------------------------------------------------
def roadmap_100_day(ctx: RunContext, state: RunState) -> dict[str, Any]:
    data = ctx.data(state.company_id)
    scores = ctx.repo.list_priorities(state.run_id)
    ranked = {s.opportunity_id for s in scores}
    candidates = [(o, ctx.repo.get_value_case(state.company_id, o.opportunity_id))
                  for o in ctx.repo.list_opportunities(state.run_id) if o.opportunity_id in ranked]
    items = [(o, vc) for o, vc in candidates if vc.annual_ebitda_base > 0]
    unsized = list(state.artifacts.get("value_modeling", {}).get("unsized", []))
    unsized += [{"opportunity_id": o.opportunity_id, "title": o.title, "lever": o.lever.value,
                 "reason": f"Base case does not pay back (annual run-rate EBITDA {vc.annual_ebitda_base})"}
                for o, vc in candidates if vc.annual_ebitda_base <= 0]
    gaps = [g["detail"] for g in (state.pause_reason or {}).get("gaps", [])]
    suff = state.artifacts.get("data_sufficiency", {}).get("results", {})
    gaps += [g["detail"] for r in suff.values() for g in r.get("gaps", []) if not g.get("blocking")]
    plan = build_plan(state.run_id, data, items, scores, ctx.policy, excluded=unsized, data_gaps=sorted(set(gaps)),
                      reviewer_notes=state.params.get("reviewer_notes"))
    if ctx.narrator is not None:
        narrative = ctx.narrator(plan, ctx.repo.list_findings(state.run_id))
        if narrative:
            plan = plan.model_copy(update={"narrative": narrative})
    ctx.repo.save_plan(PlanRecord(plan_id=plan.plan_id, run_id=state.run_id, company_id=state.company_id,
                                  status="proposed", plan=plan.model_dump(mode="json"), created_at=datetime.now(UTC)))
    return {"plan_id": plan.plan_id, "workstreams": len(plan.workstreams),
            "total_run_rate_ebitda_base": str(plan.total_run_rate_ebitda_base),
            "total_in_year_ebitda_base": str(plan.total_in_year_ebitda_base)}


# --- 8. human approval gate (PVC-061) ---------------------------------------------------------------------------
def human_approval(ctx: RunContext, state: RunState) -> dict[str, Any]:
    plan = ctx.repo.latest_plan(state.run_id)
    if plan is None:
        raise RuntimeError("No plan to approve")
    approvals = [a for a in ctx.repo.list_approvals(state.run_id) if a.artifact_id == plan.plan_id]
    latest = approvals[-1] if approvals else None
    if latest is None or latest.decision is None:
        req = latest or ctx.repo.create_approval_request(state.run_id, state.company_id, "plan", plan.plan_id)
        state.status = Status.AWAITING_APPROVAL
        state.pause_reason = {"reason": "awaiting_approval", "approval_id": req.approval_id, "plan_id": plan.plan_id}
        return {"approval_id": req.approval_id, "plan_id": plan.plan_id, "decision": None}
    if latest.decision == ApprovalDecision.REJECTED:
        ctx.repo.update_plan_status(plan.plan_id, "rejected")
        state.status = Status.REJECTED
        state.pause_reason = {"reason": "rejected", "rationale": latest.rationale, "decided_by": latest.decided_by}
        return {"approval_id": latest.approval_id, "decision": latest.decision.value}
    if latest.decision == ApprovalDecision.CHANGES_REQUESTED:
        state.params["reviewer_notes"] = latest.rationale
        state.params["excluded_opportunities"] = sorted(
            set(state.params.get("excluded_opportunities", [])) | set(latest.edits.get("exclude_opportunities", [])))
        ctx.repo.update_plan_status(plan.plan_id, "superseded")
        raise Rewind("prioritization", "changes requested by reviewer")
    approved = latest.edits.get("approved_plan") or plan.plan
    ctx.repo.update_plan_status(plan.plan_id, "approved", approved)
    defs = kpi.activate_plan(ctx.repo, plan, approved, (latest.decided_at or datetime.now(UTC)).date(),
                             actor=latest.decided_by or "unknown")
    return {"approval_id": latest.approval_id, "decision": latest.decision.value, "plan_id": plan.plan_id,
            "kpis_activated": len(defs)}
