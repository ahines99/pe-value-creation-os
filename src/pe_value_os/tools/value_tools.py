"""Analysis, value-model and workflow tools (PVC-052, PVC-053, PVC-054, PVC-058, PVC-121).

Mutating tools write audit events. `propose_opportunity` never accepts baseline values or flow-through; the
server derives them. There is deliberately no tool that records an approval decision (ADR 0004).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from mcp.server import MCPServer
from pydantic import BaseModel

from .. import security
from ..adapters.repositories import NotFound
from ..domain import sufficiency
from ..domain.baselines import derive_baseline
from ..domain.metrics import SaasMetrics, compute_saas_metrics
from ..domain.models import Confidence, EvidenceRef, Finding, FindingType
from ..domain.policies import require_citations
from ..domain.pricing import PriceWaterfall, price_waterfall
from ..domain.prioritization import prioritize
from ..domain.project_models import Lever, Opportunity, PriorityScore, ScenarioInputs, ValueCase
from ..domain.retention import RetentionAnalysis, analyse_retention
from ..domain.runs import PlanRecord, RunState, Status
from ..domain.services import size_value_case as _size
from ..domain.sufficiency import SufficiencyResult
from ..llm.quantities import catalog, render_claims
from ..llm.validation import interactive_sources, validate_interactive_opportunity, validate_interactive_run
from ..workflows import primary
from ..workflows.planning import build_plan
from ._runtime import audit, company_data, get_ctx, governed
from .source_tools import parse_period


def _run(run_id: str) -> Any:
    rec = get_ctx().repo.get_run(run_id)
    security.require(rec.company_id)
    return rec


def _open_interactive_run(run_id: str) -> Any:
    """The run a skill-driven tool may change: interactive, and not yet submitted or decided."""
    rec = _run(run_id)
    if rec.params.get("mode") != "interactive":
        raise ValueError(
            f"Run {run_id} is an automated run; the workflow produces its findings, opportunities and plan. "
            "Start an interactive run with start_diagnostic_run(mode='interactive') to work step by step."
        )
    if rec.status in (Status.AWAITING_APPROVAL, Status.COMPLETE, Status.REJECTED):
        raise ValueError(f"Run {run_id} is {rec.status.value} and can no longer be changed; start a new run.")
    return rec


class RunStatusResult(BaseModel):
    run_id: str
    company_id: str
    status: str
    current_step: str | None
    completed_steps: list[str]
    pause_reason: dict[str, Any] | None
    errors: list[str]
    paused: bool


class KpiStatusRow(BaseModel):
    kpi_id: str
    metric: str
    description: str
    direction: str
    baseline: Decimal
    day_100_target: Decimal
    run_rate_target: Decimal
    latest_value: Decimal | None
    latest_target: Decimal | None
    status: str | None
    observed_at: datetime | None
    evidence_ids: list[str]


class ApprovalRequestResult(BaseModel):
    approval_id: str
    run_id: str
    plan_id: str
    status: str
    message: str


def register_pricing(mcp: MCPServer) -> None:
    @mcp.tool(name="price_waterfall")
    @governed("price_waterfall")
    def price_waterfall_tool(company_id: str, period: str | None = None, segment: str | None = None) -> PriceWaterfall:
        """List -> invoice -> pocket price waterfall for the 12 months ending `period` ('YYYY-MM'), with discount
        dispersion, quarter-end discounting, renewal-uplift realization, legacy price books and contract
        constraints. Optionally limited to one segment."""
        data = company_data(company_id)
        end = parse_period(period, data.reference_date.replace(day=1)) if period else None
        return price_waterfall(data, period_end=end, segment=segment)


def register_value_model(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_numeric_sources")
    def get_numeric_sources(company_id: str) -> list[dict[str, Any]]:
        """Typed numeric facts from sufficient analyses. For a quantitative claim in record_finding or
        propose_opportunity, insert {{quantity:KEY}} using a returned key. The server renders the exact value
        with its metric, company, period and evidence. Write qualitative prose without numeric assertions."""
        return catalog(interactive_sources(get_ctx(), company_data(company_id)))

    @mcp.tool()
    @governed("check_data_sufficiency")
    def check_data_sufficiency(
        company_id: str, analysis: Literal["unit_economics", "pricing", "retention", "ai_opportunity"]
    ) -> SufficiencyResult:
        """SUFFICIENT or INSUFFICIENT for one analysis, with a machine-readable gap list. Never approximate data
        for an INSUFFICIENT analysis."""
        return sufficiency.check(company_data(company_id), analysis, get_ctx().policy)

    @mcp.tool(name="compute_saas_metrics")
    @governed("compute_saas_metrics")
    def compute_saas_metrics_tool(company_id: str, period: str | None = None) -> SaasMetrics:
        """ARR bridge, GRR, NRR, CAC payback, LTV/CAC, magic number, burn multiple, Rule of 40 and gross margin for
        the 12 months ending `period` ('YYYY-MM'). Each metric reports its variant, period and evidence."""
        data = company_data(company_id)
        return compute_saas_metrics(data, parse_period(period, data.reference_date) if period else None)

    @mcp.tool()
    @governed("compute_retention_cohorts")
    def compute_retention_cohorts(company_id: str, cohort_grain: Literal["quarter"] = "quarter") -> RetentionAnalysis:
        """Logo and dollar retention by quarterly cohort, segment decomposition, churn by type, early-life churn,
        reason codes and leading indicators (usage, support)."""
        return analyse_retention(company_data(company_id))

    @mcp.tool()
    @governed("record_finding", mutating=True)
    def record_finding(
        run_id: str,
        finding_type: Literal[
            "observation", "hypothesis", "value_claim", "opportunity", "data_gap", "suspicious_content"
        ],
        title: str,
        statement: str,
        confidence: Literal["low", "medium", "high"],
        evidence_ids: list[str],
        assumptions: list[str] | None = None,
    ) -> Finding:
        """Persist a finding for an open interactive run. Value claims must cite at least one evidence id from this
        company. Numeric claims must use {{quantity:KEY}} references from get_numeric_sources."""
        rec = _open_interactive_run(run_id)
        data = company_data(rec.company_id)
        sources = interactive_sources(get_ctx(), data)
        title = render_claims(title, sources)
        statement = render_claims(statement, sources)
        assumptions = [render_claims(a, sources) for a in assumptions or []]
        known = {e.evidence_id for e in get_ctx().repo.list_evidence(rec.company_id, evidence_ids)}
        if set(evidence_ids) - known:
            raise ValueError("Evidence missing or outside this company")
        principal = security.current_principal()
        f = Finding(
            finding_id=str(uuid.uuid4()),
            run_id=run_id,
            company_id=rec.company_id,
            finding_type=FindingType(finding_type),
            title=title,
            statement=statement,
            confidence=Confidence(confidence),
            evidence_ids=evidence_ids,
            assumptions=assumptions or [],
            metadata={"source": "mcp", "actor": principal.subject if principal else "unknown"},
        )
        require_citations(f)
        get_ctx().repo.add_finding(f)
        audit(rec.company_id, "record_finding", "finding_recorded", run_id, count=len(evidence_ids))
        return f

    @mcp.tool()
    @governed("propose_opportunity", mutating=True)
    def propose_opportunity(
        run_id: str,
        lever: Literal["pricing", "retention", "sales_efficiency", "gross_margin", "ai_automation"],
        baseline_metric: str,
        title: str,
        low: ScenarioInputs,
        base: ScenarioInputs,
        high: ScenarioInputs,
        confidence: Literal["low", "medium", "high"],
        rationale: str,
        evidence_ids: list[str],
        assumptions: list[str] | None = None,
        annual_run_cost: Decimal = Decimal(0),
        one_time_cost: Decimal = Decimal(0),
        metric_params: dict[str, str] | None = None,
    ) -> Opportunity:
        """Propose an opportunity. You supply scenario rates (fractions: 0.05 = 5%), evidence and rationale; the
        server fills in the baseline value and EBITDA flow-through from company data. Returns the stored
        opportunity; call size_value_case next. Only for open interactive runs. Numeric prose must use
        {{quantity:KEY}} references from get_numeric_sources; overlapping proposals are rejected."""
        rec = _open_interactive_run(run_id)
        ctx = get_ctx()
        data = company_data(rec.company_id)
        derived = derive_baseline(data, Lever(lever), baseline_metric, metric_params or {}, ctx.policy)
        contexts: dict[str, Any] = {}
        sources = interactive_sources(ctx, data, contexts)
        title = render_claims(title, sources)
        rationale = render_claims(rationale, sources)
        assumptions = [render_claims(a, sources) for a in assumptions or []]
        opp = Opportunity(
            opportunity_id=str(uuid.uuid4()),
            run_id=run_id,
            company_id=rec.company_id,
            lever=Lever(lever),
            title=title,
            baseline_metric=baseline_metric,
            baseline_value=derived.baseline.value,
            ebitda_flow_through=derived.ebitda_flow_through,
            low=low,
            base=base,
            high=high,
            annual_run_cost=annual_run_cost,
            one_time_cost=one_time_cost,
            confidence=Confidence(confidence),
            rationale=rationale,
            assumptions=assumptions or [],
            evidence_ids=sorted(set(evidence_ids) | set(derived.evidence_ids)),
            metric_params=metric_params or {},
        )
        validate_interactive_opportunity(
            ctx, data, opp, ctx.repo.list_opportunities(run_id), sources=sources, contexts=contexts
        )
        ctx.repo.add_opportunity(
            opp,
            proposer=f"mcp:{security.current_principal().subject}",  # type: ignore[union-attr]
            flow_through_rule=derived.flow_through_rule,
        )
        audit(
            rec.company_id,
            "propose_opportunity",
            "opportunity_proposed",
            run_id,
            opportunity_id=opp.opportunity_id,
            lever=lever,
        )
        return opp

    @mcp.tool(name="size_value_case")
    @governed("size_value_case", mutating=True)
    def size_value_case(company_id: str, opportunity_id: str, ev_multiple: Decimal | None = None) -> ValueCase:
        """Size low/base/high annual run-rate EBITDA for a stored opportunity. Baseline values and flow-through
        come from company data, never from the caller. Quote results exactly; do not adjust them."""
        ctx = get_ctx()
        opp = ctx.repo.get_opportunity(company_id, opportunity_id)
        _open_interactive_run(opp.run_id)
        vc = _size(opp, ev_multiple)
        ctx.repo.save_value_case(company_id, opp.run_id, vc, ctx.policy.version)
        audit(
            company_id,
            "size_value_case",
            "value_case_sized",
            opp.run_id,
            opportunity_id=opportunity_id,
            calc_version=vc.calc_version,
            policy_version=ctx.policy.version,
        )
        return vc

    @mcp.tool()
    @governed("list_evidence")
    def list_evidence(company_id: str, opportunity_id: str) -> list[EvidenceRef]:
        """Evidence linked to one opportunity (source, as-of date, content hash)."""
        return get_ctx().repo.evidence_for_opportunity(company_id, opportunity_id)

    @mcp.tool()
    @governed("prioritize_opportunities", mutating=True)
    def prioritize_opportunities(run_id: str) -> list[PriorityScore]:
        """Deterministic priority scores for every sized opportunity in an open interactive run. Opportunities not yet
        sized with size_value_case are left out. Do not reorder the result."""
        rec = _open_interactive_run(run_id)
        ctx = get_ctx()
        items = []
        for o in ctx.repo.list_opportunities(run_id):
            try:
                items.append((o, ctx.repo.get_value_case(rec.company_id, o.opportunity_id)))
            except NotFound:
                continue  # not sized yet
        scores = prioritize(items, ctx.policy)
        ctx.repo.save_priorities(run_id, rec.company_id, scores)
        audit(rec.company_id, "prioritize_opportunities", "opportunities_prioritized", run_id, count=len(scores))
        return scores

    @mcp.tool()
    @governed("draft_100_day_plan", mutating=True)
    def draft_100_day_plan(run_id: str) -> dict[str, Any]:
        """Build the 100-day plan from the run's prioritized, positively sized opportunities. Returns the draft
        plan; submit it with request_approval. Requires prioritize_opportunities first."""
        rec = _open_interactive_run(run_id)
        ctx = get_ctx()
        validate_interactive_run(ctx, company_data(rec.company_id), rec.run_state())
        scores = ctx.repo.list_priorities(run_id)
        if not scores:
            raise ValueError("No prioritized opportunities. Run size_value_case and prioritize_opportunities first.")
        ranked = {s.opportunity_id for s in scores}
        items = [
            (o, ctx.repo.get_value_case(rec.company_id, o.opportunity_id))
            for o in ctx.repo.list_opportunities(run_id)
            if o.opportunity_id in ranked
        ]
        excluded = [
            {
                "opportunity_id": o.opportunity_id,
                "title": o.title,
                "reason": f"Nonpositive modeled annual contribution ({vc.annual_ebitda_base})",
            }
            for o, vc in items
            if vc.annual_ebitda_base <= 0
        ]
        plan = build_plan(
            run_id,
            company_data(rec.company_id),
            [(o, v) for o, v in items if v.annual_ebitda_base > 0],
            scores,
            ctx.policy,
            excluded=excluded,
        )
        ctx.repo.save_plan(
            PlanRecord(
                plan_id=plan.plan_id,
                run_id=run_id,
                company_id=rec.company_id,
                status="proposed",
                plan=plan.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )
        audit(rec.company_id, "draft_100_day_plan", "plan_drafted", run_id, plan_id=plan.plan_id)
        return plan.model_dump(mode="json")

    @mcp.tool()
    @governed("get_kpi_status")
    def get_kpi_status(company_id: str) -> list[KpiStatusRow]:
        """Plan-vs-actual for the company's approved KPIs (latest observation per KPI)."""
        repo = get_ctx().repo
        latest = {o.kpi_id: o for o in repo.list_kpi_observations(company_id)}
        return [
            KpiStatusRow(
                kpi_id=d.kpi_id,
                metric=d.metric,
                description=d.description,
                direction=d.direction,
                baseline=d.baseline,
                day_100_target=d.day_100_target,
                run_rate_target=d.run_rate_target,
                latest_value=latest[d.kpi_id].value if d.kpi_id in latest else None,
                latest_target=latest[d.kpi_id].target if d.kpi_id in latest else None,
                status=latest[d.kpi_id].status if d.kpi_id in latest else None,
                observed_at=latest[d.kpi_id].observed_at if d.kpi_id in latest else None,
                evidence_ids=latest[d.kpi_id].evidence_ids if d.kpi_id in latest else d.evidence_ids,
            )
            for d in repo.list_kpi_definitions(company_id)
        ]


def register_workflow(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("start_diagnostic_run", mutating=True)
    def start_diagnostic_run(
        company_id: str, mode: Literal["automated", "interactive"] = "automated", idempotency_key: str | None = None
    ) -> RunStatusResult:
        """Create a diagnostic run. `automated` queues the full workflow for the worker; `interactive` creates an
        empty run for skill-driven analysis with record_finding / propose_opportunity."""
        ctx = get_ctx()
        rec, _ = primary.start(
            ctx,
            company_id,
            security.current_principal().subject,  # type: ignore[union-attr]
            idempotency_key=idempotency_key,
            params={"mode": mode},
        )
        if mode == "interactive" and rec.status == Status.PENDING:
            st = rec.run_state()
            st.status = Status.RUNNING
            st.current_step = "interactive"
            ctx.repo.save_run_state(st)
        return get_run_status(rec.run_id)

    @mcp.tool()
    @governed("get_run_status")
    def get_run_status(run_id: str) -> RunStatusResult:
        """Current step, status, pause reason and errors for a run."""
        _run(run_id)
        return RunStatusResult(**primary.status(get_ctx(), run_id))

    @mcp.tool()
    @governed("request_approval", mutating=True)
    def request_approval(run_id: str) -> ApprovalRequestResult:
        """Submit an open interactive run's latest plan for human approval and pause the run. A human decides through
        the approval API; no tool can approve. Automated runs request approval themselves."""
        rec = _open_interactive_run(run_id)
        ctx = get_ctx()
        plan = ctx.repo.latest_plan(run_id)
        if plan is None:
            raise ValueError("No plan to submit. Run prioritize_opportunities and draft_100_day_plan first.")
        validate_interactive_run(ctx, company_data(rec.company_id), rec.run_state())
        from ..kpi import check_monitorable

        check_monitorable(plan.plan)
        req = ctx.repo.create_approval_request(run_id, rec.company_id, "plan", plan.plan_id)
        st: RunState = ctx.repo.get_run(run_id).run_state()
        if st.status not in (Status.COMPLETE, Status.REJECTED):
            st.status = Status.AWAITING_APPROVAL
            st.pause_reason = {"reason": "awaiting_approval", "approval_id": req.approval_id, "plan_id": plan.plan_id}
            ctx.repo.save_run_state(st)
        audit(
            rec.company_id,
            "request_approval",
            "approval_requested",
            run_id,
            approval_id=req.approval_id,
            plan_id=plan.plan_id,
        )
        return ApprovalRequestResult(
            approval_id=req.approval_id,
            run_id=run_id,
            plan_id=plan.plan_id,
            status="awaiting_approval",
            message="Approval requested. A human must decide through the approval API.",
        )
