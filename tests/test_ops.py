"""PVC-144/145/146 and PVC-120..123: ops commands and KPI monitoring."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio
import pytest

from pe_value_os import approvals, kpi, ops, security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.domain import services
from pe_value_os.domain.kpi_models import KpiObservation
from pe_value_os.domain.runs import ApprovalDecision
from pe_value_os.notify import OutboxNotifier
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

configure_logging(stream=io.StringIO())
CID = "beacon-pricing"


@pytest.fixture
def approved(tmp_path):
    ctx = RunContext(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")), adapter=FixtureAdapter(),
                     policy=get_policy())
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "human:t")
        anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        approvals.decide(ctx, rec.run_id, security.Principal(subject="human:ap", companies=frozenset({CID}),
                                                             roles=frozenset({"approver"}), principal_type="human"),
                         ApprovalDecision.APPROVED, rationale="ok")
        anyio.run(lambda: primary.resume(ctx, rec.run_id, "system:worker", backoff_s=0))
        yield ctx, rec.run_id


def test_recompute_is_audited_and_keeps_history(approved, monkeypatch):
    ctx, run_id = approved
    same = ops.recompute_run(ctx, run_id, "human:op", reason="INC-1")
    assert same["changed"] == [] and same["unchanged"] > 0
    original = services.size_value_case

    def buggy_fixed(opp, ev=None):  # simulate a new calculation version producing different numbers
        vc = original(opp, ev)
        return vc.model_copy(update={"calc_version": "value-case/2", "annual_ebitda_base": vc.annual_ebitda_base + 1})

    monkeypatch.setattr(ops, "size_value_case", buggy_fixed)
    monkeypatch.setattr(ops, "CALC_VERSION", "value-case/2")
    out = ops.recompute_run(ctx, run_id, "human:op", reason="INC-2")
    assert out["changed"] and all(c["calc_version_before"] == "value-case/1" for c in out["changed"])
    opp_id = out["changed"][0]["opportunity_id"]
    assert ctx.repo.get_value_case(CID, opp_id).calc_version == "value-case/2"
    assert len(ctx.repo.value_cases[opp_id]) == 2  # history kept
    ev = [e for e in ctx.repo.list_audit(run_id=run_id) if e.event_type == "value_cases_recomputed"]
    assert ev[-1].payload["reason_code"] == "INC-2" and ev[-1].actor == "human:op"
    with pytest.raises(ValueError):
        ops.recompute_run(ctx, run_id, "human:op", reason=" ")


def test_offboarding_deletes_data_but_retains_audit(approved, tmp_path):
    ctx, _ = approved
    out = ops.offboard_company(ctx, CID, "human:op")
    assert out["deleted"]["runs"] == 1 and out["deleted"]["evidence_objects"] > 0
    assert ctx.repo.list_evidence(CID) == [] and ctx.repo.list_kpi_definitions(CID) == []
    events = ctx.repo.list_audit(company_id=CID)
    assert {"company_offboarding_started", "company_offboarded", "approval_decided"} <= {e.event_type for e in events}
    n = ops.export_audit(ctx, CID, tmp_path / "audit.jsonl")
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert n == len(lines) > 5 and json.loads(lines[0])["company_id"] == CID


def test_access_review_flags(tmp_path):
    now = datetime(2026, 9, 23, tzinfo=UTC)
    grants = [
        {"subject": "model:claude", "principal_type": "model", "roles": ["approver"], "pvc_companies": ["a"]},
        {"subject": "human:wide", "principal_type": "human", "roles": ["approver"], "pvc_companies": list("abcdefg"),
         "last_login": (now - timedelta(days=1)).isoformat()},
        {"subject": "human:stale", "principal_type": "human", "roles": ["analyst"], "pvc_companies": ["a"],
         "last_login": (now - timedelta(days=200)).isoformat()},
        {"subject": "human:ok", "principal_type": "human", "roles": ["approver"], "pvc_companies": ["a"],
         "last_login": now.isoformat()},
    ]
    f = tmp_path / "grants.json"
    f.write_text(json.dumps(grants))
    rep = ops.access_review(f, now=now)
    by = {(x["subject"], x["severity"]) for x in rep["findings"]}
    assert ("model:claude", "high") in by and ("human:wide", "medium") in by and ("human:stale", "medium") in by
    assert not any(x["subject"] == "human:ok" for x in rep["findings"])


# --- KPI monitoring (PVC-120..123) -------------------------------------------------------------------------------
def test_kpis_activated_from_approved_plan(approved):
    ctx, run_id = approved
    defs = ctx.repo.list_kpi_definitions(CID)
    plan = ctx.repo.latest_plan(run_id)
    assert plan.status == "approved" and len(defs) == len(kpi.plan_kpis(plan.approved_plan)) >= 3
    assert all(d.evidence_ids and d.metric in kpi.REGISTRY for d in defs)


def test_unmonitorable_kpi_rejected_at_approval():
    with pytest.raises(kpi.UnmonitorableKpi):
        kpi.check_monitorable({"workstreams": [{"kpis": [{"metric": "vibes", "monitorable": True}]}]})


def test_refresh_is_cadenced_and_evidence_backed(approved):
    ctx, _ = approved
    t0 = datetime.now(UTC)
    first = kpi.refresh_company(ctx.repo, ctx.adapter, CID, ctx.policy, now=t0)
    assert first and all(o.status == "on_track" and o.evidence_ids for o in first)  # day 0: target == baseline
    assert kpi.refresh_company(ctx.repo, ctx.adapter, CID, ctx.policy, now=t0 + timedelta(days=1)) == []
    later = kpi.refresh_company(ctx.repo, ctx.adapter, CID, ctx.policy, now=t0 + timedelta(days=31))
    assert len(later) == len(first)


def test_target_path_interpolation(approved):
    ctx, _ = approved
    d = ctx.repo.list_kpi_definitions(CID)[0].model_copy(update={
        "baseline": Decimal("0.20"), "day_100_target": Decimal("0.18"), "run_rate_target": Decimal("0.12")})
    s = d.start_date
    assert kpi.target_on(d, s) == Decimal("0.20")
    assert kpi.target_on(d, s + timedelta(days=50)) == Decimal("0.19")
    assert kpi.target_on(d, s + timedelta(days=100)) == Decimal("0.18")
    assert kpi.target_on(d, s + timedelta(days=400)) == Decimal("0.12")


def test_variance_threshold_and_trend(approved):
    ctx, _ = approved
    d = next(x for x in ctx.repo.list_kpi_definitions(CID) if x.direction == "decrease")
    policy = ctx.policy

    def obs(v, t, status="on_track"):
        return KpiObservation(observation_id=f"o{v}", kpi_id=d.kpi_id, company_id=CID, observed_at=datetime.now(UTC),
                              period_end=None, value=Decimal(v), target=Decimal(t), status=status,
                              variance=Decimal(0))

    assert kpi.detect_variance(d, [obs("0.10", "0.10")], policy) == []
    off, var = kpi._off_track(d, Decimal("0.30"), Decimal("0.20"), policy.kpi.off_track_tolerance)
    assert off and var == Decimal("-0.1000")
    assert not kpi._off_track(d, Decimal("0.21"), Decimal("0.20"), policy.kpi.off_track_tolerance)[0]  # within 10%
    rising = [obs(v, "0.5") for v in ("0.10", "0.11", "0.12", "0.13")]
    assert [a.rule for a in kpi.detect_variance(d, rising, policy)] == ["trend"]
    th = kpi.detect_variance(d, [obs("0.3", "0.2", "off_track")], policy)
    assert [a.rule for a in th] == ["threshold"]


def test_digest_only_for_off_track_and_delivered_to_outbox(approved, tmp_path):
    ctx, _ = approved
    assert kpi.build_digest(ctx.repo, CID, channel="outbox") is None
    d = ctx.repo.list_kpi_definitions(CID)[0]
    ctx.repo.add_kpi_observation(KpiObservation(
        observation_id="x1", kpi_id=d.kpi_id, company_id=CID, observed_at=datetime.now(UTC), period_end=None,
        value=d.baseline, target=d.run_rate_target, status="off_track", variance=Decimal("-0.1")))
    n = kpi.build_digest(ctx.repo, CID, channel="outbox", base_url="https://pvc.example")
    assert n and "1 KPI(s) off track" in n.subject and "https://pvc.example/companies/beacon-pricing/kpis" in n.body
    OutboxNotifier(tmp_path / "out").deliver(ctx.repo, n)
    assert json.loads(next((tmp_path / "out").glob("*.json")).read_text())["subject"] == n.subject
