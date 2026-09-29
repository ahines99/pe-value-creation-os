"""Processing permission requires a scoped human decision, preserved with revocation history."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict
from pe_value_os.diligence import private_grants as grants
from pe_value_os.diligence.private_intake import IntakePolicy, fingerprint
from pe_value_os.domain.source_models import CompanyProfile

NOW = datetime(2026, 9, 29, 18, tzinfo=UTC)
COMPANY = "pilot-fixture"


def principal(
    *,
    company=COMPANY,
    subject="human:fixture-owner",
    kind="human",
    roles=("data_owner",),
    scopes=("pvc.read", "pvc.approve"),
    client="approval-ui",
):
    return security.Principal(subject, frozenset({company}), frozenset(roles), kind, frozenset(scopes), client)


@pytest.fixture(autouse=True)
def clock_and_client(monkeypatch):
    class Clock:
        @staticmethod
        def now(zone):
            return NOW

    monkeypatch.setattr(grants, "datetime", Clock)
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "approval-ui")


def policy():
    return IntakePolicy.model_validate_json((Path(__file__).parent / "fixtures/pilot-intake/policy.json").read_bytes())


def request(*, key="initial", previous=None, action="grant", supplied_policy=None):
    return grants.GrantRequest(
        idempotency_key=key,
        action=action,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        policy=(supplied_policy or policy()) if action == "grant" else None,
        operator_subjects=("human:fixture-operator",) if action == "grant" else (),
        environment_id="isolated-test" if action == "grant" else None,
        rationale="Fictional test of exact-scope processing authority; not a company permission.",
        authority_attestation="Fictional test actor only. No actual sponsor or agreement is represented.",
    )


def setup(repo):
    repo.upsert_company(
        CompanyProfile(
            company_id=COMPANY,
            name="Fictional private intake fixture",
            currency="USD",
            business_model="test",
            vertical="test",
            fiscal_year_start_month=1,
        )
    )


def test_grant_revocation_and_reauthorization_preserve_history(repo):
    with security.principal_scope(principal()):
        setup(repo)
        first = repo.record_private_grant(COMPANY, "monthly-ledger", request())
        original = first.model_dump_json()
        status = grants.permission_status(
            repo.list_private_grants(COMPANY, "monthly-ledger"), fingerprint(policy()), now=NOW
        )
        assert status["processing_grant_active"] and status["event_sha256"] == first.content_sha256
        assert (
            not status["finance_reviewed"] and not status["data_admitted"] and not status["operating_action_authorized"]
        )
        revoked = repo.record_private_grant(
            COMPANY, "monthly-ledger", request(key="withdraw", previous=first, action="revoke")
        )
        history = repo.list_private_grants(COMPANY, "monthly-ledger")
        assert grants.permission_status(history, fingerprint(policy()), now=NOW)["reason"] == "revoked"
        # A retried original write returns its historical receipt, never reactivates it.
        assert repo.record_private_grant(COMPANY, "monthly-ledger", request()) == first
        assert len(repo.list_private_grants(COMPANY, "monthly-ledger")) == 2
        restored = repo.record_private_grant(COMPANY, "monthly-ledger", request(key="restore", previous=revoked))
        history = repo.list_private_grants(COMPANY, "monthly-ledger")
        assert [e.sequence for e in history] == [1, 2, 3]
        assert history[0].model_dump_json() == original
        assert grants.permission_status(history, fingerprint(policy()), now=NOW)["event_id"] == restored.event_id
        assert len(repo.list_audit(company_id=COMPANY)) == 3
        assert repo.list_kpi_definitions(COMPANY) == [] and repo.list_runs(COMPANY) == []


def test_exact_policy_binding_expiry_and_future_window(repo):
    with security.principal_scope(principal()):
        setup(repo)
        first = repo.record_private_grant(COMPANY, "ledger", request())
        history = [first]
        assert grants.permission_status(history, "0" * 64, now=NOW)["reason"] == "policy_mismatch"
        assert (
            grants.permission_status(history, fingerprint(policy()), now=policy().expires_at)["reason"]
            == "outside_processing_window"
        )
        future = policy().model_copy(update={"valid_from": datetime(2026, 10, 1, tzinfo=UTC)})
        event = repo.record_private_grant(COMPANY, "future", request(supplied_policy=future))
        assert grants.permission_status([event], fingerprint(future), now=NOW)["reason"] == "outside_processing_window"
        assert grants.permission_status([], fingerprint(policy()), now=NOW)["reason"] == "no_grant"


def test_processing_requires_the_named_operator_environment_and_unrevoked_head(repo):
    with security.principal_scope(principal()):
        setup(repo)
        first = repo.record_private_grant(COMPANY, "ledger", request())
    operator = principal(subject="human:fixture-operator", roles=("operator",), scopes=("pvc.read",))
    with security.principal_scope(operator):
        history = repo.list_private_grants(COMPANY, "ledger")
        assert grants.require_processing_permission(history, policy(), "isolated-test", now=NOW) == first
        with pytest.raises(security.ScopeError):
            grants.require_processing_permission(history, policy(), "another-environment", now=NOW)
        with pytest.raises(security.ScopeError):
            grants.require_processing_permission(
                history, policy().model_copy(update={"purpose": "changed"}), "isolated-test", now=NOW
            )
    with security.principal_scope(principal(subject="human:not-listed", roles=("operator",))):
        with pytest.raises(security.ScopeError):
            grants.require_processing_permission([first], policy(), "isolated-test", now=NOW)
    with security.principal_scope(principal(subject="human:another-data-owner")):
        revoked = repo.record_private_grant(COMPANY, "ledger", request(key="stop", previous=first, action="revoke"))
        assert revoked.actor == "human:another-data-owner"
    with security.principal_scope(operator), pytest.raises(security.ScopeError):
        grants.require_processing_permission(
            repo.list_private_grants(COMPANY, "ledger"), policy(), "isolated-test", now=NOW
        )


def test_stale_head_foreign_policy_and_duplicate_key_fail(repo):
    with security.principal_scope(principal()):
        setup(repo)
        first = repo.record_private_grant(COMPANY, "ledger", request())
        with pytest.raises(Conflict, match="changed"):
            repo.record_private_grant(COMPANY, "ledger", request(key="stale"))
        changed = request().model_copy(update={"rationale": "Different request under the same key"})
        with pytest.raises(Conflict, match="idempotency"):
            repo.record_private_grant(COMPANY, "ledger", changed)
        foreign = policy().model_copy(update={"company_id": "other-company"})
        with pytest.raises(ValueError, match="foreign"):
            repo.record_private_grant(COMPANY, "other", request(supplied_policy=foreign))
        assert repo.list_private_grants(COMPANY, "ledger") == [first]
    with security.principal_scope(principal(subject="human:other-owner")), pytest.raises(Conflict, match="actor"):
        repo.record_private_grant(COMPANY, "ledger", request())


@pytest.mark.parametrize(
    "actor",
    [
        principal(kind="model"),
        principal(kind="service"),
        principal(roles=("approver",)),
        principal(roles=("operator",)),
        principal(scopes=("pvc.read", "pvc.write")),
        principal(scopes=("pvc.approve",)),
        principal(client="mcp-client"),
        principal(company="other-company"),
    ],
)
def test_only_scoped_data_owner_from_approval_client_can_mutate(repo, actor):
    with security.principal_scope(principal()):
        setup(repo)
    with security.principal_scope(actor), pytest.raises(security.ScopeError):
        repo.record_private_grant(COMPANY, "ledger", request())
    with security.principal_scope(principal()):
        assert repo.list_private_grants(COMPANY, "ledger") == []
        assert repo.list_audit(company_id=COMPANY) == []


def test_read_scope_model_and_cross_company_boundaries(repo):
    with security.principal_scope(principal()):
        setup(repo)
        repo.record_private_grant(COMPANY, "ledger", request())
    for actor in (principal(kind="model"), principal(company="other-company"), principal(scopes=())):
        with security.principal_scope(actor), pytest.raises(security.ScopeError):
            repo.list_private_grants(COMPANY, "ledger")
    with security.principal_scope(principal(roles=("operator",), scopes=("pvc.read",))):
        assert len(repo.list_private_grants(COMPANY, "ledger")) == 1


def test_grant_and_audit_rollback_together(repo, monkeypatch):
    with security.principal_scope(principal()):
        setup(repo)

        def fail(event):
            raise RuntimeError("injected audit failure")

        monkeypatch.setattr(repo, "append_audit", fail)
        with pytest.raises(RuntimeError, match="audit"):
            repo.record_private_grant(COMPANY, "ledger", request())
        assert repo.list_private_grants(COMPANY, "ledger") == []


def test_concurrent_initial_grants_have_one_winner(repo):
    with security.principal_scope(principal()):
        setup(repo)

    def submit(key):
        with security.principal_scope(principal()):
            try:
                return repo.record_private_grant(COMPANY, "ledger", request(key=key))
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(submit, ["a", "b"]))
    assert sum(r is not None for r in result) == 1
    with security.principal_scope(principal()):
        assert len(repo.list_private_grants(COMPANY, "ledger")) == 1
        assert len(repo.list_audit(company_id=COMPANY)) == 1


def test_offboarding_removes_private_grants_and_preserves_audit(repo):
    with security.principal_scope(principal()):
        setup(repo)
        repo.record_private_grant(COMPANY, "ledger", request())
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_processing_grants"] == 1
        assert len(repo.list_audit(company_id=COMPANY)) == 1


def test_rehashed_or_incomplete_history_does_not_become_current_authority(repo):
    with security.principal_scope(principal()):
        setup(repo)
        first = repo.record_private_grant(COMPANY, "ledger", request())
        revoked = repo.record_private_grant(COMPANY, "ledger", request(key="revoke", previous=first, action="revoke"))
        with pytest.raises(ValueError, match="incomplete"):
            grants.permission_status([revoked], fingerprint(policy()), now=NOW)
        corrupt = first.model_copy(update={"actor": "human:forged"})
        with pytest.raises(ValueError, match="hash"):
            grants.permission_status([corrupt], fingerprint(policy()), now=NOW)
        with pytest.raises(ValueError, match="hash"):
            grants.GrantEvent.model_validate(corrupt.model_dump(mode="json"))


def test_private_grant_api_requires_bearer_role_client_and_company_scope(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    tokens = {}
    for name, actor in {
        "owner": principal(),
        "other": principal(company="other-company"),
        "operator": principal(roles=("operator",)),
        "model": principal(kind="model"),
        "wrong-client": principal(client="mcp-client"),
    }.items():
        tokens[name] = dict(
            sub=actor.subject,
            pvc_companies=list(actor.companies),
            pvc_roles=list(actor.roles),
            pvc_principal_type=actor.principal_type,
            scope=" ".join(actor.scopes),
            client_id=actor.client_id,
        )
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    api.reset_auth()
    api.set_ctx(SimpleNamespace(repo=repo))
    path = f"/companies/{COMPANY}/private-grants/ledger"
    try:
        with security.principal_scope(principal()):
            setup(repo)
        with TestClient(api.app) as client:
            payload = request().model_dump(mode="json")
            assert client.post(path + "/events", json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "owner")
            assert client.post(path + "/events", json=payload).status_code == 403
            client.cookies.clear()
            for token in ("other", "operator", "model", "wrong-client"):
                assert (
                    client.post(
                        path + "/events", json=payload, headers={"Authorization": "Bearer " + token}
                    ).status_code
                    == 404
                )
            created = client.post(path + "/events", json=payload, headers={"Authorization": "Bearer owner"})
            assert created.status_code == 201
            first = grants.GrantEvent.model_validate(created.json())
            response = client.get(
                path, params={"policy_sha256": fingerprint(policy())}, headers={"Authorization": "Bearer owner"}
            )
            assert response.status_code == 200 and response.json()["current"]["processing_grant_active"]
            assert response.headers["Cache-Control"] == "no-store"
            revoked = request(key="revoke", previous=first, action="revoke").model_dump(mode="json")
            assert (
                client.post(path + "/events", json=revoked, headers={"Authorization": "Bearer owner"}).status_code
                == 201
            )
            current = client.get(
                path, params={"policy_sha256": fingerprint(policy())}, headers={"Authorization": "Bearer owner"}
            ).json()
            assert current["current"]["reason"] == "revoked" and len(current["events"]) == 2
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_database_rls_immutability_and_populated_downgrade_guard(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade

    with security.principal_scope(principal()):
        setup(pg_repo)
        pg_repo.record_private_grant(COMPANY, "ledger", request())
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from private_processing_grants").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_processing_grants").fetchone()[0] == 1
        for statement in ("update private_processing_grants set sequence=99", "delete from private_processing_grants"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='private_processing_grants'::regclass"
        ).fetchone()[0]
        conn.execute("alter table private_processing_grants owner to pvc_migrator")
        conn.execute("grant select,update on alembic_version to pvc_migrator")
        try:
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_processing_grants").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private grant history"):
                downgrade(owner_url, "0007")
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='private_processing_grants'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table private_processing_grants owner to {}").format(sql.Identifier(owner)))
    assert current(pg_database[0]) == "0008"
