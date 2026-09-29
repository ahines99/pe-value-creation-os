"""Private schedules preserve source authority, costs and explicit capacity limits."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_capacity as capacity
from pe_value_os.diligence.private_records import content_hash
from pe_value_os.diligence.scheduling import OperatingPlan
from tests.test_private_financials import financial_clock as financial_clock
from tests.test_private_financials import snapshot
from tests.test_private_records import COMPANY, ENV, FINANCE, NOW, OPERATOR, actor, ingest, review, revoke
from tests.test_private_records import fixed_clock as fixed_clock
from tests.test_private_underwriting import inputs, prepare
from tests.test_private_underwriting import save as save_underwriting
from tests.test_private_underwriting import underwriting_clock as underwriting_clock


@pytest.fixture(autouse=True)
def capacity_clock(monkeypatch):
    monkeypatch.setattr(capacity, "datetime", SimpleNamespace(now=lambda zone: NOW))


def plan(underwriting):
    return capacity.PrivateOperatingPlan.model_validate(
        dict(
            plan_id="pilot-plan",
            revision_id="draft-1",
            case_id="pilot-case",
            underwriting_sha256=underwriting.content_sha256,
            start=underwriting.request.inputs.start,
            maximum_active_workstreams=1,
            sequencing_rationale="Fictional dependency and capacity rehearsal",
            resources=[
                dict(
                    resource_id="operator",
                    proposed_operator="Fictional proposed operator",
                    weekly_hours=["10"] * 15,
                    basis="Net of ordinary duties",
                    capacity_evidence_reference="fixture:capacity-worksheet",
                    capacity_evidence_sha256="4" * 64,
                    capacity_attestation="Fictional capacity assumption; no commitment",
                )
            ],
            tasks=[
                dict(
                    task_id=key,
                    title=key,
                    workstream_id=key,
                    initiative_id=initiative,
                    accountable_resource="operator",
                    earliest_start=underwriting.request.inputs.start,
                    duration_weeks=1,
                    prerequisites=[] if key == "foundation" else ["foundation"],
                    demands=[dict(resource_id="operator", hours_per_week="10")],
                    deliverable="Reconciled eligible population",
                    acceptance_evidence="Exact-version finance and contract review",
                    acceptance_reviewer="Proposed reviewer",
                )
                for key, initiative in [("foundation", None), ("price-gate", "price")]
            ],
            priority_order=["foundation", "price-gate"],
            benefit_gates=[dict(initiative_id="price", task_id="price-gate")],
        )
    )


def request(underwriting, *, key="initial", previous=None, supplied=None):
    return capacity.CapacityPlanRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        underwriting_revision_id=underwriting.revision_id,
        plan=supplied or plan(underwriting),
        rationale="Fictional planning proposal, not permission to operate",
    )


def setup(repo):
    grant, record, accepted, financials = prepare(repo)
    return grant, record, accepted, financials, save_underwriting(repo, financials)


def save(repo, underwriting, **kwargs):
    with security.principal_scope(OPERATOR):
        return repo.record_private_capacity_plan(COMPANY, "pilot-case", request(underwriting, **kwargs), ENV)


def test_worked_capacity_dates_monthly_earnings_cash_and_immutable_underwriting(repo):
    *_, underwriting = setup(repo)
    before = underwriting.model_dump(mode="json")
    with localcontext() as ctx:
        ctx.prec = 2
        result = save(repo, underwriting)
    report = result.schedule_result
    assert [t["scheduled_start"] for t in report["tasks"]] == ["2026-10-01", "2026-10-08"]
    assert report["tasks"][1]["benefit_ready_on"] == "2026-10-15"
    assert sum(Decimal(w["used_hours"]) for w in report["capacity"][0]["weeks"]) == 20
    base = report["scheduled_financials"]["scenarios"][1]
    # Oct: 49 * 17/31 rounds to 26.87, variable cost rounds to -5.37, setup is -50.
    assert Decimal(base["monthly"][0]["incremental_ebitda"]) == Decimal("-28.50")
    assert Decimal(base["year_one"]["incremental_ebitda"]) == Decimal("402.70")
    assert Decimal(base["year_one"]["pre_tax_cash_proxy"]) == Decimal("363.50")
    assert report["original_financials"] == underwriting.forecast
    assert underwriting.model_dump(mode="json") == before
    assert report["original_financials"]["scenarios"][1]["costs"] == base["costs"]
    assert "Private proposed plan" in report["authority"]
    assert result.origin == "synthetic_test_fixture"
    assert not any(
        (
            result.capacity_committed,
            result.finance_reviewed,
            result.operating_reviewed,
            result.frozen_comparison_baseline,
            result.operating_action_authorized,
        )
    )
    with security.principal_scope(OPERATOR):
        assert repo.usable_private_capacity_plan(COMPANY, result.revision_id, ENV) == result
        assert len(repo.list_audit(company_id=COMPANY)) == 6
    with pytest.raises(ValueError, match="public exhibits"):
        result.require_public()
    with pytest.raises(ValueError):
        OperatingPlan.model_validate(result.request.plan.model_dump(mode="json"))


@pytest.mark.parametrize("hours,reason", [(None, "unknown_capacity"), ("0", "resource_capacity")])
def test_unknown_or_zero_capacity_blocks_benefits_but_preserves_committed_costs(repo, hours, reason):
    *_, underwriting = setup(repo)
    raw = plan(underwriting).model_dump(mode="json")
    raw["resources"][0]["weekly_hours"] = [hours] * 15
    result = save(repo, underwriting, supplied=capacity.PrivateOperatingPlan.model_validate(raw))
    report = result.schedule_result
    assert all(t["status"] == "blocked" for t in report["tasks"])
    assert report["tasks"][0]["candidate_rejections"][0]["conflicts"][0]["kind"] == reason
    assert report["tasks"][1]["blocked_by"] == ["foundation"]
    base = report["scheduled_financials"]["scenarios"][1]
    assert base["suppressed_benefits"] == ["price"]
    assert Decimal(base["total"]["incremental_ebitda"]) == Decimal("-50")
    assert Decimal(base["total"]["pre_tax_cash_proxy"]) == Decimal("-50")
    assert Decimal(base["valuation"][0]["incremental_ev_sensitivity"]) == 0


def test_unknown_early_capacity_delays_and_day_99_release_cannot_fit_a_week(repo):
    *_, underwriting = setup(repo)
    raw = plan(underwriting).model_dump(mode="json")
    raw["resources"][0]["weekly_hours"][0] = None
    first = save(repo, underwriting, supplied=capacity.PrivateOperatingPlan.model_validate(raw))
    assert first.schedule_result["tasks"][1]["benefit_ready_on"] == "2026-10-22"
    raw["tasks"][1]["earliest_start"] = "2027-01-07"
    second = save(
        repo, underwriting, key="late", previous=first, supplied=capacity.PrivateOperatingPlan.model_validate(raw)
    )
    assert second.schedule_result["tasks"][1]["status"] == "blocked"
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)


def test_benefits_cannot_start_before_authored_economic_date(repo):
    *_, financials, first_underwriting = setup(repo)
    raw = inputs(financials).model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["drivers"][0]["effective_on"] = "2026-11-01"
    from pe_value_os.diligence.private_underwriting import PrivateUnderwritingInputs

    underwriting = save_underwriting(
        repo,
        financials,
        key="later",
        previous=first_underwriting,
        supplied=PrivateUnderwritingInputs.model_validate(raw),
    )
    result = save(repo, underwriting)
    assert {t["scheduled_effective_on"] for t in result.schedule_result["timing"]} == {"2026-11-01"}


def with_collections(repo):
    from pe_value_os.diligence.private_underwriting import PrivateUnderwritingInputs

    *_, financials, prior = setup(repo)
    raw = inputs(financials).model_dump(mode="json")
    for scenario in raw["scenarios"]:
        scenario["assumptions"].append(
            dict(
                assumption_id="receivables",
                value="1000",
                unit="currency",
                rationale="Fictional collectible pool",
                owner="operator",
                invalidated_by="Credit dispute",
                evidence_ids=["eligibility"],
            )
        )
        raw["assumption_bases"].append(
            dict(
                scenario_id=scenario["scenario_id"],
                assumption_id="receivables",
                kind="operator_judgment",
                rationale="Fictional collection hypothesis",
            )
        )
        scenario["drivers"].append(
            dict(
                kind="collections",
                initiative_id="collections",
                title="Fictional collections",
                benefit_pool="receivables",
                effective_on="2026-10-01",
                receivables_balance="receivables",
                accelerated_fraction="capture",
                counterfactual_collection_on="2026-10-20",
            )
        )
    raw["selected_initiatives"].append("collections")
    raw["initiative_bases"].append({**raw["initiative_bases"][0], "initiative_id": "collections"})
    underwriting = save_underwriting(
        repo, financials, key="collections", previous=prior, supplied=PrivateUnderwritingInputs.model_validate(raw)
    )
    proposal = plan(underwriting).model_dump(mode="json")
    proposal["tasks"].append(
        {
            **proposal["tasks"][1],
            "task_id": "collections-gate",
            "initiative_id": "collections",
            "workstream_id": "collections-gate",
        }
    )
    proposal["priority_order"].append("collections-gate")
    proposal["benefit_gates"].append(dict(initiative_id="collections", task_id="collections-gate"))
    return financials, underwriting, proposal


def test_competing_streams_and_authored_order_change_financials_and_collection_window(repo):
    _financials, underwriting, proposal = with_collections(repo)
    proposal["resources"][0]["weekly_hours"] = ["20"] * 15
    first = save(repo, underwriting, supplied=capacity.PrivateOperatingPlan.model_validate(proposal))
    report = first.schedule_result
    assert report["tasks"][2]["candidate_rejections"][0]["conflicts"][0]["kind"] == "workstream_limit"
    assert report["scheduled_financials"]["scenarios"][1]["suppressed_benefits"] == ["collections"]
    assert all(
        Decimal(m["working_capital_cash"]) == 0 for m in report["scheduled_financials"]["scenarios"][1]["monthly"]
    )
    assert "expired" in report["timing"][1]["reason"]
    proposal["priority_order"] = ["foundation", "collections-gate", "price-gate"]
    second = save(
        repo,
        underwriting,
        key="reordered",
        previous=first,
        supplied=capacity.PrivateOperatingPlan.model_validate(proposal),
    )
    revised = second.schedule_result
    assert revised["scheduled_financials"]["scenarios"][1]["suppressed_benefits"] == []
    assert revised["timing"][1]["scheduled_effective_on"] == "2026-10-15"
    assert revised["scheduled_inputs"]["scenarios"][1]["drivers"][1]["counterfactual_collection_on"] == "2026-10-20"
    assert Decimal(revised["scheduled_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"]) < Decimal(
        report["scheduled_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"]
    )
    proposal["maximum_active_workstreams"] = 2
    concurrent = save(
        repo,
        underwriting,
        key="concurrent",
        previous=second,
        supplied=capacity.PrivateOperatingPlan.model_validate(proposal),
    )
    assert {t["scheduled_start"] for t in concurrent.schedule_result["tasks"][1:]} == {"2026-10-08"}
    assert concurrent.schedule_result["scheduled_financials"]["scenarios"][1]["suppressed_benefits"] == []


def test_selected_work_cannot_hide_dependency_on_an_excluded_initiative(repo):
    financials, underwriting, proposal = with_collections(repo)
    excluded = save_underwriting(
        repo,
        financials,
        key="excluded",
        previous=underwriting,
        supplied=underwriting.request.inputs.model_copy(update={"selected_initiatives": ("price",)}),
    )
    proposal["underwriting_sha256"] = excluded.content_sha256
    proposal["tasks"][1]["prerequisites"] = [*proposal["tasks"][1]["prerequisites"], "collections-gate"]
    with pytest.raises(ValueError, match="unselected initiative"):
        save(repo, excluded, supplied=capacity.PrivateOperatingPlan.model_validate(proposal))


@pytest.mark.parametrize(
    "mutation",
    [
        "cycle",
        "missing-gate",
        "gate-bypass",
        "owner-without-demand",
        "duplicate-priority",
        "wrong-case",
        "wrong-start",
        "wrong-hash",
        "actual-assignment",
        "simulated-assignment",
        "missing-capacity-evidence",
        "excess-precision",
        "constructed-class",
    ],
)
def test_invalid_private_capacity_contracts(repo, mutation):
    *_, underwriting = setup(repo)
    raw = plan(underwriting).model_dump(mode="json")
    if mutation == "cycle":
        raw["tasks"][0]["prerequisites"] = ["price-gate"]
    elif mutation == "missing-gate":
        raw["benefit_gates"] = []
    elif mutation == "gate-bypass":
        raw["tasks"][0]["initiative_id"] = "price"
        raw["tasks"][0]["workstream_id"] = "price-gate"
        raw["tasks"][1]["prerequisites"] = []
    elif mutation == "owner-without-demand":
        raw["tasks"][0]["accountable_resource"] = "unknown"
    elif mutation == "duplicate-priority":
        raw["priority_order"][0] = "price-gate"
    elif mutation == "wrong-case":
        raw["case_id"] = "foreign"
    elif mutation == "wrong-start":
        raw["start"] = "2026-09-01"
    elif mutation == "wrong-hash":
        raw["underwriting_sha256"] = "0" * 64
    elif mutation in {"actual-assignment", "simulated-assignment"}:
        raw["resources"][0]["assignment"] = "actual" if mutation == "actual-assignment" else "simulated_assignment"
    elif mutation == "missing-capacity-evidence":
        raw["resources"][0].pop("capacity_evidence_sha256")
    elif mutation == "excess-precision":
        raw["resources"][0]["weekly_hours"][0] = "0.0000001"
    else:
        raw["classification"] = "constructed_operating_exercise"
    with pytest.raises(ValueError):
        save(repo, underwriting, supplied=capacity.PrivateOperatingPlan.model_validate(raw))
    with security.principal_scope(OPERATOR):
        assert repo.list_private_capacity_plans(COMPANY, "pilot-case") == []


def test_selection_excludes_capacity_without_canceling_retained_financial_commitment(repo):
    *_, financials, underwriting = setup(repo)
    excluded = save_underwriting(
        repo,
        financials,
        key="excluded",
        previous=underwriting,
        supplied=inputs(financials).model_copy(update={"selected_initiatives": ()}),
    )
    result = save(repo, excluded)
    report = result.schedule_result
    assert report["tasks"] == [] and len(report["excluded_tasks"]) == 2
    assert all(Decimal(w["used_hours"]) == 0 for w in report["capacity"][0]["weeks"])
    assert Decimal(report["scheduled_financials"]["scenarios"][1]["total"]["incremental_ebitda"]) == Decimal("-50")


def test_underwriting_revision_requires_new_plan_binding_without_rewriting_original(repo):
    *_, financials, underwriting = setup(repo)
    first = save(repo, underwriting)
    original = json.dumps(first.model_dump(mode="json"), sort_keys=True)
    newer = save_underwriting(repo, financials, key="revised", previous=underwriting)
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)
    second = save(repo, newer, key="revised", previous=first)
    with security.principal_scope(OPERATOR):
        history = repo.list_private_capacity_plans(COMPANY, "pilot-case")
        assert history == [first, second]
        assert json.dumps(history[0].model_dump(mode="json"), sort_keys=True) == original
        assert repo.usable_private_capacity_plan(COMPANY, second.revision_id, ENV) == second


def test_source_correction_requires_new_financial_forecast_and_capacity_versions(repo):
    grant, record, _accepted, financials, underwriting = setup(repo)
    first = save(repo, underwriting)
    corrected = ingest(repo, grant, key="corrected", previous=record)
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)
    accepted = review(repo, corrected, grant)
    updated = snapshot(repo, corrected, accepted, grant, key="corrected", previous=financials)
    revised = save_underwriting(repo, updated, key="corrected", previous=underwriting)
    second = save(repo, revised, key="corrected", previous=first)
    assert second.sequence == 2
    assert (
        second.schedule_result["scheduled_financials"]["scenarios"]
        == first.schedule_result["scheduled_financials"]["scenarios"]
    )


def test_finance_withdrawal_and_revocation_block_current_plan_use_not_historical_receipts(repo):
    grant, record, accepted, _financials, underwriting = setup(repo)
    first = save(repo, underwriting)
    withdrawn = review(repo, record, grant, decision="withdraw", previous=accepted, key="withdraw")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="finance acceptance"):
        repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)
    review(repo, record, grant, previous=withdrawn, key="reaccept")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="authority changed"):
        repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)
    revoke(repo, grant)
    assert save(repo, underwriting) == first
    with security.principal_scope(OPERATOR):
        assert repo.list_private_capacity_plans(COMPANY, "pilot-case") == [first]
        with pytest.raises(security.ScopeError):
            repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)
    with pytest.raises(security.ScopeError):
        save(repo, underwriting, key="after-revocation", previous=first)


@pytest.mark.parametrize(
    "person",
    [
        actor(kind="model"),
        actor(kind="service"),
        actor(subject="unnamed"),
        actor(roles=()),
        actor(scopes=("pvc.read",)),
        actor(company="foreign"),
    ],
)
def test_private_plan_creation_requires_named_human_processing_and_write_rights(repo, person):
    *_, underwriting = setup(repo)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.record_private_capacity_plan(COMPANY, "pilot-case", request(underwriting), ENV)


def test_plan_reproduction_detects_rehashed_schedule_financial_or_authority_tampering(repo):
    *_, financials, underwriting = setup(repo)
    first = save(repo, underwriting)
    for field, value in [("tasks", []), ("timing", []), ("capacity_committed", True), ("scheduled_financials", {})]:
        raw = first.model_dump(mode="json")
        raw["schedule_result"][field] = value
        forged = first.model_copy(update={"schedule_result": raw["schedule_result"]})
        forged = forged.model_copy(update={"content_sha256": content_hash(forged)})
        with pytest.raises(ValueError, match="reproduce"):
            capacity.verify_revision(forged, underwriting, financials)


def test_environment_identifiers_and_company_offboarding(repo):
    *_, underwriting = setup(repo)
    with security.principal_scope(OPERATOR), pytest.raises(security.ScopeError):
        repo.record_private_capacity_plan(COMPANY, "pilot-case", request(underwriting), "wrong")
    first = save(repo, underwriting)
    with security.principal_scope(OPERATOR):
        with pytest.raises(NotFound):
            repo.usable_private_capacity_plan(COMPANY, "invalid", ENV)
        with pytest.raises(security.ScopeError):
            repo.usable_private_capacity_plan(COMPANY, first.revision_id, "wrong")
        assert repo.delete_company_data(COMPANY)["private_capacity_plans"] == 1
        with pytest.raises(NotFound):
            repo.usable_private_capacity_plan(COMPANY, first.revision_id, ENV)


def test_plan_idempotency_concurrent_heads_and_atomic_audit(repo, monkeypatch):
    *_, underwriting = setup(repo)
    append = repo.append_audit

    def fail(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        save(repo, underwriting)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_capacity_plans(COMPANY, "pilot-case") == []
    monkeypatch.setattr(repo, "append_audit", append)
    first = save(repo, underwriting)
    assert save(repo, underwriting) == first
    with security.principal_scope(FINANCE), pytest.raises(Conflict, match="idempotency"):
        repo.record_private_capacity_plan(COMPANY, "pilot-case", request(underwriting), ENV)
    with pytest.raises(Conflict, match="idempotency"):
        save(repo, underwriting, supplied=plan(underwriting).model_copy(update={"sequencing_rationale": "changed"}))

    def append_revision(key):
        try:
            return save(repo, underwriting, key=key, previous=first)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(r is not None for r in pool.map(append_revision, ["one", "two"])) == 1


def test_private_capacity_api_keeps_history_separate_from_current_use(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    grant, _record, _accepted, _financials, underwriting = setup(repo)
    tokens = {
        name: dict(
            sub=person.subject,
            pvc_companies=list(person.companies),
            pvc_roles=list(person.roles),
            pvc_principal_type=person.principal_type,
            scope=" ".join(person.scopes),
            client_id=person.client_id,
        )
        for name, person in {"operator": OPERATOR, "model": actor(kind="model")}.items()
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
    api.reset_auth()
    api.set_ctx(SimpleNamespace(repo=repo))
    path = f"/companies/{COMPANY}/private-capacity"
    case_path = path + "/cases/pilot-case"
    headers = {"Authorization": "Bearer operator"}
    payload = request(underwriting).model_dump(mode="json")
    try:
        with TestClient(api.app) as client:
            assert client.post(case_path, json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "operator")
            assert client.post(case_path, json=payload).status_code == 403
            client.cookies.clear()
            assert (
                client.post(
                    case_path, content=b"private-invalid", headers={"Authorization": "Bearer model"}
                ).status_code
                == 404
            )
            bad = client.post(case_path, json={"secret": "sensitive-fixture-value"}, headers=headers)
            assert bad.status_code == 422 and "sensitive-fixture-value" not in bad.text
            assert client.post(case_path, content=b" " * (1024 * 1024 + 1), headers=headers).status_code == 413
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            assert client.post(case_path, json=payload, headers=headers).status_code == 503
            monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
            created = client.post(case_path, json=payload, headers=headers)
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            revision = capacity.PrivateCapacityRevision.model_validate(created.json())
            usable = path + f"/revisions/{revision.revision_id}/usable"
            assert client.get(usable, headers=headers).json()["source_currently_accepted"]
            assert client.get(case_path, headers=headers).json()["historical_records_only"]
            revoke(repo, grant)
            assert client.get(usable, headers=headers).status_code == 404
            assert client.get(case_path, headers=headers).status_code == 200
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_capacity_database_rls_immutability_and_populated_downgrade_guard(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade, upgrade

    *_, underwriting = setup(pg_repo)
    save(pg_repo, underwriting)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from private_capacity_plans").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_capacity_plans").fetchone()[0] == 1
        for statement in (
            "delete from private_capacity_plans",
            "update private_capacity_plans set sequence=99",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = current(pg_database[0])
    downgrade(pg_database[0], "0012")
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='private_capacity_plans'::regclass"
        ).fetchone()[0]
        try:
            conn.execute("alter table private_capacity_plans owner to pvc_migrator")
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_capacity_plans").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private capacity history"):
                downgrade(owner_url, "0011")
            assert current(pg_database[0]) == "0012"
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='private_capacity_plans'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table private_capacity_plans owner to {}").format(sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert current(pg_database[0]) == head
