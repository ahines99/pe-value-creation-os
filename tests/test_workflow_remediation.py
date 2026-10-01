"""Regression coverage for review lifecycle, leases, snapshots and durable delivery."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio
import pytest

from pe_value_os import approvals, kpi, security
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository, LeaseLost
from pe_value_os.domain.baselines import LEVER_METRICS, derive_baseline
from pe_value_os.domain.calc import add_months
from pe_value_os.domain.kpi_models import KpiObservation, Notification
from pe_value_os.domain.project_models import Opportunity, ScenarioInputs
from pe_value_os.domain.runs import ApprovalDecision, Status
from pe_value_os.policy import get_policy
from pe_value_os.worker import Worker
from pe_value_os.workflows import primary
from pe_value_os.workflows.planning import _kpi
from pe_value_os.workflows.steps import RunContext
from tests.test_repository_contract import onboard

CID = "beacon-pricing"


def context(repo):
    return RunContext(repo=repo, adapter=FixtureAdapter(), policy=get_policy())


@pytest.mark.anyio
async def test_identical_review_rounds_pause_once_and_create_fresh_request(repo):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test")
        state = await primary.execute(ctx, rec.run_id, backoff_s=0)
        assert state.status == Status.AWAITING_APPROVAL
        ids = []
        for _ in range(3):
            a = repo.latest_approval(rec.run_id)
            ids.append(a.approval_id)
            repo.record_decision(a.approval_id, ApprovalDecision.CHANGES_REQUESTED, "human", "Same notes")
            with anyio.fail_after(15):
                state = await primary.execute(ctx, rec.run_id, backoff_s=0)
            assert state.status == Status.AWAITING_APPROVAL
            assert repo.latest_approval(rec.run_id).decision is None
        assert len(repo.list_approvals(rec.run_id)) == 4
        assert state.params["consumed_approvals"] == sorted(ids)


def expire(repo, run_id, request):
    if isinstance(repo, InMemoryRepository):
        repo.lease_times[run_id] = datetime.now(UTC) - timedelta(hours=1)
    else:
        import psycopg

        admin, _ = request.getfixturevalue("pg_database")
        with psycopg.connect(admin) as conn:
            conn.execute("update workflow_runs set locked_at = now() - interval '1 hour' where run_id = %s", (run_id,))


def test_expired_running_run_is_reclaimed_and_old_owner_cannot_write(repo, as_companies, request):
    with as_companies("a"):
        onboard(repo, "a")
        run, _ = repo.create_run("a", "tester")
        assert repo.claim_runnable("old", 1)[0].run_id == run.run_id
        old = repo.fenced_run(run.run_id, "old")
        state = run.run_state()
        state.status = Status.RUNNING
        old.save_run_state(state)
        expire(repo, run.run_id, request)
        assert not repo.renew_lease(run.run_id, "old")
        with pytest.raises(LeaseLost):
            old.save_run_state(state)
        assert repo.claim_runnable("new", 1)[0].run_id == run.run_id
        with pytest.raises(LeaseLost):
            old.save_run_state(state)
        with pytest.raises(LeaseLost):
            old.request_resume(run.run_id)
        assert repo.renew_lease(run.run_id, "new")
        repo.release_run(run.run_id, "old")
        assert repo.renew_lease(run.run_id, "new")


def test_notification_claim_is_shared_retryable_and_acknowledged(repo, as_companies):
    with as_companies("a"):
        onboard(repo, "a")
        n = Notification(
            notification_id=str(uuid.uuid4()),
            company_id="a",
            channel="outbox",
            subject="x",
            body="x",
            created_at=datetime.now(UTC),
        )
        assert repo.claim_notification(n, "a")
        assert not repo.claim_notification(n, "b")
        repo.finish_notification(n.notification_id, "a", delivered=False)
        assert repo.claim_notification(n, "b")
        with pytest.raises(LeaseLost):
            repo.finish_notification(n.notification_id, "a", delivered=True)
        repo.finish_notification(n.notification_id, "b", delivered=True)
        assert not repo.claim_notification(n, "c")
        stored = repo.list_notifications("a")
        assert len(stored) == 1 and stored[0].delivered_at is not None


@pytest.mark.anyio
async def test_resume_uses_persisted_source_and_policy_after_process_restart(repo):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test")
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        a = repo.latest_approval(rec.run_id)
        repo.record_decision(a.approval_id, ApprovalDecision.CHANGES_REQUESTED, "human", "Review again")

        class NoSource:
            def load(self, *args, **kwargs):
                raise AssertionError("A resume must not fetch a new source export")

        restarted = replace(
            ctx, adapter=NoSource(), _data={}, policy=ctx.policy.model_copy(update={"version": "changed"})
        )
        state = await primary.execute(restarted, rec.run_id, backoff_s=0)
        assert state.status == Status.AWAITING_APPROVAL
        assert state.artifacts["policy_snapshot"]["version"] == ctx.policy.version
        assert repo.get_run(rec.run_id).resume_requested_at is not None  # durable decision enqueue


@pytest.mark.parametrize(
    "lever,metric", [(lever, metric) for lever, metrics in LEVER_METRICS.items() for metric in sorted(metrics)]
)
def test_every_valid_baseline_has_evidence_backed_kpi(lever, metric):
    data = FixtureAdapter().load(CID)
    policy = get_policy()
    baseline = derive_baseline(data, lever, metric, {}, policy)
    scenario = ScenarioInputs(improvement_rate=Decimal("0.05"), realization_rate=Decimal("0.5"))
    opp = Opportunity(
        opportunity_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        company_id=CID,
        lever=lever,
        title="Measured improvement",
        baseline_metric=metric,
        baseline_value=baseline.baseline.value,
        ebitda_flow_through=baseline.ebitda_flow_through,
        low=scenario,
        base=scenario,
        high=scenario,
        confidence="medium",
        rationale="test",
        evidence_ids=baseline.evidence_ids,
    )
    definition = _kpi(opp, data, policy)
    assert definition and definition.evidence_ids and definition.monitorable
    kpi.check_monitorable(
        {
            "workstreams": [
                {"initiatives": [{"opportunity_id": opp.opportunity_id}], "kpis": [definition.model_dump(mode="json")]}
            ]
        }
    )


def test_missing_initiative_kpi_cannot_be_approved():
    with pytest.raises(kpi.UnmonitorableKpi, match="missing"):
        kpi.check_monitorable({"workstreams": [{"initiatives": [{"opportunity_id": "missing"}], "kpis": []}]})


class FlakyNotifier:
    channel = "outbox"

    def __init__(self):
        self.attempts = 0

    def deliver(self, repo, n):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("temporary delivery failure")

    def escalate(self, repo, approval, contact):
        self.deliver(repo, None)


@pytest.mark.anyio
async def test_failed_escalation_retries_before_marking_complete(repo):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test")
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        a = repo.latest_approval(rec.run_id)
        notifier = FlakyNotifier()
        worker = Worker(ctx, frozenset({CID}), notifier=notifier)
        now = a.requested_at + timedelta(hours=ctx.policy.approval.expiry_hours + 1)
        with pytest.raises(RuntimeError):
            worker.escalate_approvals(now)
        assert repo.latest_approval(rec.run_id).escalated_at is None
        assert worker.escalate_approvals(now) == 1
        assert worker.escalate_approvals(now) == 0
        assert notifier.attempts == 2
        assert repo.list_notifications(CID)[0].status == "delivered"


@pytest.mark.anyio
async def test_digest_ticks_retry_then_dedupe_and_next_day_send(repo):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test")
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        a = repo.latest_approval(rec.run_id)
        repo.record_decision(a.approval_id, ApprovalDecision.APPROVED, "human", "ok")
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        now = datetime.now(UTC)
        for d in repo.list_kpi_definitions(CID):
            repo.add_kpi_observation(
                KpiObservation(
                    observation_id=str(uuid.uuid4()),
                    kpi_id=d.kpi_id,
                    company_id=CID,
                    observed_at=now,
                    period_end=add_months(now.date(), 1),  # a post-plan month; earlier readings are baselines
                    value=d.baseline,
                    target=d.run_rate_target,
                    status="off_track",
                    variance=Decimal("-1"),
                )
            )
        notifier = FlakyNotifier()
        worker = Worker(ctx, frozenset({CID}), notifier=notifier)
        assert worker.refresh_kpis(now) == (0, 0)
        assert worker.refresh_kpis(now) == (0, 1)
        replica = Worker(ctx, frozenset({CID}), notifier=notifier)
        assert replica.refresh_kpis(now) == (0, 0)
        assert replica.refresh_kpis(now + timedelta(days=1)) == (0, 1)
        assert notifier.attempts == 3 and len(repo.list_notifications(CID)) == 2


@pytest.mark.anyio
async def test_worker_claims_only_immediate_capacity(monkeypatch):
    repo = InMemoryRepository()
    ctx = context(repo)
    with security.principal_scope(security.system_principal("a")):
        onboard(repo, "a")
        runs = [repo.create_run("a", "test")[0] for _ in range(3)]

        async def execute(ctx, run_id):
            assert len(repo.locks) == 1
            state = repo.get_run(run_id).run_state()
            state.status = Status.COMPLETE
            ctx.repo.save_run_state(state)
            return state

        monkeypatch.setattr(primary, "execute", execute)
        assert await Worker(ctx, frozenset({"a"})).run_queue() == len(runs)


def test_removed_initiative_has_no_stale_plan_metadata():
    plan = {
        "workstreams": [
            {
                "lever": "pricing",
                "initiatives": [
                    {
                        "opportunity_id": "remove",
                        "title": "Removed",
                        "run_rate_ebitda_base": "2",
                        "in_year_ebitda_base": "1",
                    },
                    {
                        "opportunity_id": "keep",
                        "title": "Kept",
                        "run_rate_ebitda_base": "3",
                        "in_year_ebitda_base": "2",
                    },
                ],
                "kpis": [{"opportunity_id": "remove"}, {"opportunity_id": "keep"}],
                "risks": ["Removed: risk", "Kept: risk"],
                "milestones": {"day_30": ["Launch: Removed", "Launch: Kept"]},
            }
        ],
        "decisions_requiring_approval": ["Removed: approval", "Kept: approval"],
        "total_run_rate_ebitda_base": "5",
        "total_in_year_ebitda_base": "3",
        "narrative": "Do Removed",
    }
    edited, _ = approvals.apply_edits(plan, ["remove"])
    assert edited["workstreams"][0]["risks"] == ["Kept: risk"]
    assert edited["workstreams"][0]["milestones"]["day_30"] == ["Launch: Kept"]
    assert edited["decisions_requiring_approval"] == ["Kept: approval"]
    assert edited["total_run_rate_ebitda_base"] == "3"


@pytest.mark.anyio
async def test_explicit_refresh_queues_new_run_and_preserves_original_snapshot(repo):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test")
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        original = repo.get_run(rec.run_id).state
        with pytest.raises(ValueError, match="reason"):
            primary.refresh_inputs(ctx, rec.run_id, "human", reason=" ")
        fresh = primary.refresh_inputs(ctx, rec.run_id, "human", reason="Source export corrected")
        assert fresh.run_id != rec.run_id and fresh.status == Status.PENDING
        assert fresh.params["supersedes_run_id"] == rec.run_id
        assert fresh.run_state().artifacts == {}
        assert repo.get_run(rec.run_id).state == original
        assert repo.list_audit(run_id=rec.run_id)[-1].event_type == "input_refresh_requested"


@pytest.mark.anyio
async def test_lease_loss_cancels_inflight_worker_attempt(monkeypatch):
    import pe_value_os.worker as module

    repo = InMemoryRepository()
    ctx = context(repo)
    with security.principal_scope(security.system_principal("a")):
        onboard(repo, "a")
        rec, _ = repo.create_run("a", "test")
        cancelled = []

        async def execute(ctx, run_id):
            repo.release_run(run_id)
            assert repo.acquire_run(run_id, "replacement")
            try:
                await anyio.sleep(10)
            finally:
                cancelled.append(True)

        monkeypatch.setattr(primary, "execute", execute)
        monkeypatch.setattr(module, "HEARTBEAT_S", 0.01)
        with pytest.raises(ExceptionGroup) as error, anyio.fail_after(1):
            await Worker(ctx, frozenset({"a"})).run_queue()
        assert isinstance(error.value.exceptions[0], LeaseLost)
        assert cancelled and repo.renew_lease(rec.run_id, "replacement")


@pytest.mark.anyio
async def test_interactive_decision_rolls_back_if_activation_fails(repo, monkeypatch):
    ctx = context(repo)
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "test", params={"mode": "interactive"})
        await primary.execute(ctx, rec.run_id, backoff_s=0)
        principal = security.Principal(
            subject="human", companies=frozenset({CID}), roles=frozenset({"approver"}), principal_type="human"
        )
        old_activate = kpi.activate_plan

        def fail_after_writes(*args, **kwargs):
            old_activate(*args, **kwargs)
            raise RuntimeError("activation failed after writes")

        monkeypatch.setattr(kpi, "activate_plan", fail_after_writes)
        with pytest.raises(RuntimeError):
            approvals.decide(ctx, rec.run_id, principal, ApprovalDecision.APPROVED)
        assert repo.latest_approval(rec.run_id).decision is None
        assert repo.latest_plan(rec.run_id).status == "proposed"
        assert repo.list_kpi_definitions(CID) == []
        assert repo.get_run(rec.run_id).status == Status.AWAITING_APPROVAL
        assert not any(e.event_type == "approval_decided" for e in repo.list_audit(run_id=rec.run_id))
        monkeypatch.setattr(kpi, "activate_plan", old_activate)
        approvals.decide(ctx, rec.run_id, principal, ApprovalDecision.APPROVED)
        assert repo.get_run(rec.run_id).status == Status.COMPLETE
