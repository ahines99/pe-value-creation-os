"""Fictional intervention receipts test authority boundaries, never company execution."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_execution as execution
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_baselines import OPERATING, freeze, reviewed
from tests.test_private_baselines import review as review_plan
from tests.test_private_observations import clock as measurement_clock  # noqa: F401
from tests.test_private_records import COMPANY, ENV, FINANCE, NOW, OPERATOR, actor, revoke


def at(day, hour=12):
    return datetime(2026, 10, day, hour, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch, request):
    measured = request.getfixturevalue("measurement_clock")

    class Clock(datetime):
        @classmethod
        def now(cls, zone):
            return measured.value

    monkeypatch.setattr(execution, "datetime", Clock)
    return measured


def evidence():
    return execution.EvidenceBinding(
        reference="fixture:execution-evidence",
        sha256="5" * 64,
        attestation="Fictional review/commitment only; no actual authority represented",
    )


def setup(repo):
    grant, source, accepted, anchor, underwriting, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    return SimpleNamespace(
        grant=grant,
        source=source,
        accepted=accepted,
        anchor=anchor,
        underwriting=underwriting,
        plan=plan,
        finance=finance,
        operating=operating,
        baseline=baseline,
    )


def binding(event):
    return execution.EventBinding(event_id=event.event_id, sha256=event.content_sha256)


def terms(*, start=None, expiry=None, cost="50", tasks=("foundation", "price-gate")):
    return execution.AuthorizationTerms(
        valid_from=start or at(1, 0),
        expires_at=expiry or datetime(2026, 11, 1, tzinfo=UTC),
        task_ids=tasks,
        assignments=(
            execution.OperatorAssignment(
                resource_id="operator", operator_subject=FINANCE.subject, capacity_commitment=evidence()
            ),
        ),
        approved_cost_limit=cost,
        permitted_population_and_actions="Fictional bounded population and actions",
        constraints_and_exclusions="No source writes",
        stop_conditions="Stop on quality breach or reported cost overrun",
        rollback_plan="Fictional manual rollback",
        sponsor_authority=evidence(),
    )


def request(case, payload, *, key, previous=None):
    return execution.PrivateExecutionRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        baseline_sha256=case.baseline.content_sha256,
        payload=payload,
        rationale="Fictional receipt, no real operating result",
    )


def record(repo, case, payload, *, key=None, person=None, previous="current"):
    with security.principal_scope(OPERATOR):
        events = repo.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    if previous == "current":
        previous = events[-1] if events else None
    person = person or (FINANCE if isinstance(payload, execution.DeliveryReport) else OPERATING)
    body = request(case, payload, key=key or f"event-{len(events) + 1}", previous=previous)
    with security.principal_scope(person):
        return repo.record_private_execution(COMPANY, case.baseline.baseline_id, body, ENV)


def authorize(repo, case, **kwargs):
    return record(repo, case, execution.AuthorizationDecision(decision="authorize", terms=terms(**kwargs)))


def delivery(
    grant, *, task="foundation", work_key="first", start=None, end=None, cost="10", hours="6", state="completed"
):
    return execution.DeliveryReport(
        task_id=task,
        work_key=work_key,
        authorization=binding(grant),
        state=state,
        started_at=start or at(1, 9),
        through_at=end or at(1, 17),
        incurred_cost=cost,
        reported_effort=(execution.ReportedEffort(resource_id="operator", hours=hours),),
        delivered_scope_and_exceptions="Fictional segment; scope and effort need external verification",
        delivery_evidence=evidence(),
    )


def acceptance(deliveries, *, prerequisites=(), decision="accept"):
    return execution.DeliveryAcceptance(
        task_id=deliveries[0].request.payload.task_id,
        deliveries=tuple(binding(d) for d in deliveries),
        decision=decision,
        prerequisite_acceptances=tuple(binding(p) for p in prerequisites),
        quality_and_scope_assessment="Fictional quality and scope review",
        review_evidence=evidence(),
    )


def status(repo, case):
    with security.principal_scope(OPERATOR):
        return repo.private_execution_status(COMPANY, case.baseline.baseline_id, ENV)


def completed_foundation(repo, clock):
    case = setup(repo)
    grant = authorize(repo, case)
    clock.value = at(2)
    work = record(repo, case, delivery(grant))
    clock.value = at(2, 13)
    accepted = record(repo, case, acceptance([work]))
    return case, grant, work, accepted


def test_named_authorization_delivery_and_distinct_review_preserve_frozen_plan(repo, clock):
    case, grant, first, accepted = completed_foundation(repo, clock)
    frozen = case.baseline.model_dump_json()
    clock.value = at(4)
    second = record(
        repo,
        case,
        delivery(grant, task="price-gate", work_key="second", start=at(3, 9), end=at(3, 17), cost="20", hours="4"),
    )
    final = record(repo, case, acceptance([second], prerequisites=(accepted,)))
    result = status(repo, case)
    assert result["recorded_authorization_currently_supported"]
    assert Decimal(result["reported_cost"]) == 30 and all(t["acceptance_supported"] for t in result["tasks"])
    assert result["origin"] == "synthetic_test_fixture" and not result["causal_value_claim"]
    assert not result["automated_action_executed"] and not case.baseline.operating_action_authorized
    assert case.baseline.model_dump_json() == frozen
    assert final.author != second.author
    for event in (grant, first, accepted, final):
        with pytest.raises(ValueError, match="public exhibits"):
            event.require_public()


@pytest.mark.parametrize(
    "invalid", ["backdated", "past_horizon", "unknown_task", "missing_dependency", "unassigned", "model_assignment"]
)
def test_authorization_requires_explicit_current_plan_scope_and_human_capacity(repo, invalid):
    case = setup(repo)
    raw = terms().model_dump(mode="json")
    if invalid == "backdated":
        raw["valid_from"] = (NOW - timedelta(days=1)).isoformat()
    elif invalid == "past_horizon":
        raw["expires_at"] = "2027-10-01T00:00:00Z"
    elif invalid == "unknown_task":
        raw["task_ids"] = ["unknown"]
    elif invalid == "missing_dependency":
        raw["task_ids"] = ["price-gate"]
    elif invalid == "unassigned":
        raw["assignments"][0]["resource_id"] = "unknown"
    else:
        raw["assignments"][0]["operator_subject"] = "model:claude"
    with pytest.raises(ValueError):
        record(
            repo,
            case,
            execution.AuthorizationDecision(
                decision="authorize", terms=execution.AuthorizationTerms.model_validate(raw)
            ),
        )


@pytest.mark.parametrize(
    "change,expected",
    [("overrun", "cost_limit"), ("outside_window", "cover_work"), ("impossible_hours", "person_hours")],
)
def test_exceptions_are_recorded_but_cannot_support_accepted_completion(repo, clock, change, expected):
    case = setup(repo)
    grant = authorize(repo, case)
    clock.value = at(3)
    supplied = delivery(
        grant, cost="60" if change == "overrun" else "10", hours="12" if change == "impossible_hours" else "6"
    )
    if change == "outside_window":
        supplied = supplied.model_copy(update={"started_at": NOW})
    work = record(repo, case, supplied)
    view = status(repo, case)
    errors = view["tasks"][0]["delivery_segments"][0]["exceptions"]
    assert any(expected in e for e in errors)
    with pytest.raises(ValueError, match=expected):
        record(repo, case, acceptance([work]))
    if change == "overrun":
        assert not view["recorded_authorization_currently_supported"] and view["reported_cost_limit_exceeded"]
        assert Decimal(view["reported_cost"]) == 60


def test_pause_and_reauthorization_keep_disjoint_delivery_segments_and_costs(repo, clock):
    case = setup(repo)
    grant = authorize(repo, case)
    clock.value = at(2)
    first = record(repo, case, delivery(grant, hours="3", cost="10"))
    record(repo, case, execution.AuthorizationDecision(decision="hold"))
    assert not status(repo, case)["recorded_authorization_currently_supported"]
    clock.value = at(3)
    renewed = authorize(repo, case, start=at(4, 0), cost="20")
    clock.value = at(5)
    second = record(
        repo, case, delivery(renewed, work_key="resumed", start=at(4, 9), end=at(4, 17), hours="3", cost="15")
    )
    with pytest.raises(ValueError, match="every current delivery segment"):
        record(repo, case, acceptance([second]))
    record(repo, case, acceptance([first, second]))
    view = status(repo, case)
    assert view["tasks"][0]["acceptance_supported"]
    assert Decimal(view["reported_cost"]) == 25
    assert Decimal(view["current_authorization_reported_cost"]) == 15
    assert view["recorded_authorization_currently_supported"]


def test_work_spanning_a_hold_is_preserved_as_unauthorized_and_not_accepted(repo, clock):
    case = setup(repo)
    grant = authorize(repo, case)
    clock.value = at(2)
    record(repo, case, execution.AuthorizationDecision(decision="hold"))
    clock.value = at(4)
    work = record(repo, case, delivery(grant, end=at(3, 17)))
    with pytest.raises(ValueError, match="authorization_changed"):
        record(repo, case, acceptance([work]))


def test_correction_invalidates_acceptance_and_repeated_reports_do_not_duplicate_cost(repo, clock):
    case, grant, work, accepted = completed_foundation(repo, clock)
    before = accepted.model_dump_json()
    corrected = record(repo, case, delivery(grant, cost="12"))
    view = status(repo, case)
    assert not view["tasks"][0]["acceptance_supported"] and Decimal(view["reported_cost"]) == 12
    with pytest.raises(ValueError, match="corrected"):
        record(repo, case, acceptance([work]))
    record(repo, case, acceptance([corrected]))
    assert status(repo, case)["tasks"][0]["acceptance_supported"]
    assert accepted.model_dump_json() == before
    with security.principal_scope(FINANCE):
        assert repo.record_private_execution(COMPANY, case.baseline.baseline_id, work.request, ENV) == work


def test_prerequisite_review_must_precede_work_and_remain_supported(repo, clock):
    case, grant, work, accepted = completed_foundation(repo, clock)
    clock.value = at(4)
    too_early = record(repo, case, delivery(grant, task="price-gate", work_key="gate", start=at(1, 9), end=at(1, 17)))
    with pytest.raises(ValueError, match="precede dependent"):
        record(repo, case, acceptance([too_early], prerequisites=(accepted,)))
    corrected = record(repo, case, delivery(grant, task="price-gate", work_key="gate", start=at(3, 9), end=at(3, 17)))
    with pytest.raises(ValueError, match="every exact prerequisite"):
        record(repo, case, acceptance([corrected]))
    record(repo, case, acceptance([corrected], prerequisites=(accepted,)))
    record(repo, case, acceptance([work], decision="withdraw"))
    assert not any(t["acceptance_supported"] for t in status(repo, case)["tasks"])


@pytest.mark.parametrize("action", ["hold", "stop", "withdraw"])
def test_reducing_authority_and_acceptance_withdrawal_work_after_revocation(repo, clock, action):
    case, grant, work, _accepted = completed_foundation(repo, clock)
    revoke(repo, case.grant)
    with pytest.raises(security.ScopeError):
        status(repo, case)
    record(repo, case, execution.AuthorizationDecision(decision=action))
    record(repo, case, acceptance([work], decision="withdraw"))
    with pytest.raises(security.ScopeError):
        authorize(repo, case, start=at(4, 0))
    with security.principal_scope(OPERATOR):
        assert len(repo.list_private_execution_events(COMPANY, case.baseline.baseline_id)) == 5
    with security.principal_scope(OPERATING):
        assert repo.record_private_execution(COMPANY, case.baseline.baseline_id, grant.request, ENV) == grant


def test_plan_review_withdrawal_removes_support_without_rewriting_delivery(repo, clock):
    case, _grant, work, _accepted = completed_foundation(repo, clock)
    review_plan(repo, case.plan, "finance", decision="withdraw", key="withdraw", previous=case.finance)
    view = status(repo, case)
    assert not view["baseline_currently_supported"] and not view["recorded_authorization_currently_supported"]
    assert not view["tasks"][0]["acceptance_supported"]
    assert view["tasks"][0]["delivery_segments"][0]["delivery_id"] == work.event_id
    with pytest.raises(ValueError, match="currently supported baseline"):
        record(repo, case, acceptance([work]))
    record(repo, case, execution.AuthorizationDecision(decision="stop"))


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        FINANCE,
        actor(kind="model", roles=("operator", "approver")),
        actor(kind="service", roles=("operator", "approver")),
        actor(company="foreign", roles=("operator", "approver")),
        actor(client="mcp-client", roles=("operator", "approver")),
        actor(roles=("operator", "approver"), scopes=("pvc.read", "pvc.write")),
    ],
)
def test_only_scoped_human_approvers_can_authorize(repo, person):
    case = setup(repo)
    with pytest.raises(security.ScopeError):
        record(repo, case, execution.AuthorizationDecision(decision="authorize", terms=terms()), person=person)


def test_delivery_requires_assigned_operator_and_distinct_acceptance_reviewer(repo, clock):
    case = setup(repo)
    grant = authorize(repo, case)
    clock.value = at(2)
    with pytest.raises(ValueError, match="assigned accountable"):
        record(repo, case, delivery(grant), person=OPERATOR)
    work = record(repo, case, delivery(grant))
    self_reviewer = actor("finance", roles=("operator", "operating_reviewer"))
    with pytest.raises(ValueError, match="different human"):
        record(repo, case, acceptance([work]), person=self_reviewer)


def test_atomic_audit_rollback_and_competing_event_heads(repo, monkeypatch):
    case = setup(repo)
    original = repo.append_audit

    def fail(event):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="injected"):
        authorize(repo, case)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_execution_events(COMPANY, case.baseline.baseline_id) == []
    monkeypatch.setattr(repo, "append_audit", original)

    def submit(key):
        try:
            return record(
                repo, case, execution.AuthorizationDecision(decision="authorize", terms=terms()), key=key, previous=None
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ("first", "second")))
    assert sum(o is not None for o in outcomes) == 1


def test_history_tampering_scope_idempotency_expiry_and_offboarding(repo, clock):
    case, grant, _work, _accepted = completed_foundation(repo, clock)
    changed = grant.model_copy(update={"recorded_at": NOW - timedelta(days=1)})
    changed = changed.model_copy(update={"content_sha256": content_hash(changed)})
    with pytest.raises(ValueError, match="chronology"):
        execution.replay(case.baseline, case.plan, [changed])
    with security.principal_scope(OPERATING), pytest.raises(Conflict):
        repo.record_private_execution(
            COMPANY, case.baseline.baseline_id, grant.request.model_copy(update={"rationale": "changed"}), ENV
        )
    with security.principal_scope(actor(company="foreign")), pytest.raises(security.ScopeError):
        repo.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    clock.value = datetime(2026, 11, 1, tzinfo=UTC)
    with localcontext() as ctx:
        ctx.prec = 2
        view = status(repo, case)
    assert not view["recorded_authorization_currently_supported"]
    assert view["tasks"][0]["acceptance_supported"]  # Valid historical work survives natural expiry.
    with security.principal_scope(OPERATOR):
        assert repo.delete_company_data(COMPANY)["private_execution_events"] == 3
        with pytest.raises(NotFound):
            repo.list_private_execution_events(COMPANY, case.baseline.baseline_id)


def test_aggregate_budget_and_future_status_cannot_hide_exceptions(repo, clock):
    case, grant, _first, accepted = completed_foundation(repo, clock)
    clock.value = at(4)
    second = record(
        repo, case, delivery(grant, task="price-gate", work_key="gate", start=at(3, 9), end=at(3, 17), cost="45")
    )
    with pytest.raises(ValueError, match="cost_limit"):
        record(repo, case, acceptance([second], prerequisites=(accepted,)))
    view = status(repo, case)
    assert view["reported_cost_limit_exceeded"] and Decimal(view["reported_cost"]) == 55
    assert not view["tasks"][0]["acceptance_supported"]
    with security.principal_scope(OPERATOR):
        events = repo.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    with pytest.raises(ValueError, match="predates"):
        execution.execution_view(case.baseline, case.plan, events, baseline_supported=True, now=NOW)


def test_concurrent_authorization_and_revocation_cannot_leave_active_permission(repo, monkeypatch):
    import importlib
    from threading import Event

    case = setup(repo)
    module = importlib.import_module(type(repo).__module__)
    original = module.prepare_private_execution
    entered, attempted, release = Event(), Event(), Event()

    def gate(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    def revoke_processing():
        attempted.set()
        return revoke(repo, case.grant)

    monkeypatch.setattr(module, "prepare_private_execution", gate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        authorization = pool.submit(authorize, repo, case)
        try:
            assert entered.wait(10)
            withdrawal = pool.submit(revoke_processing)
            assert attempted.wait(10) and not withdrawal.done()
        finally:
            release.set()
        authorization.result(timeout=10)
        withdrawal.result(timeout=10)
    with pytest.raises(security.ScopeError):
        status(repo, case)


def test_private_execution_api_roles_body_bounds_and_reduction_after_revocation(repo, clock, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    case = setup(repo)
    people = {"operator": OPERATOR, "operating": OPERATING, "finance": FINANCE, "model": actor(kind="model")}
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
    path = f"/companies/{COMPANY}/private-execution/baselines/{case.baseline.baseline_id}"

    def headers(person):
        return {"Authorization": "Bearer " + person}

    try:
        with TestClient(api.app) as client:
            payload = request(
                case, execution.AuthorizationDecision(decision="authorize", terms=terms()), key="initial"
            ).model_dump(mode="json")
            assert client.post(path + "/events/authorization", json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "operating")
            assert client.post(path + "/events/authorization", json=payload).status_code == 403
            client.cookies.clear()
            for kind in ("authorization", "acceptance"):
                assert (
                    client.post(
                        path + "/events/" + kind, content=b"private-invalid", headers=headers("operator")
                    ).status_code
                    == 404
                )
            for kind in ("authorization", "acceptance", "delivery"):
                endpoint = path + "/events/" + kind
                assert client.post(endpoint, content=b"private-invalid", headers=headers("model")).status_code == 404
                bad = client.post(endpoint, json={"secret": "sensitive-fixture"}, headers=headers("operating"))
                assert bad.status_code == 422 and "sensitive-fixture" not in bad.text
                assert (
                    client.post(endpoint, content=b" " * (1024 * 1024 + 1), headers=headers("operating")).status_code
                    == 413
                )
            assert client.post(path + "/events/delivery", json=payload, headers=headers("operating")).status_code == 422
            created = client.post(path + "/events/authorization", json=payload, headers=headers("operating"))
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            grant = execution.PrivateExecutionEvent.model_validate(created.json())
            clock.value = at(2)
            work_request = request(case, delivery(grant), key="work", previous=grant)
            work_response = client.post(
                path + "/events/delivery", json=work_request.model_dump(mode="json"), headers=headers("finance")
            )
            assert work_response.status_code == 201
            work = execution.PrivateExecutionEvent.model_validate(work_response.json())
            accepted_request = request(case, acceptance([work]), key="accepted", previous=work)
            accepted_response = client.post(
                path + "/events/acceptance", json=accepted_request.model_dump(mode="json"), headers=headers("operating")
            )
            assert accepted_response.status_code == 201
            accepted = execution.PrivateExecutionEvent.model_validate(accepted_response.json())
            assert client.get(path + "/status", headers=headers("operator")).json()[
                "recorded_authorization_currently_supported"
            ]
            revoke(repo, case.grant)
            assert client.get(path + "/status", headers=headers("operator")).status_code == 404
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            stop_request = request(
                case, execution.AuthorizationDecision(decision="stop"), key="stop", previous=accepted
            )
            stopped = client.post(
                path + "/events/authorization", json=stop_request.model_dump(mode="json"), headers=headers("operating")
            )
            assert stopped.status_code == 201
            assert len(client.get(path + "/events", headers=headers("operator")).json()["events"]) == 4
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_execution_rls_immutability_and_populated_owner_downgrade_guard(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade, upgrade

    case = setup(pg_repo)
    authorize(pg_repo, case)
    table = "private_execution_events"
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from private_execution_events").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_execution_events").fetchone()[0] == 1
        for statement in ("delete from private_execution_events", "update private_execution_events set sequence=99"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = current(pg_database[0])
    downgrade(pg_database[0], "0015")
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid=%s::regclass", (table,)
        ).fetchone()[0]
        try:
            conn.execute("alter table private_execution_events owner to pvc_migrator")
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_execution_events").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private execution history"):
                downgrade(owner_url, "0014")
            assert current(pg_database[0]) == "0015"
            assert conn.execute("select relforcerowsecurity from pg_class where oid=%s::regclass", (table,)).fetchone()[
                0
            ]
        finally:
            conn.execute(sql.SQL("alter table private_execution_events owner to {}").format(sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert current(pg_database[0]) == head
