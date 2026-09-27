"""Primary diagnostic workflow: wiring and run lifecycle (PVC-043, PVC-041).

intake -> data_sufficiency -> diagnostics (parallel: unit_economics, pricing, retention, ai_opportunity)
-> value_modeling -> evidence_review -> prioritization -> roadmap_100_day -> human_approval

KPI monitoring runs afterwards as a scheduled job (pe_value_os.kpi), not as a step.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

from ..domain.models import AuditEvent
from ..domain.runs import TERMINAL, RunRecord, RunState, Status
from ..policy import PolicyConfig
from . import steps as S
from .base import FunctionalStep, ParallelStep, Runner, Step, run_guarded_in_thread

STEP_ORDER = [
    "intake",
    "data_sufficiency",
    "diagnostics",
    "value_modeling",
    "evidence_review",
    "prioritization",
    "roadmap_100_day",
    "human_approval",
]
DIAGNOSTIC_BRANCHES = ["unit_economics", "pricing", "retention", "ai_opportunity"]


def _fn(ctx: S.RunContext, fn: Any) -> Any:
    async def run(state: RunState) -> Any:
        return await run_guarded_in_thread(ctx, fn, state)

    return run


def _branch(ctx: S.RunContext, name: str) -> Any:
    async def run(state: RunState) -> Any:
        return await run_guarded_in_thread(ctx, S.diagnostic_branch, state, name)

    return run


class DiagnosticsStep(ParallelStep):
    """Parallel diagnostics that pause the run when the model layer is unavailable (PVC-074)."""

    async def execute(self, state: RunState) -> RunState:
        state = await super().execute(state)
        results = state.artifacts[self.name]["results"]
        down = {b: r["model_unavailable"] for b, r in results.items() if r.get("model_unavailable")}
        if down:
            state.status = Status.NEEDS_EVIDENCE
            state.pause_reason = {
                "reason": "model_unavailable",
                "branches": down,
                "detail": "The model could not produce proposals; resume when it is available "
                "or set policy model.on_unavailable = 'rules'",
            }
        return state


def build_steps(ctx: S.RunContext, timeouts: dict[str, float] | None = None) -> list[Step]:
    t = timeouts or {}
    seq = {
        "intake": S.intake,
        "data_sufficiency": S.data_sufficiency,
        "value_modeling": S.value_modeling,
        "evidence_review": S.evidence_review,
        "prioritization": S.prioritization,
        "roadmap_100_day": S.roadmap_100_day,
        "human_approval": S.human_approval,
    }
    out: list[Step] = []
    for name in STEP_ORDER:
        if name == "diagnostics":
            out.append(
                DiagnosticsStep(
                    "diagnostics",
                    {b: _branch(ctx, b) for b in DIAGNOSTIC_BRANCHES},
                    timeout_s=t.get("diagnostics", 600.0),
                    branch_timeout_s=t.get("branch", 300.0),
                )
            )
        else:
            out.append(FunctionalStep(name, _fn(ctx, seq[name]), timeout_s=t.get(name, 300.0)))
    return out


def runner(ctx: S.RunContext, backoff_s: float = 0.5) -> Runner:
    return Runner(
        store=ctx.repo, audit=ctx.repo, actor=ctx.actor, backoff_s=backoff_s, policy_version=ctx.policy.version
    )


def start(
    ctx: S.RunContext,
    company_id: str,
    requested_by: str,
    *,
    idempotency_key: str | None = None,
    reference_date: date | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[RunRecord, bool]:
    """Create (or return the existing idempotent) run. Execution is separate: `execute` or the worker."""
    try:
        ctx.repo.get_company(company_id)
    except Exception:
        ctx.repo.upsert_company(ctx.adapter.load(company_id).profile)
    rec, created = ctx.repo.create_run(
        company_id, requested_by, idempotency_key=idempotency_key, reference_date=reference_date, params=params
    )
    if created:
        ctx.repo.append_audit(
            AuditEvent(
                run_id=rec.run_id,
                company_id=company_id,
                step="run",
                actor=requested_by,
                event_type="run_requested",
                created_at=datetime.now(UTC),
                payload={"idempotency_key": idempotency_key or ""},
            )
        )
    return rec, created


async def execute(
    ctx: S.RunContext, run_id: str, *, backoff_s: float = 0.5, timeouts: dict[str, float] | None = None
) -> RunState:
    rec = ctx.repo.get_run(run_id)
    state = rec.run_state()
    if state.status in TERMINAL:
        return state
    # A process restart must not mix a new export/policy with already completed calculations.
    data = (
        {state.company_id: S.load_snapshot(ctx, state.artifacts["input_snapshot"])}
        if "input_snapshot" in state.artifacts
        else {}
    )
    policy = (
        PolicyConfig.model_validate(state.artifacts["policy_snapshot"])
        if "policy_snapshot" in state.artifacts
        else ctx.policy
    )
    ctx = replace(ctx, _data=data, policy=policy)
    return await runner(ctx, backoff_s).run(state, build_steps(ctx, timeouts))


async def resume(
    ctx: S.RunContext,
    run_id: str,
    requested_by: str,
    *,
    accept_gaps: bool = False,
    reason: str | None = None,
    backoff_s: float = 0.5,
    timeouts: dict[str, float] | None = None,
) -> RunState:
    """Resume a paused or failed run. `accept_gaps` is a human decision to proceed despite data gaps."""
    rec = ctx.repo.get_run(run_id)
    state = rec.run_state()
    if state.status in TERMINAL:
        return state
    if accept_gaps:
        state.params["accept_gaps"] = True
    ctx.repo.save_run_state(state)
    ctx.repo.append_audit(
        AuditEvent(
            run_id=run_id,
            company_id=rec.company_id,
            step=state.current_step or "run",
            actor=requested_by,
            event_type="run_resumed",
            created_at=datetime.now(UTC),
            payload={"accept_gaps": accept_gaps, "reason_code": (reason or "")[:80]},
        )
    )
    return await execute(ctx, run_id, backoff_s=backoff_s, timeouts=timeouts)


def refresh_inputs(ctx: S.RunContext, run_id: str, requested_by: str, *, reason: str) -> RunRecord:
    """Queue a clean, linked diagnostic; preserve the original run's inputs and derived audit history."""
    if not reason.strip():
        raise ValueError("A reason is required to refresh inputs")
    original = ctx.repo.get_run(run_id)
    params = {
        k: v
        for k, v in original.params.items()
        if k
        not in {"mode", "accept_gaps", "reviewer_notes", "excluded_opportunities", "consumed_approvals", "review_round"}
    }
    params["supersedes_run_id"] = run_id
    fresh, _ = start(ctx, original.company_id, requested_by, params=params)
    ctx.repo.append_audit(
        AuditEvent(
            run_id=run_id,
            company_id=original.company_id,
            step="run",
            actor=requested_by,
            event_type="input_refresh_requested",
            created_at=datetime.now(UTC),
            payload={"replacement_run_id": fresh.run_id, "reason": reason.strip()[:500]},
        )
    )
    return fresh


def status(ctx: S.RunContext, run_id: str) -> dict[str, Any]:
    rec = ctx.repo.get_run(run_id)
    st = rec.run_state()
    return {
        "run_id": rec.run_id,
        "company_id": rec.company_id,
        "status": st.status.value,
        "current_step": st.current_step,
        "completed_steps": st.completed_steps,
        "pause_reason": st.pause_reason,
        "errors": st.errors,
        "updated_at": rec.updated_at.isoformat(),
        "paused": st.status in (Status.NEEDS_EVIDENCE, Status.AWAITING_APPROVAL),
    }
