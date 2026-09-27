"""Human approval decisions (PVC-060, PVC-061, PVC-063).

`decide` is the only code path that records an approval decision. It requires a human principal with the
approver role, a rationale for rejections and change requests, and monitorable KPIs before approval. Approvers
may remove initiatives when approving; the diff between the proposed and approved plan is stored and audited.
"""

from __future__ import annotations

import copy
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from . import kpi, security
from .domain.models import AuditEvent
from .domain.runs import ApprovalDecision, ApprovalRecord, RunState, Status
from .observability import metrics
from .workflows.steps import RunContext


class ApprovalError(ValueError):
    """The decision request is invalid (HTTP 422)."""


class NotApprover(PermissionError):
    """The principal may not approve (HTTP 403)."""


def _require_approver(principal: security.Principal, company_id: str, approver_role: str) -> None:
    if not principal.is_human:
        raise NotApprover("Only human principals may record approval decisions")
    if approver_role not in principal.roles:
        raise NotApprover(f"Principal lacks the {approver_role!r} role")
    if company_id not in principal.companies:
        raise NotApprover("Principal may not access this company")
    if principal.scopes is not None:  # issued by the identity provider (bearer token or dev token)
        if not principal.has_scope(security.APPROVE_SCOPE):
            raise NotApprover(f"Token lacks the {security.APPROVE_SCOPE!r} scope")
        allowed = {c.strip() for c in os.environ.get("PVC_API_CLIENT_IDS", "").split(",") if c.strip()}
        if not allowed and os.environ.get("PVC_ENV", "prod") != "dev":
            raise NotApprover("PVC_API_CLIENT_IDS is not configured; approval decisions are disabled")
        if allowed and principal.client_id not in allowed:
            raise NotApprover("Approval decisions must come from the approval UI client")


def apply_edits(plan: dict[str, Any], remove_initiatives: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove initiatives (by opportunity id) from a plan. Returns (approved_plan, diff)."""
    remove = set(remove_initiatives)
    if not remove:
        return plan, {}
    approved = copy.deepcopy(plan)
    known = {i["opportunity_id"] for ws in plan["workstreams"] for i in ws["initiatives"]}
    unknown = remove - known
    if unknown:
        raise ApprovalError(f"Unknown initiatives: {sorted(unknown)}")
    removed_titles = []
    kept_ws = []
    for ws in approved["workstreams"]:
        removed_titles += [i["title"] for i in ws["initiatives"] if i["opportunity_id"] in remove]
        ws["initiatives"] = [i for i in ws["initiatives"] if i["opportunity_id"] not in remove]
        ws["kpis"] = [k for k in ws["kpis"] if k.get("opportunity_id") not in remove]
        if ws["initiatives"]:
            ws["risks"] = [r for r in ws.get("risks", []) if not any(r.startswith(t + ":") for t in removed_titles)]
            ws["milestones"] = {
                day: [m for m in entries if not any(m.endswith(": " + t) for t in removed_titles)]
                for day, entries in ws.get("milestones", {}).items()
            }
            kept_ws.append(ws)
    approved["workstreams"] = kept_ws
    approved["decisions_requiring_approval"] = [
        d
        for d in approved.get("decisions_requiring_approval", [])
        if not any(d.startswith(t + ":") for t in removed_titles)
    ]
    if not any(ws.get("lever") == "retention" for ws in kept_ws):
        for ws in kept_ws:
            ws["dependencies"] = [
                d
                for d in ws.get("dependencies", [])
                if d != "Price changes sequenced after the retention health score identifies at-risk accounts"
            ]
    # Narrative was generated against the original initiative set; retain an accurate edit summary.
    approved["narrative"] = "Reviewer removed initiatives: " + "; ".join(removed_titles)
    approved.setdefault("excluded_opportunities", []).extend(
        {"opportunity_id": oid, "reason": "Removed by human approver"} for oid in sorted(remove)
    )
    before = Decimal(plan["total_run_rate_ebitda_base"])
    after = sum((Decimal(i["run_rate_ebitda_base"]) for ws in kept_ws for i in ws["initiatives"]), Decimal(0))
    approved["total_run_rate_ebitda_base"] = str(after)
    approved["total_in_year_ebitda_base"] = str(
        sum((Decimal(i["in_year_ebitda_base"]) for ws in kept_ws for i in ws["initiatives"]), Decimal(0))
    )
    diff = {
        "removed_initiatives": sorted(remove),
        "removed_titles": removed_titles,
        "run_rate_ebitda_base_before": str(before),
        "run_rate_ebitda_base_after": str(after),
    }
    return approved, diff


def decide(
    ctx: RunContext,
    run_id: str,
    principal: security.Principal,
    decision: ApprovalDecision,
    *,
    rationale: str | None = None,
    remove_initiatives: list[str] | None = None,
    exclude_opportunities: list[str] | None = None,
) -> ApprovalRecord:
    with ctx.repo.approval_transaction():
        return _decide(
            ctx,
            run_id,
            principal,
            decision,
            rationale=rationale,
            remove_initiatives=remove_initiatives,
            exclude_opportunities=exclude_opportunities,
        )


def _decide(
    ctx: RunContext,
    run_id: str,
    principal: security.Principal,
    decision: ApprovalDecision,
    *,
    rationale: str | None = None,
    remove_initiatives: list[str] | None = None,
    exclude_opportunities: list[str] | None = None,
) -> ApprovalRecord:
    run = ctx.repo.get_run(run_id)
    _require_approver(principal, run.company_id, ctx.policy.approval.approver_role)
    if decision in (ApprovalDecision.REJECTED, ApprovalDecision.CHANGES_REQUESTED) and not (rationale or "").strip():
        raise ApprovalError("A rationale is required to reject or request changes")
    pending = [a for a in ctx.repo.list_approvals(run_id) if a.decision is None]
    if not pending:
        raise ApprovalError("No pending approval request for this run")
    req = pending[-1]
    plan = ctx.repo.get_plan(req.artifact_id)
    edits: dict[str, Any] = {}
    diff: dict[str, Any] = {}
    if decision == ApprovalDecision.APPROVED:
        approved, diff = apply_edits(plan.plan, remove_initiatives or [])
        try:
            kpi.check_monitorable(approved)
        except kpi.UnmonitorableKpi as e:
            raise ApprovalError(str(e)) from e
        if diff:
            edits["approved_plan"] = approved
    elif decision == ApprovalDecision.CHANGES_REQUESTED:
        edits["exclude_opportunities"] = sorted(exclude_opportunities or [])
    rec = ctx.repo.record_decision(req.approval_id, decision, principal.subject, rationale, edits, diff)
    changed = bool(diff)
    ctx.repo.append_audit(
        AuditEvent(
            run_id=run_id,
            company_id=run.company_id,
            step="human_approval",
            actor=principal.subject,
            event_type="approval_decided",
            created_at=datetime.now(UTC),
            payload={
                "approval_id": rec.approval_id,
                "decision": decision.value,
                "changed": changed,
                "plan_id": plan.plan_id,
                "policy_version": ctx.policy.version,
            },
        )
    )
    hours = ((rec.decided_at or datetime.now(UTC)) - rec.requested_at).total_seconds() / 3600
    metrics().approval_turnaround.record(hours, {"decision": decision.value})
    metrics().approval_decisions.add(1, {"decision": decision.value, "changed": str(changed).lower()})
    if run.params.get("mode") == "interactive":
        _finalize_interactive(ctx, run.run_state(), rec, plan.plan_id)
    # Automated enqueue is committed atomically by record_decision.
    return rec


def _finalize_interactive(ctx: RunContext, state: RunState, rec: ApprovalRecord, plan_id: str) -> None:
    """Interactive runs have no workflow steps, so the decision is applied here."""
    plan = ctx.repo.get_plan(plan_id)
    if rec.decision == ApprovalDecision.APPROVED:
        approved = rec.edits.get("approved_plan") or plan.plan
        ctx.repo.update_plan_status(plan_id, "approved", approved)
        kpi.activate_plan(
            ctx.repo, plan, approved, (rec.decided_at or datetime.now(UTC)).date(), actor=rec.decided_by or "unknown"
        )
        state.status, state.pause_reason = Status.COMPLETE, None
    elif rec.decision == ApprovalDecision.REJECTED:
        ctx.repo.update_plan_status(plan_id, "rejected")
        state.status = Status.REJECTED
        state.pause_reason = {"reason": "rejected", "rationale": rec.rationale}
    else:
        ctx.repo.update_plan_status(plan_id, "superseded")
        state.status, state.pause_reason = Status.RUNNING, {"reason": "changes_requested", "notes": rec.rationale}
    ctx.repo.save_run_state(state)


def override_stats(ctx: RunContext) -> dict[str, Any]:
    """Share of decided approvals where the human changed or rejected the recommendation (PVC-063)."""
    decided: list[ApprovalRecord] = []
    for run in ctx.repo.list_runs():
        decided += [a for a in ctx.repo.list_approvals(run.run_id) if a.decision is not None]
    changed = sum(1 for a in decided if a.diff or a.decision != ApprovalDecision.APPROVED)
    return {
        "decisions": len(decided),
        "changed_or_rejected": changed,
        "override_rate": round(changed / len(decided), 4) if decided else None,
    }
