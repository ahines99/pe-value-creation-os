"""Real review mechanics exercised only with fictional people, sources and decisions."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_baselines as baselines
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_capacity import capacity_clock as capacity_clock
from tests.test_private_capacity import plan as proposal
from tests.test_private_capacity import save as save_plan
from tests.test_private_capacity import setup as setup_capacity
from tests.test_private_financials import financial_clock as financial_clock
from tests.test_private_records import COMPANY, ENV, FINANCE, NOW, OPERATOR, actor, ingest, revoke
from tests.test_private_records import fixed_clock as fixed_clock
from tests.test_private_records import review as review_source
from tests.test_private_underwriting import save as save_underwriting
from tests.test_private_underwriting import underwriting_clock as underwriting_clock

OPERATING = actor(roles=("operator", "operating_reviewer", "approver"))


@pytest.fixture(autouse=True)
def baseline_clock(monkeypatch):
    monkeypatch.setattr(baselines, "datetime", SimpleNamespace(now=lambda zone: NOW))


def setup(repo, *, blocked=False):
    grant, record, accepted, financials, underwriting = setup_capacity(repo)
    plan = proposal(underwriting)
    if blocked:
        raw = plan.model_dump(mode="json")
        raw["resources"][0]["weekly_hours"] = [None] * 15
        from pe_value_os.diligence.private_capacity import PrivateOperatingPlan

        plan = PrivateOperatingPlan.model_validate(raw)
    return grant, record, accepted, financials, underwriting, save_plan(repo, underwriting, supplied=plan)


def review_request(plan, kind, *, decision="accept", key="initial", previous=None):
    assessment = None
    if decision == "accept":
        assessment = (
            baselines.FinanceAssessment(
                accounting_and_controls="Fictional reconciled definition",
                assumptions_and_eligibility="Fictional population review",
                cash_and_cost_timing="Fictional dated cost and cash review",
                valuation_limitations="Sensitivity only; not maintainable value",
            )
            if kind == "finance"
            else baselines.OperatingAssessment(
                owners_and_capacity="Fictional owner and available-hour confirmation",
                dependencies_and_constraints="Fictional contract and dependency checks",
                measurement_and_stop_conditions="Fictional baseline, measurement and stop-rule review",
                capacity_confirmed_for_planning=True,
            )
        )
    return baselines.PlanReviewRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        expected_capacity_sha256=plan.content_sha256,
        review_kind=kind,
        decision=decision,
        rationale="Fictional review; no real company participation",
        evidence_reference="fixture:review-packet",
        evidence_sha256="5" * 64,
        assessment=assessment,
    )


def review(repo, plan, kind, *, person=None, **kwargs):
    person = person or (FINANCE if kind == "finance" else OPERATING)
    with security.principal_scope(person):
        return repo.review_private_capacity(COMPANY, plan.revision_id, review_request(plan, kind, **kwargs), ENV)


def baseline_request(plan, finance, operating, *, key="initial", previous=None, scenario="base"):
    return baselines.BaselineRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        capacity_revision_id=plan.revision_id,
        expected_capacity_sha256=plan.content_sha256,
        finance_review_id=finance.review_id,
        finance_review_sha256=finance.content_sha256,
        operating_review_id=operating.review_id,
        operating_review_sha256=operating.content_sha256,
        scenario_id=scenario,
        rationale="Fictional comparison baseline only; no operating authorization",
    )


def freeze(repo, plan, finance, operating, **kwargs):
    with security.principal_scope(OPERATING):
        return repo.freeze_private_baseline(
            COMPANY, "pilot-case", baseline_request(plan, finance, operating, **kwargs), ENV
        )


def reviewed(repo):
    *source, plan = setup(repo)
    finance, operating = review(repo, plan, "finance"), review(repo, plan, "operating")
    return *source, plan, finance, operating


def status(repo, baseline):
    with security.principal_scope(OPERATOR):
        return repo.private_baseline_status(COMPANY, baseline.baseline_id, ENV)


def test_exact_human_reviews_freeze_scheduled_scenario_without_execution_authority(repo):
    *_, plan, finance, operating = reviewed(repo)
    result = freeze(repo, plan, finance, operating)
    assert finance.actor != operating.actor and finance.actor_type == operating.actor_type == "human"
    assert result.frozen_forecast == plan.schedule_result["scheduled_financials"]["scenarios"][1]
    assert Decimal(result.frozen_forecast["year_one"]["incremental_ebitda"]) == Decimal("402.70")
    assert result.origin == "synthetic_test_fixture" and result.purpose == "comparison_only"
    assert result.currency == "USD" and result.unit_scale == 1
    assert result.financial_snapshot_sha256 == plan.schedule_result["financial_snapshot_sha256"]
    assert not result.operating_action_authorized and not result.causal_value_claim
    assert not plan.finance_reviewed and not plan.operating_reviewed  # Original proposal is immutable.
    view = status(repo, result)
    assert view["usable_for_comparison"] and view["processing_currently_permitted"]
    assert view["source_currently_accepted"] and view["supporting_reviews_currently_accepted"]
    for record in (result, finance, operating):
        with pytest.raises(ValueError, match="public exhibits"):
            record.require_public()
    with security.principal_scope(OPERATOR):
        assert len(repo.list_audit(company_id=COMPANY)) == 9


def test_baseline_requires_both_current_reviews_exact_hashes_and_two_people(repo):
    *_, plan = setup(repo)
    finance = review(repo, plan, "finance")
    with pytest.raises(ValueError, match="accepted finance and operating"):
        freeze(repo, plan, finance, finance)
    same_actor = actor("finance", roles=("operator", "finance_reviewer", "operating_reviewer"))
    operating = review(repo, plan, "operating", person=same_actor)
    with pytest.raises(ValueError, match="distinct human"):
        freeze(repo, plan, finance, operating)
    actual_operating = review(repo, plan, "operating", previous=operating, key="second-person")
    for field in ("expected_capacity_sha256", "finance_review_sha256", "operating_review_sha256"):
        request = baseline_request(plan, finance, actual_operating).model_copy(update={field: "0" * 64})
        with security.principal_scope(OPERATING), pytest.raises(ValueError):
            repo.freeze_private_baseline(COMPANY, "pilot-case", request, ENV)
    freeze(repo, plan, finance, actual_operating)


def test_review_assessment_kind_and_exact_capacity_binding_are_required(repo):
    *_, plan = setup(repo)
    for patch in (
        {"assessment": None},
        {"assessment": review_request(plan, "operating").assessment},
        {"decision": "reject"},
        {"expected_capacity_sha256": "0" * 64},
    ):
        request = review_request(plan, "finance").model_copy(update=patch)
        with security.principal_scope(FINANCE), pytest.raises(ValueError):
            repo.review_private_capacity(COMPANY, plan.revision_id, request, ENV)
    with pytest.raises(ValueError, match="currently accepted review"):
        review(repo, plan, "finance", decision="withdraw")


@pytest.mark.parametrize("decision", ["reject", "request_changes"])
def test_nonaccepting_decisions_cannot_support_baseline(repo, decision):
    *_, plan = setup(repo)
    finance = review(repo, plan, "finance", decision=decision)
    operating = review(repo, plan, "operating")
    with pytest.raises(ValueError, match="accepted finance and operating"):
        freeze(repo, plan, finance, operating)


def test_blocked_plan_can_receive_financial_challenge_but_not_operating_acceptance(repo):
    *_, plan = setup(repo, blocked=True)
    finance = review(repo, plan, "finance")
    assert finance.request.decision == "accept"
    with pytest.raises(ValueError, match="blocked capacity"):
        review(repo, plan, "operating")
    assert review(repo, plan, "operating", decision="request_changes").request.decision == "request_changes"


def test_new_forecast_and_plan_do_not_move_original_frozen_baseline(repo):
    _grant, _record, _accepted, financials, underwriting, plan, finance, operating = reviewed(repo)
    original = freeze(repo, plan, finance, operating)
    original_payload = json.dumps(original.model_dump(mode="json"), sort_keys=True)
    revised = save_underwriting(repo, financials, key="revised", previous=underwriting)
    new_plan = save_plan(repo, revised, key="revised", previous=plan)
    # The old plan is no longer a current proposal; its reviewed baseline remains
    # the comparison anchor while the original source and reviews remain supported.
    view = status(repo, original)
    assert view["usable_for_comparison"] and view["frozen_forecast"] == original.frozen_forecast
    with pytest.raises(ValueError, match="accepted finance and operating"):
        freeze(repo, new_plan, finance, operating, key="replace", previous=original)
    new_finance, new_operating = review(repo, new_plan, "finance"), review(repo, new_plan, "operating")
    replacement = freeze(
        repo, new_plan, new_finance, new_operating, key="replace", previous=original, scenario="downside"
    )
    assert status(repo, replacement)["usable_for_comparison"]
    assert not status(repo, original)["current_designation"] and not status(repo, original)["usable_for_comparison"]
    with security.principal_scope(OPERATOR):
        assert (
            json.dumps(repo.list_private_baselines(COMPANY, "pilot-case")[0].model_dump(mode="json"), sort_keys=True)
            == original_payload
        )


def test_review_withdrawal_and_reacceptance_never_reactivate_old_baseline(repo):
    *_, plan, finance, operating = reviewed(repo)
    original = freeze(repo, plan, finance, operating)
    withdrawn = review(repo, plan, "finance", decision="withdraw", key="withdraw", previous=finance)
    assert not status(repo, original)["supporting_reviews_currently_accepted"]
    reaccepted = review(repo, plan, "finance", key="reaccept", previous=withdrawn)
    assert not status(repo, original)["usable_for_comparison"]
    replacement = freeze(repo, plan, reaccepted, operating, key="renew", previous=original)
    assert status(repo, replacement)["usable_for_comparison"]
    assert original.frozen_forecast == replacement.frozen_forecast


def test_source_correction_invalidates_support_without_rewriting_frozen_numbers(repo):
    grant, record, _accepted, _financials, _underwriting, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    ingest(repo, grant, key="correction", previous=record)
    view = status(repo, baseline)
    assert view["processing_currently_permitted"] and not view["source_currently_accepted"]
    assert not view["usable_for_comparison"] and view["frozen_forecast"] == baseline.frozen_forecast
    assert (
        review(repo, plan, "finance", decision="withdraw", key="withdraw", previous=finance).request.decision
        == "withdraw"
    )


def test_source_finance_reacceptance_does_not_reactivate_original_baseline(repo):
    grant, record, accepted, _financials, _underwriting, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    withdrawn = review_source(repo, record, grant, decision="withdraw", key="withdraw", previous=accepted)
    view = status(repo, baseline)
    assert view["supporting_reviews_currently_accepted"] and not view["source_currently_accepted"]
    review_source(repo, record, grant, key="reaccept", previous=withdrawn)
    assert not status(repo, baseline)["usable_for_comparison"]


@pytest.mark.parametrize("first_operation", ["freeze", "withdraw"])
def test_withdrawal_and_freeze_are_serialized_and_cannot_leave_usable_stale_approval(
    repo, monkeypatch, first_operation
):
    import importlib
    from threading import Event

    *_, plan, finance, operating = reviewed(repo)
    # Both backends run the shared record rules defined beside InMemoryRepository.
    module = importlib.import_module("pe_value_os.adapters.repositories")
    target = "prepare_private_baseline" if first_operation == "freeze" else "prepare_private_plan_review"
    prepare_original = getattr(module, target)
    entered, attempted, release = Event(), Event(), Event()

    def gate(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return prepare_original(*args, **kwargs)

    monkeypatch.setattr(module, target, gate)

    def perform(operation, *, second=False):
        if second:
            attempted.set()
        if operation == "withdraw":
            return review(repo, plan, "finance", decision="withdraw", key="withdraw", previous=finance)
        try:
            return freeze(repo, plan, finance, operating)
        except ValueError as exc:
            assert "accepted finance and operating" in str(exc)
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(perform, first_operation)
        try:
            assert entered.wait(10)
            second = pool.submit(perform, "withdraw" if first_operation == "freeze" else "freeze", second=True)
            assert attempted.wait(10)
        finally:
            release.set()
        first_result, second_result = first.result(), second.result()
    if first_operation == "freeze":
        assert not status(repo, first_result)["usable_for_comparison"]
    else:
        assert second_result is None
        with security.principal_scope(OPERATOR):
            assert repo.list_private_baselines(COMPANY, "pilot-case") == []


def test_revocation_blocks_reproduction_but_not_historical_receipt_or_withdrawal(repo, monkeypatch):
    grant, _record, _accepted, _financials, _underwriting, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    revoke(repo, grant)
    with pytest.raises(security.ScopeError):
        status(repo, baseline)
    assert freeze(repo, plan, finance, operating) == baseline  # Idempotent historical receipt only.
    with security.principal_scope(OPERATOR):
        assert repo.list_private_baselines(COMPANY, "pilot-case") == [baseline]

    def forbidden(*args, **kwargs):
        raise AssertionError("Withdrawal must not process a private source or calculate its forecast")

    monkeypatch.setattr(repo, "private_intake_source", forbidden)
    monkeypatch.setattr(repo, "usable_private_capacity_plan", forbidden)
    withdrawn = review(repo, plan, "finance", decision="withdraw", key="withdraw", previous=finance)
    assert withdrawn.request.decision == "withdraw"


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        actor("finance", roles=("operator", "operating_reviewer")),
        actor("finance", roles=("operator", "finance_reviewer"), kind="model"),
        actor("finance", roles=("operator", "finance_reviewer"), scopes=("pvc.read", "pvc.write")),
        actor("finance", roles=("operator", "finance_reviewer"), client="mcp-client"),
        actor("unnamed", roles=("operator", "finance_reviewer")),
        actor("finance", roles=("operator", "finance_reviewer"), company="foreign"),
    ],
)
def test_plan_acceptance_requires_matching_role_client_scope_and_named_processing_person(repo, person):
    *_, plan = setup(repo)
    with pytest.raises(security.ScopeError):
        review(repo, plan, "finance", person=person)


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        FINANCE,
        actor(roles=("operator", "approver"), kind="model"),
        actor(roles=("operator", "approver"), client="mcp-client"),
        actor("unnamed", roles=("operator", "approver")),
        actor(roles=("operator", "approver"), scopes=("pvc.read",)),
    ],
)
def test_baseline_requires_human_approver_and_current_processing_permission(repo, person):
    *_, plan, finance, operating = reviewed(repo)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.freeze_private_baseline(COMPANY, "pilot-case", baseline_request(plan, finance, operating), ENV)


def test_foreign_plan_review_cannot_support_baseline_and_old_plan_cannot_receive_new_acceptance(repo):
    *_, underwriting, plan, finance, operating = reviewed(repo)
    newer = save_plan(repo, underwriting, key="revised", previous=plan)
    with pytest.raises(ValueError, match="superseded"):
        review(repo, plan, "finance", key="again", previous=finance)
    with pytest.raises(ValueError, match="accepted finance and operating"):
        freeze(repo, newer, finance, operating)
    assert (
        review(repo, plan, "finance", decision="withdraw", previous=finance, key="withdraw").request.decision
        == "withdraw"
    )


def test_review_concurrency_idempotency_and_audit_rollback(repo, monkeypatch):
    *_, plan = setup(repo)
    append = repo.append_audit

    def fail(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        review(repo, plan, "finance")
    with security.principal_scope(OPERATOR):
        assert repo.list_private_plan_reviews(COMPANY, plan.revision_id) == []
    monkeypatch.setattr(repo, "append_audit", append)
    first = review(repo, plan, "finance")
    assert review(repo, plan, "finance") == first
    with pytest.raises(Conflict, match="idempotency"):
        review(repo, plan, "finance", decision="reject")
    alternate = actor(roles=("operator", "finance_reviewer"))
    with pytest.raises(Conflict, match="idempotency"):
        review(repo, plan, "finance", person=alternate)

    def append_review(key):
        try:
            return review(repo, plan, "finance", previous=first, key=key)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(r is not None for r in pool.map(append_review, ("a", "b"))) == 1


def test_baseline_concurrency_idempotency_and_audit_rollback(repo, monkeypatch):
    *_, plan, finance, operating = reviewed(repo)
    append = repo.append_audit

    def fail(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        freeze(repo, plan, finance, operating)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_baselines(COMPANY, "pilot-case") == []
    monkeypatch.setattr(repo, "append_audit", append)
    first = freeze(repo, plan, finance, operating)
    assert freeze(repo, plan, finance, operating) == first
    with pytest.raises(Conflict, match="idempotency"):
        freeze(repo, plan, finance, operating, scenario="downside")
    alternate = actor("finance", roles=("operator", "approver"))
    with security.principal_scope(alternate), pytest.raises(Conflict, match="idempotency"):
        repo.freeze_private_baseline(COMPANY, "pilot-case", baseline_request(plan, finance, operating), ENV)

    def append_baseline(key):
        try:
            return freeze(repo, plan, finance, operating, previous=first, key=key)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(r is not None for r in pool.map(append_baseline, ("a", "b"))) == 1


def test_rehashing_frozen_numbers_cannot_change_saved_forecast(repo):
    *_, plan, finance, operating = reviewed(repo)
    original = freeze(repo, plan, finance, operating)
    raw = original.model_dump(mode="json")
    raw["frozen_forecast"]["year_one"]["incremental_ebitda"] = "999999"
    forged = original.model_copy(update={"frozen_forecast": raw["frozen_forecast"]})
    forged = forged.model_copy(update={"content_sha256": content_hash(forged)})
    with security.principal_scope(OPERATOR):
        reviews = repo.list_private_plan_reviews(COMPANY, plan.revision_id)
    with pytest.raises(ValueError, match="frozen forecast differs"):
        baselines.baseline_view(forged, plan, reviews, [original], source_current=True)
    wrong_currency = original.model_copy(update={"currency": "EUR"})
    wrong_currency = wrong_currency.model_copy(update={"content_sha256": content_hash(wrong_currency)})
    with pytest.raises(ValueError, match="financial scope"):
        baselines.baseline_view(wrong_currency, plan, reviews, [original], source_current=True)


def test_scope_environment_identifiers_and_offboarding(repo):
    *_, plan, finance, operating = reviewed(repo)
    with security.principal_scope(OPERATING), pytest.raises(security.ScopeError):
        repo.freeze_private_baseline(COMPANY, "pilot-case", baseline_request(plan, finance, operating), "wrong")
    baseline = freeze(repo, plan, finance, operating)
    with security.principal_scope(OPERATOR):
        with pytest.raises(NotFound):
            repo.private_baseline_status(COMPANY, "invalid", ENV)
        with pytest.raises(security.ScopeError):
            repo.private_baseline_status(COMPANY, baseline.baseline_id, "wrong")
    with security.principal_scope(actor(company="foreign")), pytest.raises(security.ScopeError):
        repo.list_private_baselines(COMPANY, "pilot-case")
    with security.principal_scope(actor(kind="model")), pytest.raises(security.ScopeError):
        repo.list_private_plan_reviews(COMPANY, plan.revision_id)
    with security.principal_scope(OPERATOR):
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_plan_reviews"] == 2 and counts["private_baselines"] == 1
        with pytest.raises(NotFound):
            repo.private_baseline_status(COMPANY, baseline.baseline_id, ENV)


def test_api_reviews_freeze_current_support_and_withdrawal_after_revocation(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    grant, _record, _accepted, _financials, _underwriting, plan = setup(repo)
    people = {"operator": OPERATOR, "finance": FINANCE, "operating": OPERATING, "model": actor(kind="model")}
    tokens = {
        name: dict(
            sub=p.subject,
            pvc_companies=list(p.companies),
            pvc_roles=list(p.roles),
            pvc_principal_type=p.principal_type,
            scope=" ".join(p.scopes),
            client_id=p.client_id,
        )
        for name, p in people.items()
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
    api.reset_auth()
    api.set_ctx(SimpleNamespace(repo=repo))
    review_path = f"/companies/{COMPANY}/private-capacity/revisions/{plan.revision_id}/reviews"
    baseline_path = f"/companies/{COMPANY}/private-baselines"
    case_path = baseline_path + "/cases/pilot-case"

    def headers(name):
        return {"Authorization": "Bearer " + name}

    try:
        with TestClient(api.app) as client:
            payload = review_request(plan, "finance").model_dump(mode="json")
            assert client.post(review_path + "/finance", json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "finance")
            assert client.post(review_path + "/finance", json=payload).status_code == 403
            client.cookies.clear()
            for name in ("operator", "model"):
                assert (
                    client.post(review_path + "/finance", content=b"private-invalid", headers=headers(name)).status_code
                    == 404
                )
                assert client.post(case_path, content=b"private-invalid", headers=headers(name)).status_code == 404
            bad = client.post(
                review_path + "/finance", json={"secret": "sensitive-fixture-value"}, headers=headers("finance")
            )
            assert bad.status_code == 422 and "sensitive-fixture-value" not in bad.text
            assert (
                client.post(
                    review_path + "/finance", content=b" " * (1024 * 1024 + 1), headers=headers("finance")
                ).status_code
                == 413
            )
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            assert client.post(review_path + "/finance", json=payload, headers=headers("finance")).status_code == 503
            monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
            created = client.post(review_path + "/finance", json=payload, headers=headers("finance"))
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            finance = baselines.PrivatePlanReview.model_validate(created.json())
            operating_response = client.post(
                review_path + "/operating",
                json=review_request(plan, "operating").model_dump(mode="json"),
                headers=headers("operating"),
            )
            assert operating_response.status_code == 201
            operating = baselines.PrivatePlanReview.model_validate(operating_response.json())
            frozen = client.post(
                case_path,
                json=baseline_request(plan, finance, operating).model_dump(mode="json"),
                headers=headers("operating"),
            )
            assert frozen.status_code == 201 and frozen.headers["cache-control"] == "no-store"
            baseline = baselines.PrivateBaseline.model_validate(frozen.json())
            status_path = baseline_path + f"/designations/{baseline.baseline_id}/status"
            assert client.get(status_path, headers=headers("operator")).json()["usable_for_comparison"]
            assert client.get(case_path, headers=headers("operator")).json()["historical_records_only"]
            revoke(repo, grant)
            assert client.get(status_path, headers=headers("operator")).status_code == 404
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            withdrawal = review_request(
                plan, "finance", decision="withdraw", key="withdraw", previous=finance
            ).model_dump(mode="json")
            assert client.post(review_path + "/finance", json=withdrawal, headers=headers("finance")).status_code == 201
            assert len(client.get(review_path, headers=headers("operator")).json()["reviews"]) == 3
            assert client.get(case_path, headers=headers("operator")).status_code == 200
    finally:
        api.set_ctx(None)
        api.reset_auth()


@pytest.mark.parametrize("with_baseline", [False, True])
def test_review_and_baseline_database_rls_immutability_and_populated_downgrade_guard(
    pg_repo, pg_database, with_baseline
):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade, upgrade

    *_, plan, finance, operating = reviewed(pg_repo)
    if with_baseline:
        freeze(pg_repo, plan, finance, operating)
    tables = ("private_plan_reviews", "private_baselines")
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        for table in tables:
            assert conn.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table))).fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_plan_reviews").fetchone()[0] == 2
        assert conn.execute("select count(*) from private_baselines").fetchone()[0] == int(with_baseline)
        for table in tables:
            for statement in ("delete from {}", "update {} set sequence=99"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql.SQL(statement).format(sql.Identifier(table)))
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = current(pg_database[0])
    downgrade(pg_database[0], "0013")
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owners = {
            table: conn.execute(
                "select pg_get_userbyid(relowner) from pg_class where oid=%s::regclass", (table,)
            ).fetchone()[0]
            for table in tables
        }
        try:
            for table in tables:
                conn.execute(sql.SQL("alter table {} owner to pvc_migrator").format(sql.Identifier(table)))
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                for table in tables:
                    assert (
                        hidden.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table))).fetchone()[0]
                        == 0
                    )
            with pytest.raises(RuntimeError, match="Private reviewed baseline history"):
                downgrade(owner_url, "0012")
            assert current(pg_database[0]) == "0013"
            for table in tables:
                assert conn.execute(
                    "select relforcerowsecurity from pg_class where oid=%s::regclass", (table,)
                ).fetchone()[0]
        finally:
            for table, owner in owners.items():
                conn.execute(sql.SQL("alter table {} owner to {}").format(sql.Identifier(table), sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert current(pg_database[0]) == head
