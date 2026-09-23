"""PVC-031/032/033/034/035: one contract suite for both repository implementations."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from pe_value_os import security
from pe_value_os.adapters.base import make_evidence
from pe_value_os.adapters.evidence_store import ImmutableEvidenceError
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.domain.kpi_models import KpiDefinition, Notification
from pe_value_os.domain.models import AuditEvent, Finding, FindingType
from pe_value_os.domain.project_models import Opportunity, PriorityScore, ScenarioInputs, ValueCase
from pe_value_os.domain.runs import ApprovalDecision, PlanRecord, RunState, Status
from pe_value_os.domain.source_models import CompanyProfile

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def profile(cid):
    return CompanyProfile(
        company_id=cid, name=cid.title(), business_model="SaaS", vertical="v", currency="USD", fiscal_year_start_month=1
    )


def onboard(repo, cid, content=b"a,b\n1,2\n"):
    repo.upsert_company(profile(cid))
    return repo.add_evidence(make_evidence(cid, f"test://{cid}/f.csv", "dataset:test", content, NOW))


def s(i, r):
    return ScenarioInputs(improvement_rate=Decimal(i), realization_rate=Decimal(r))


def opportunity(run_id, cid, ev, oid="11111111-1111-1111-1111-111111111111"):
    return Opportunity(
        opportunity_id=oid,
        run_id=run_id,
        company_id=cid,
        lever="pricing",
        title="Uplift",
        baseline_metric="renewing_arr",
        baseline_value=Decimal("1000000"),
        ebitda_flow_through=Decimal("0.95"),
        low=s("0.01", "0.5"),
        base=s("0.02", "0.6"),
        high=s("0.03", "0.7"),
        confidence="medium",
        rationale="r",
        evidence_ids=[ev],
    )


def test_evidence_dedupe_and_immutability(repo, as_companies):
    with as_companies("a"):
        ev1 = onboard(repo, "a")
        ev2 = onboard(repo, "a")
        assert ev1 == ev2 and len(repo.list_evidence("a")) == 1
        assert repo.evidence_content(ev1) == b"a,b\n1,2\n"
        with pytest.raises(ImmutableEvidenceError):
            repo.evidence_store.put_original("a", ev1, b"tampered")


def test_runs_idempotency_state_and_listing(repo, as_companies):
    with as_companies("a"):
        onboard(repo, "a")
        r1, created1 = repo.create_run("a", "tester", idempotency_key="k1", reference_date=date(2026, 9, 15))
        r2, created2 = repo.create_run("a", "tester", idempotency_key="k1")
        assert created1 and not created2 and r1.run_id == r2.run_id
        st = RunState(
            run_id=r1.run_id,
            company_id="a",
            status=Status.AWAITING_APPROVAL,
            current_step="human_approval",
            completed_steps=["intake"],
            artifacts={"intake": {"x": "1"}},
            reference_date=date(2026, 9, 15),
        )
        repo.save_run_state(st)
        back = repo.get_run(r1.run_id)
        assert back.status == Status.AWAITING_APPROVAL and back.completed_steps == ["intake"]
        assert back.run_state().artifacts == {"intake": {"x": "1"}}
        assert [r.run_id for r in repo.list_runs("a", Status.AWAITING_APPROVAL)] == [r1.run_id]


def test_findings_opportunities_value_cases(repo, as_companies):
    with as_companies("a"):
        ev = onboard(repo, "a")
        run, _ = repo.create_run("a", "t")
        f = Finding(
            finding_id="22222222-2222-2222-2222-222222222222",
            run_id=run.run_id,
            company_id="a",
            finding_type=FindingType.OBSERVATION,
            title="t",
            statement="s",
            confidence="low",
            evidence_ids=[ev],
        )
        repo.add_finding(f)
        assert repo.list_findings(run.run_id)[0].evidence_ids == [ev]
        o = opportunity(run.run_id, "a", ev)
        repo.add_opportunity(o, proposer="rules")
        assert repo.get_opportunity("a", o.opportunity_id).baseline_value == Decimal("1000000")
        assert [e.evidence_id for e in repo.evidence_for_opportunity("a", o.opportunity_id)] == [ev]
        vc1 = ValueCase(
            opportunity_id=o.opportunity_id,
            annual_ebitda_low=Decimal(1),
            annual_ebitda_base=Decimal(2),
            annual_ebitda_high=Decimal(3),
            one_time_cost=Decimal(0),
            calc_version="v1",
            inputs_hash="h1",
        )
        repo.save_value_case("a", run.run_id, vc1, "p1")
        repo.save_value_case(
            "a", run.run_id, vc1.model_copy(update={"annual_ebitda_base": Decimal(5), "inputs_hash": "h2"}), "p1"
        )
        assert repo.get_value_case("a", o.opportunity_id).annual_ebitda_base == Decimal(5)
        assert len(repo.list_value_cases(run.run_id)) == 1
        repo.save_priorities(
            run.run_id,
            "a",
            [
                PriorityScore(
                    opportunity_id=o.opportunity_id,
                    rank=1,
                    score=Decimal("0.5"),
                    components={"ebitda": Decimal(1)},
                    run_rate_ebitda_base=Decimal(5),
                    in_year_ebitda_base=Decimal(2),
                    start_month=3,
                )
            ],
        )
        assert repo.list_priorities(run.run_id)[0].rank == 1


def test_evidence_from_another_company_cannot_be_cited(repo, as_companies):
    with as_companies("a", "b"):
        onboard(repo, "a")
        ev_b = onboard(repo, "b", b"other")
        run, _ = repo.create_run("a", "t")
        f = Finding(
            finding_id="33333333-3333-3333-3333-333333333333",
            run_id=run.run_id,
            company_id="a",
            finding_type=FindingType.OBSERVATION,
            title="t",
            statement="s",
            confidence="low",
            evidence_ids=[ev_b],
        )
        with pytest.raises(NotFound):
            repo.add_finding(f)


def test_cross_company_isolation(repo, as_companies):
    with as_companies("a", "b"):
        onboard(repo, "a")
        ev_b = onboard(repo, "b", b"b-data")
        run_b, _ = repo.create_run("b", "t")
    with as_companies("a"):
        with pytest.raises(NotFound):
            repo.get_run(run_b.run_id)
        with pytest.raises(NotFound):
            repo.get_evidence(ev_b)
        with pytest.raises(security.ScopeError):
            repo.list_evidence("b")
        with pytest.raises(security.ScopeError):
            repo.create_run("b", "t")
        assert repo.list_runs() == [] and repo.list_companies() == ["a"]
        assert repo.list_audit() == []


def test_plans_and_approvals(repo, as_companies):
    with as_companies("a"):
        onboard(repo, "a")
        run, _ = repo.create_run("a", "t")
        p1 = PlanRecord(
            plan_id="44444444-4444-4444-4444-444444444444",
            run_id=run.run_id,
            company_id="a",
            status="proposed",
            plan={"v": 1},
            created_at=NOW,
        )
        repo.save_plan(p1)
        p2 = p1.model_copy(
            update={
                "plan_id": "55555555-5555-5555-5555-555555555555",
                "plan": {"v": 2},
                "created_at": datetime(2026, 9, 2, tzinfo=UTC),
            }
        )
        repo.save_plan(p2)
        assert repo.get_plan(p1.plan_id).status == "superseded"
        assert repo.latest_plan(run.run_id).plan == {"v": 2}
        a1 = repo.create_approval_request(run.run_id, "a", "plan", p2.plan_id)
        assert repo.create_approval_request(run.run_id, "a", "plan", p2.plan_id).approval_id == a1.approval_id
        assert [x.approval_id for x in repo.pending_approvals()] == [a1.approval_id]
        done = repo.record_decision(a1.approval_id, ApprovalDecision.APPROVED, "human:jo", "ok")
        assert done.decision == ApprovalDecision.APPROVED and done.decided_by == "human:jo"
        with pytest.raises(Conflict):
            repo.record_decision(a1.approval_id, ApprovalDecision.REJECTED, "human:jo", "changed mind")
        repo.update_plan_status(p2.plan_id, "approved")
        assert repo.get_plan(p2.plan_id).approved_plan == {"v": 2}
        assert repo.pending_approvals() == []


def test_audit_append_and_list(repo, as_companies):
    with as_companies("a"):
        onboard(repo, "a")
        run, _ = repo.create_run("a", "t")
        for i in range(3):
            repo.append_audit(
                AuditEvent(
                    run_id=run.run_id,
                    company_id="a",
                    step="s",
                    event_type=f"e{i}",
                    actor="x",
                    created_at=NOW,
                    payload={"i": i},
                )
            )
        assert [e.event_type for e in repo.list_audit(run_id=run.run_id)] == ["e0", "e1", "e2"]


def test_claim_and_resume(repo, as_companies):
    with as_companies("a"):
        onboard(repo, "a")
        run, _ = repo.create_run("a", "t")
        claimed = repo.claim_runnable("w1")
        assert [r.run_id for r in claimed] == [run.run_id]
        assert repo.claim_runnable("w2") == []  # locked
        repo.save_run_state(RunState(run_id=run.run_id, company_id="a", status=Status.AWAITING_APPROVAL))
        repo.release_run(run.run_id)
        assert repo.claim_runnable("w2") == []  # paused, no resume requested
        repo.request_resume(run.run_id)
        assert [r.run_id for r in repo.claim_runnable("w2")] == [run.run_id]


def test_kpis_notifications_and_deletion(repo, as_companies):
    with as_companies("a"):
        ev = onboard(repo, "a")
        run, _ = repo.create_run("a", "t")
        plan = PlanRecord(
            plan_id="66666666-6666-6666-6666-666666666666",
            run_id=run.run_id,
            company_id="a",
            status="approved",
            plan={},
            created_at=NOW,
        )
        repo.save_plan(plan)
        kd = KpiDefinition(
            kpi_id="77777777-7777-7777-7777-777777777777",
            company_id="a",
            plan_id=plan.plan_id,
            run_id=run.run_id,
            metric="grr",
            description="GRR",
            baseline=Decimal("0.86"),
            day_100_target=Decimal("0.87"),
            run_rate_target=Decimal("0.9"),
            direction="increase",
            cadence_days=30,
            source="arr",
            evidence_ids=[ev],
            start_date=date(2026, 9, 15),
            created_at=NOW,
        )
        repo.save_kpi_definitions([kd])
        assert repo.list_kpi_definitions("a")[0].metric == "grr"
        repo.add_notification(
            Notification(
                notification_id="88888888-8888-8888-8888-888888888888",
                company_id="a",
                channel="file",
                subject="s",
                body="b",
                created_at=NOW,
            )
        )
        assert len(repo.list_notifications("a")) == 1
        counts = repo.delete_company_data("a")
        assert counts["runs"] == 1 and counts["evidence_objects"] == 1
        assert repo.list_companies() == [] and repo.list_evidence("a") == []


def test_fixture_adapter_registers_stable_evidence(repo, as_companies):
    with as_companies("acme-healthy"):
        a = FixtureAdapter()
        repo.upsert_company(a.load("acme-healthy").profile)
        d1 = a.load("acme-healthy", sink=repo)
        d2 = a.load("acme-healthy", sink=repo)
        ids1 = sorted(ds.evidence_id for ds in d1.datasets.values())
        assert ids1 == sorted(ds.evidence_id for ds in d2.datasets.values())
        stored = {e.evidence_id for e in repo.list_evidence("acme-healthy")}
        assert set(ids1) <= stored and d1.profile_evidence_id in stored


@pytest.mark.postgres
def test_audit_is_append_only_for_app_role(pg_repo, as_companies):
    import psycopg

    with as_companies("a"):
        onboard(pg_repo, "a")
        pg_repo.append_audit(
            AuditEvent(run_id=None, company_id="a", step="s", event_type="e", actor="x", created_at=NOW)
        )
        for stmt in ("update audit_events set actor = 'evil'", "delete from audit_events"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with pg_repo._tx() as cur:
                    cur.execute(stmt)
        assert pg_repo.list_audit()[0].actor == "x"


@pytest.mark.postgres
def test_rls_filters_unfiltered_queries(pg_repo, as_companies):
    with as_companies("a", "b"):
        onboard(pg_repo, "a")
        onboard(pg_repo, "b", b"b")
        pg_repo.create_run("a", "t")
        pg_repo.create_run("b", "t")
    with as_companies("a"), pg_repo._tx() as cur:
        rows = cur.execute("select company_id from workflow_runs").fetchall()  # deliberately unfiltered
        assert {r["company_id"] for r in rows} == {"a"}
        assert cur.execute("select count(*) as n from evidence").fetchone()["n"] == 1
    with security.principal_scope(security.Principal(subject="nobody", companies=frozenset())), pg_repo._tx() as cur:
        assert cur.execute("select count(*) as n from companies").fetchone()["n"] == 0


@pytest.mark.postgres
def test_rls_blocks_cross_company_writes(pg_repo, as_companies):
    import psycopg

    with as_companies("a", "b"):
        onboard(pg_repo, "a")
        onboard(pg_repo, "b", b"b")
    with as_companies("a"), pytest.raises(psycopg.errors.InsufficientPrivilege), pg_repo._tx() as cur:
        cur.execute("insert into audit_events (company_id, step, actor, event_type) values ('b', 's', 'x', 'e')")
