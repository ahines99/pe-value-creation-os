"""PVC-040..046, PVC-061, PVC-064, PVC-134: workflow engine, approval gate, worker, CLI."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from pe_value_os import security
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.domain.runs import ApprovalDecision, Status
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.workflows import faults, primary
from pe_value_os.workflows import steps as S
from pe_value_os.workflows.steps import RunContext

pytestmark = pytest.mark.anyio
configure_logging(stream=io.StringIO())


@pytest.fixture
def ctx(tmp_path):
    from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore

    return RunContext(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")), adapter=FixtureAdapter(),
                      policy=get_policy())


def scoped(*companies):
    return security.principal_scope(security.system_principal(*companies))


async def run(ctx, cid, **kw):
    rec, _ = primary.start(ctx, cid, "human:test", **kw)
    return rec, await primary.execute(ctx, rec.run_id, backoff_s=0)


def approve(ctx, run_id, decision=ApprovalDecision.APPROVED, rationale="ok", edits=None):
    a = ctx.repo.latest_approval(run_id)
    return ctx.repo.record_decision(a.approval_id, decision, "human:approver", rationale, edits or {})


# --- PVC-043: primary workflow on fixtures ---------------------------------------------------------------------
async def test_pricing_leak_end_to_end(ctx):
    with scoped("beacon-pricing"):
        rec, st = await run(ctx, "beacon-pricing")
        assert st.status == Status.AWAITING_APPROVAL and st.current_step == "human_approval"
        opps = {o.baseline_metric: o for o in ctx.repo.list_opportunities(rec.run_id)}
        assert {"discounted_arr", "renewing_arr", "legacy_price_book_arr"} <= set(opps)
        assert opps["discounted_arr"].metric_params == {"segment": "mid_market"}
        ranking = ctx.repo.list_priorities(rec.run_id)
        assert [p.rank for p in ranking] == list(range(1, len(ranking) + 1))
        plan = ctx.repo.latest_plan(rec.run_id)
        titles = [i["title"] for ws in plan.plan["workstreams"] for i in ws["initiatives"]]
        assert "Discount governance in mid_market" in titles
        for o in ctx.repo.list_opportunities(rec.run_id):
            vc = ctx.repo.get_value_case("beacon-pricing", o.opportunity_id)
            assert vc.inputs_hash and o.evidence_ids


async def test_broken_company_pauses_with_gaps(ctx):
    with scoped("delta-broken"):
        rec, st = await run(ctx, "delta-broken")
        assert st.status == Status.NEEDS_EVIDENCE and st.current_step == "data_sufficiency"
        codes = {(g["analysis"], g["code"]) for g in st.pause_reason["gaps"]}
        assert ("pricing", "missing_dataset") in codes and ("unit_economics", "month_gaps") in codes
        types = {f.finding_type.value for f in ctx.repo.list_findings(rec.run_id)}
        assert {"data_gap", "suspicious_content"} <= types


async def test_accept_gaps_is_audited_and_continues(ctx):
    with scoped("delta-broken"):
        rec, _ = await run(ctx, "delta-broken")
        st = await primary.resume(ctx, rec.run_id, "human:operator", accept_gaps=True, reason="proceed on retention")
        assert st.status == Status.AWAITING_APPROVAL
        resumed = [e for e in ctx.repo.list_audit(run_id=rec.run_id) if e.event_type == "run_resumed"]
        assert resumed and resumed[0].actor == "human:operator" and resumed[0].payload["accept_gaps"] is True
        assert st.artifacts["diagnostics"]["results"]["pricing"]["skipped"] is True


# --- PVC-040/041: checkpoints, resume, idempotency -------------------------------------------------------------
async def test_state_checkpointed_and_audited_every_step(ctx):
    with scoped("acme-healthy"):
        rec, _ = await run(ctx, "acme-healthy")
        events = [(e.step, e.event_type) for e in ctx.repo.list_audit(run_id=rec.run_id)]
        for step in primary.STEP_ORDER[:-1]:
            assert (step, "step_started") in events and (step, "step_completed") in events
        assert ctx.repo.get_run(rec.run_id).completed_steps == primary.STEP_ORDER[:-1]


class Crash(BaseException):
    """Simulates the process dying mid-step (not an Exception, so the runner cannot catch it)."""


async def test_crash_then_resume_skips_finished_steps(ctx, monkeypatch):
    calls: list[str] = []
    originals = {n: getattr(S, n) for n in ("intake", "data_sufficiency", "value_modeling")}

    def counted(name):
        def f(c, s):
            calls.append(name)
            if name == "value_modeling" and calls.count("value_modeling") == 1:
                raise Crash()
            return originals[name](c, s)
        return f

    for n in originals:
        monkeypatch.setattr(S, n, counted(n))
    with scoped("beacon-pricing"):
        rec, _ = primary.start(ctx, "beacon-pricing", "human:test")
        with pytest.raises(Crash):
            await primary.execute(ctx, rec.run_id, backoff_s=0)
        saved = ctx.repo.get_run(rec.run_id)
        assert saved.completed_steps == ["intake", "data_sufficiency", "diagnostics"]
        fresh = RunContext(repo=ctx.repo, adapter=FixtureAdapter(), policy=ctx.policy)  # "new process"
        st = await primary.execute(fresh, rec.run_id, backoff_s=0)
        assert st.status == Status.AWAITING_APPROVAL
        assert calls == ["intake", "data_sufficiency", "value_modeling", "value_modeling"]


async def test_idempotency_key_returns_existing_run(ctx):
    with scoped("acme-healthy"):
        r1, c1 = primary.start(ctx, "acme-healthy", "human:a", idempotency_key="q3-diagnostic")
        r2, c2 = primary.start(ctx, "acme-healthy", "human:a", idempotency_key="q3-diagnostic")
        assert c1 and not c2 and r1.run_id == r2.run_id


async def test_rerunning_steps_does_not_duplicate_records(ctx):
    with scoped("beacon-pricing"):
        rec, _ = await run(ctx, "beacon-pricing")
        n_f, n_o = len(ctx.repo.list_findings(rec.run_id)), len(ctx.repo.list_opportunities(rec.run_id))
        state = ctx.repo.get_run(rec.run_id).run_state()
        state.completed_steps = ["intake", "data_sufficiency"]  # force diagnostics and later to re-run
        ctx.repo.save_run_state(state)
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        assert len(ctx.repo.list_findings(rec.run_id)) == n_f
        assert len(ctx.repo.list_opportunities(rec.run_id)) == n_o


# --- PVC-042 / PVC-046: parallel branches and injected failures --------------------------------------------------
async def test_one_failed_branch_run_continues(ctx):
    with scoped("beacon-pricing"), faults.inject(branch="retention", fault=faults.Fault("error", times=99)):
        _, st = await run(ctx, "beacon-pricing")
    assert st.status == Status.AWAITING_APPROVAL
    diag = st.artifacts["diagnostics"]
    assert "retention" in diag["failures"] and "pricing" in diag["results"]
    assert any(e.startswith("diagnostics.retention") for e in st.errors)


async def test_all_branches_failing_fails_the_step(ctx):
    with scoped("acme-healthy"):
        with faults.inject(branch="pricing", fault=faults.Fault("error", 99)), \
                faults.inject(branch="retention", fault=faults.Fault("error", 99)), \
                faults.inject(branch="unit_economics", fault=faults.Fault("error", 99)), \
                faults.inject(branch="ai_opportunity", fault=faults.Fault("error", 99)):
            _, st = await run(ctx, "acme-healthy")
    assert st.status == Status.FAILED and st.current_step == "diagnostics"


async def test_value_modeling_failure_fails_cleanly_then_resumes(ctx):
    with scoped("beacon-pricing"):
        with faults.inject(step="value_modeling", fault=faults.Fault("error", times=1)):
            rec, st = await run(ctx, "beacon-pricing")
            assert st.status == Status.FAILED and st.current_step == "value_modeling"
            assert "injected fault" in st.errors[-1]
            assert any(e.event_type == "step_failed" for e in ctx.repo.list_audit(run_id=rec.run_id))
        st = await primary.resume(ctx, rec.run_id, "human:operator", reason="fault cleared")
        assert st.status == Status.AWAITING_APPROVAL


async def test_branches_run_concurrently(ctx, monkeypatch):
    import threading
    import time

    active, peak, lock = [0], [0], threading.Lock()
    original = S.diagnostic_branch

    def slow(c, s, branch):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        return original(c, s, branch)

    monkeypatch.setattr(S, "diagnostic_branch", slow)
    with scoped("acme-healthy"):
        await run(ctx, "acme-healthy")
    assert peak[0] >= 2


# --- PVC-044: retries and timeouts ------------------------------------------------------------------------------
async def test_transient_adapter_errors_are_retried_and_audited(ctx):
    with scoped("acme-healthy"):
        rec, _ = primary.start(ctx, "acme-healthy", "human:t")
        ctx.adapter = faults.FaultInjectingAdapter(FixtureAdapter(), load_fault=faults.Fault("transient", times=2))
        st = await primary.execute(ctx, rec.run_id, backoff_s=0)
        assert st.status == Status.AWAITING_APPROVAL
        retries = [e for e in ctx.repo.list_audit(run_id=rec.run_id) if e.event_type == "step_retry"]
        assert [r.payload["attempt"] for r in retries] == [1, 2]


async def test_non_transient_errors_are_not_retried(ctx):
    with scoped("acme-healthy"):
        rec, _ = primary.start(ctx, "acme-healthy", "human:t")  # onboard with the healthy adapter first
        ctx.adapter = faults.FaultInjectingAdapter(FixtureAdapter(), load_fault=faults.Fault("error", times=1))
        st = await primary.execute(ctx, rec.run_id, backoff_s=0)
        assert st.status == Status.FAILED and "SourceError" in st.errors[-1]
        assert "step_retry" not in [e.event_type for e in ctx.repo.list_audit(run_id=rec.run_id)]


async def test_step_timeout_is_retried_then_fails(ctx, monkeypatch):
    import time

    monkeypatch.setattr(S, "intake", lambda c, s: time.sleep(2))
    with scoped("acme-healthy"):
        rec, _ = primary.start(ctx, "acme-healthy", "human:t")
        st = await primary.execute(ctx, rec.run_id, backoff_s=0, timeouts={"intake": 0.2})
        assert st.status == Status.FAILED and "TimeoutError" in st.errors[-1]
        assert len([e for e in ctx.repo.list_audit(run_id=rec.run_id) if e.event_type == "step_retry"]) == 2


# --- PVC-061: approval gate -------------------------------------------------------------------------------------
async def test_approval_completes_and_activates_kpis(ctx):
    with scoped("beacon-pricing"):
        rec, _ = await run(ctx, "beacon-pricing")
        approve(ctx, rec.run_id)
        st = await primary.resume(ctx, rec.run_id, "human:approver")
        assert st.status == Status.COMPLETE
        assert ctx.repo.latest_plan(rec.run_id).status == "approved"
        assert ctx.repo.list_kpi_definitions("beacon-pricing")


async def test_rejection_ends_run(ctx):
    with scoped("acme-healthy"):
        rec, _ = await run(ctx, "acme-healthy")
        approve(ctx, rec.run_id, ApprovalDecision.REJECTED, "not credible")
        st = await primary.resume(ctx, rec.run_id, "human:approver")
        assert st.status == Status.REJECTED and st.pause_reason["rationale"] == "not credible"
        assert (await primary.resume(ctx, rec.run_id, "human:x")).status == Status.REJECTED  # terminal


async def test_changes_requested_rewinds_and_excludes(ctx):
    with scoped("beacon-pricing"):
        rec, _ = await run(ctx, "beacon-pricing")
        first_plan = ctx.repo.latest_plan(rec.run_id)
        drop = next(o for o in ctx.repo.list_opportunities(rec.run_id) if o.baseline_metric == "renewing_arr")
        approve(ctx, rec.run_id, ApprovalDecision.CHANGES_REQUESTED, "Hold renewal uplifts until Q2",
                {"exclude_opportunities": [drop.opportunity_id]})
        st = await primary.resume(ctx, rec.run_id, "human:approver")
        assert st.status == Status.AWAITING_APPROVAL
        second = ctx.repo.latest_plan(rec.run_id)
        assert second.plan_id != first_plan.plan_id
        ids = [i["opportunity_id"] for ws in second.plan["workstreams"] for i in ws["initiatives"]]
        assert drop.opportunity_id not in ids
        assert "Hold renewal uplifts" in second.plan["narrative"]
        assert any(e.event_type == "run_rewound" for e in ctx.repo.list_audit(run_id=rec.run_id))
        approve(ctx, rec.run_id)
        assert (await primary.resume(ctx, rec.run_id, "human:approver")).status == Status.COMPLETE


# --- PVC-134 / PVC-064: worker ----------------------------------------------------------------------------------
async def test_worker_executes_queue_and_escalates(ctx, tmp_path):
    from pe_value_os.notify import OutboxNotifier
    from pe_value_os.worker import Worker

    with scoped("acme-healthy"):
        rec, _ = primary.start(ctx, "acme-healthy", "human:t")
    w = Worker(ctx, frozenset({"acme-healthy"}), worker_id="w-test", notifier=OutboxNotifier(tmp_path / "out"))
    report = await w.tick()
    assert report.runs_executed == 1
    with scoped("acme-healthy"):
        assert ctx.repo.get_run(rec.run_id).status == Status.AWAITING_APPROVAL
    later = datetime.now(UTC) + timedelta(hours=ctx.policy.approval.expiry_hours + 1)
    assert w.escalate_approvals(now=later) == 1
    assert w.escalate_approvals(now=later) == 0  # only once
    assert list((tmp_path / "out").glob("escalation-*.json"))
    with scoped("acme-healthy"):
        assert any(e.event_type == "approval_escalated" for e in ctx.repo.list_audit(run_id=rec.run_id))
        assert ctx.repo.get_run(rec.run_id).status == Status.AWAITING_APPROVAL  # never auto-approved


# --- PVC-045: CLI ------------------------------------------------------------------------------------------------
def test_cli_run_status_resume(monkeypatch, capsys, tmp_path):
    from pe_value_os import cli
    from pe_value_os.adapters import repositories

    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PVC_EVIDENCE_DIR", str(tmp_path / "ev"))
    repositories.set_repository(None)
    assert cli.main(["run", "--company", "delta-broken"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "needs_evidence"
    assert cli.main(["status", out["run_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["current_step"] == "data_sufficiency"
    assert cli.main(["resume", out["run_id"], "--accept-gaps", "--reason", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting_approval"
