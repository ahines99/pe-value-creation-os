"""Custody and finance decisions require fresh permission and exact source versions."""

import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_grants, private_records
from pe_value_os.diligence.private_intake import IntakeManifest, IntakePolicy
from pe_value_os.diligence.private_records import FinanceReviewRequest, IntakeRequest
from pe_value_os.domain.source_models import CompanyProfile

NOW = datetime(2026, 9, 29, 18, tzinfo=UTC)
COMPANY = "pilot-fixture"
ENV = "isolated-test"
FIXTURES = Path(__file__).parent / "fixtures/pilot-intake"


def actor(
    subject="operator",
    *,
    roles=("operator",),
    company=COMPANY,
    scopes=("pvc.read", "pvc.write", "pvc.approve"),
    kind="human",
    client="approval-ui",
):
    return security.Principal(
        "human:" + subject, frozenset({company}), frozenset(roles), kind, frozenset(scopes), client
    )


OWNER = actor("owner", roles=("data_owner",))
OPERATOR = actor()
FINANCE = actor("finance", roles=("operator", "finance_reviewer"))


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock:
        @staticmethod
        def now(zone):
            return NOW

    monkeypatch.setattr(private_grants, "datetime", Clock)
    monkeypatch.setattr(private_records, "datetime", Clock)
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "approval-ui")


def setup(repo):
    policy = IntakePolicy.model_validate_json((FIXTURES / "policy.json").read_bytes())
    with security.principal_scope(OWNER):
        repo.upsert_company(
            CompanyProfile(
                company_id=COMPANY,
                name="Fictional ledger",
                currency="USD",
                business_model="test",
                vertical="test",
                fiscal_year_start_month=1,
            )
        )
        grant = repo.record_private_grant(
            COMPANY,
            "ledger",
            private_grants.GrantRequest(
                idempotency_key="initial",
                action="grant",
                expected_previous_sha256=None,
                policy=policy,
                operator_subjects=(OPERATOR.subject, FINANCE.subject),
                environment_id=ENV,
                rationale="Fictional test",
                authority_attestation="No actual company permission represented",
            ),
        )
    return grant


def intake_request(grant, *, key="initial", previous=None, raw=None):
    manifest = IntakeManifest.model_validate_json((FIXTURES / "manifest.json").read_bytes())
    if raw is not None:
        manifest = manifest.model_copy(update={"source_sha256": hashlib.sha256(raw).hexdigest()})
    return IntakeRequest(
        idempotency_key=key,
        grant_key="ledger",
        expected_grant_sha256=grant.content_sha256,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        policy=grant.request.policy,
        manifest=manifest,
        rationale="Fictional ledger receipt",
    )


def ingest(repo, grant, *, key="initial", previous=None, raw=None):
    raw = raw if raw is not None else (FIXTURES / "ledger.json").read_bytes()
    with security.principal_scope(OPERATOR):
        return repo.record_private_intake(
            COMPANY, "ledger", intake_request(grant, key=key, previous=previous, raw=raw), raw, ENV
        )


def review_request(record, grant, *, decision="accept", previous=None, key="initial"):
    return FinanceReviewRequest(
        idempotency_key=key,
        expected_intake_sha256=record.content_sha256,
        expected_grant_sha256=grant.content_sha256,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        decision=decision,
        rationale="Fictional reconciliation only",
        review_evidence_reference="fixture:finance-control",
        review_evidence_sha256="1" * 64,
    )


def review(repo, record, grant, **kwargs):
    with security.principal_scope(FINANCE):
        return repo.review_private_intake(COMPANY, record.intake_id, review_request(record, grant, **kwargs), ENV)


def revoke(repo, grant):
    with security.principal_scope(OWNER):
        return repo.record_private_grant(
            COMPANY,
            "ledger",
            private_grants.GrantRequest(
                idempotency_key="revoke",
                action="revoke",
                expected_previous_sha256=grant.content_sha256,
                rationale="Stop fictional processing",
                authority_attestation="Fictional owner decision",
            ),
        )


def test_exact_custody_acceptance_withdrawal_and_correction(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    raw = (FIXTURES / "ledger.json").read_bytes()
    assert record.preflight.status == "ready_for_finance_review"
    assert not record.preflight.data_admitted and not record.preflight.operating_action_authorized
    with security.principal_scope(OPERATOR):
        assert repo.private_intake_source(COMPANY, record.intake_id, ENV) == raw
        with pytest.raises(ValueError, match="finance acceptance"):
            repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=True)
    first = review(repo, record, grant)
    for private in (record, first):
        with pytest.raises(ValueError, match="public exhibits"):
            private.require_public()
    with security.principal_scope(OPERATOR):
        assert repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=True) == raw
    withdrawn = review(repo, record, grant, decision="withdraw", previous=first, key="withdraw")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="finance acceptance"):
        repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=True)
    accepted = review(repo, record, grant, previous=withdrawn, key="reaccept")
    replacement = ingest(repo, grant, key="correction", previous=record)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_intakes(COMPANY, "ledger") == [record, replacement]
        assert repo.list_private_finance_reviews(COMPANY, record.intake_id) == [first, withdrawn, accepted]
        assert repo.list_private_finance_reviews(COMPANY, replacement.intake_id) == []
        with pytest.raises(ValueError, match="superseded"):
            repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=True)
        with pytest.raises(ValueError, match="finance acceptance"):
            repo.private_intake_source(COMPANY, replacement.intake_id, ENV, accepted_only=True)
        assert repo.private_intake_source(COMPANY, record.intake_id, ENV) == raw
        assert repo.list_runs(COMPANY) == [] and repo.list_kpi_definitions(COMPANY) == []
    with pytest.raises(Conflict, match="superseded"):
        review(repo, record, grant, key="too-late", previous=accepted)


@pytest.mark.parametrize(
    "raw", [b'{"rows":[]}', b"not-json", (FIXTURES / "ledger.json").read_bytes().replace(b"1000", b"1001")]
)
def test_quarantine_is_preserved_and_cannot_be_accepted(repo, raw):
    grant = setup(repo)
    record = ingest(repo, grant, raw=raw)
    assert record.preflight.status == "quarantined"
    with pytest.raises(ValueError, match="quarantined"):
        review(repo, record, grant)
    rejected = review(repo, record, grant, decision="request_changes")
    with security.principal_scope(OPERATOR):
        assert repo.private_intake_source(COMPANY, record.intake_id, ENV) == raw
        assert repo.list_private_finance_reviews(COMPANY, record.intake_id) == [rejected]


def test_revocation_blocks_new_custody_review_and_source_access_but_keeps_receipts(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    accepted = review(repo, record, grant)
    revoke(repo, grant)
    with pytest.raises(security.ScopeError):
        ingest(repo, grant, previous=record, key="after-revoke")
    with pytest.raises(security.ScopeError):
        review(repo, record, grant, previous=accepted, key="after-revoke")
    with security.principal_scope(OPERATOR):
        for accepted_only in (False, True):
            with pytest.raises(security.ScopeError):
                repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=accepted_only)
        assert repo.list_private_intakes(COMPANY, "ledger") == [record]
    assert ingest(repo, grant) == record  # Historical receipt only; does not reactivate access.
    assert review(repo, record, grant) == accepted


def test_exact_heads_idempotency_and_conflicting_retries(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    assert ingest(repo, grant) == record
    with pytest.raises(Conflict, match="idempotency"):
        ingest(repo, grant, raw=b'{"rows":[]}')
    with pytest.raises(Conflict, match="changed"):
        ingest(repo, grant, key="stale")
    accepted = review(repo, record, grant)
    assert review(repo, record, grant) == accepted
    with pytest.raises(Conflict, match="idempotency"):
        review(repo, record, grant, decision="reject")
    with pytest.raises(Conflict, match="changed"):
        review(repo, record, grant, key="stale")
    with security.principal_scope(OPERATOR):
        assert len(repo.list_audit(company_id=COMPANY)) == 3


@pytest.mark.parametrize(
    "person",
    [
        actor(kind="model"),
        actor(kind="service"),
        actor(roles=("approver",)),
        actor(scopes=("pvc.read",)),
        actor("unnamed"),
        actor(company="foreign"),
    ],
)
def test_only_named_scoped_human_operator_can_store(repo, person):
    grant = setup(repo)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.record_private_intake(
            COMPANY, "ledger", intake_request(grant), (FIXTURES / "ledger.json").read_bytes(), ENV
        )
    with security.principal_scope(OPERATOR):
        assert repo.list_private_intakes(COMPANY, "ledger") == []


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        OWNER,
        actor("finance", roles=("finance_reviewer",)),
        actor("finance", roles=("operator", "finance_reviewer"), scopes=("pvc.read", "pvc.write")),
        actor("finance", roles=("operator", "finance_reviewer"), client="mcp-client"),
        actor("other-finance", roles=("operator", "finance_reviewer")),
    ],
)
def test_only_named_authorized_finance_reviewer_can_decide(repo, person):
    grant = setup(repo)
    record = ingest(repo, grant)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.review_private_intake(COMPANY, record.intake_id, review_request(record, grant), ENV)


def test_scope_environment_and_foreign_lookup(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    with security.principal_scope(OPERATOR):
        with pytest.raises(security.ScopeError):
            repo.private_intake_source(COMPANY, record.intake_id, "wrong-environment")
        with pytest.raises(NotFound):
            repo.list_private_finance_reviews(COMPANY, "00000000-0000-0000-0000-000000000000")
    with security.principal_scope(actor(company="foreign")):
        with pytest.raises(NotFound):
            repo.list_private_finance_reviews("foreign", record.intake_id)
        with pytest.raises(security.ScopeError):
            repo.list_private_intakes(COMPANY, "ledger")
    with security.principal_scope(actor(kind="model")), pytest.raises(security.ScopeError):
        repo.list_private_intakes(COMPANY, "ledger")


def test_stale_grant_and_wrong_intake_bindings_cannot_write(repo):
    grant = setup(repo)
    request = intake_request(grant).model_copy(update={"expected_grant_sha256": "0" * 64})
    with security.principal_scope(OPERATOR):
        with pytest.raises(ValueError, match="exact current grant"):
            repo.record_private_intake(COMPANY, "ledger", request, (FIXTURES / "ledger.json").read_bytes(), ENV)
        assert repo.list_private_intakes(COMPANY, "ledger") == []
    record = ingest(repo, grant)
    for field in ("expected_intake_sha256", "expected_grant_sha256"):
        request = review_request(record, grant).model_copy(update={field: "0" * 64})
        with security.principal_scope(FINANCE), pytest.raises(ValueError, match="exact"):
            repo.review_private_intake(COMPANY, record.intake_id, request, ENV)


def test_processing_expiry_blocks_access_and_review_without_erasing_history(repo, monkeypatch):
    grant = setup(repo)
    record = ingest(repo, grant)
    accepted = review(repo, record, grant)

    class Expired:
        @staticmethod
        def now(zone):
            return grant.request.policy.expires_at

    monkeypatch.setattr(private_records, "datetime", Expired)
    with security.principal_scope(OPERATOR):
        with pytest.raises(security.ScopeError):
            repo.private_intake_source(COMPANY, record.intake_id, ENV, accepted_only=True)
        assert repo.list_private_intakes(COMPANY, "ledger") == [record]
    with pytest.raises(security.ScopeError):
        review(repo, record, grant, key="expired", previous=accepted)


def test_audit_failure_rolls_back_source_and_review(repo, monkeypatch):
    grant = setup(repo)
    append = repo.append_audit

    def fail(event):
        raise RuntimeError("test audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        ingest(repo, grant)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_intakes(COMPANY, "ledger") == []
    if hasattr(repo, "private_sources"):
        assert repo.private_sources == {}
    monkeypatch.setattr(repo, "append_audit", append)
    record = ingest(repo, grant)
    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        review(repo, record, grant)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_finance_reviews(COMPANY, record.intake_id) == []


def test_offboarding_removes_private_sources_and_reviews_but_keeps_audit(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    review(repo, record, grant)
    with security.principal_scope(OPERATOR):
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_intakes"] == 1 and counts["private_intake_reviews"] == 1
        assert counts["private_source_bytes"] == len((FIXTURES / "ledger.json").read_bytes())
        assert len(repo.list_audit(company_id=COMPANY)) == 3
        with pytest.raises(NotFound):
            repo.private_intake_source(COMPANY, record.intake_id, ENV)
    if hasattr(repo, "private_sources"):
        assert repo.private_sources == {}


def test_revocation_transaction_cannot_be_bypassed_by_waiting_intake(repo):
    grant = setup(repo)
    started = Event()

    def waiting_intake():
        started.set()
        return ingest(repo, grant)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with security.principal_scope(OWNER), repo.approval_transaction():
            revoke(repo, grant)
            future = pool.submit(waiting_intake)
            assert started.wait(5)
            assert not future.done()
        with pytest.raises(security.ScopeError):
            future.result(timeout=15)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_intakes(COMPANY, "ledger") == []


def test_concurrent_corrections_have_one_winner(repo):
    grant = setup(repo)
    first = ingest(repo, grant)

    def append(key):
        try:
            return ingest(repo, grant, previous=first, key=key)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, ("a", "b")))
    assert sum(r is not None for r in results) == 1
    with security.principal_scope(OPERATOR):
        assert len(repo.list_private_intakes(COMPANY, "ledger")) == 2


def test_rehashed_preflight_does_not_replace_source_reproduction(repo):
    from decimal import Decimal

    grant = setup(repo)
    record = ingest(repo, grant)
    raw = (FIXTURES / "ledger.json").read_bytes()
    control = record.preflight.controls[0].model_copy(update={"observed": Decimal("999999")})
    forged = record.model_copy(
        update={
            "preflight": record.preflight.model_copy(update={"controls": (control, *record.preflight.controls[1:])})
        }
    )
    forged = forged.model_copy(update={"content_sha256": private_records.content_hash(forged)})
    with security.principal_scope(OPERATOR):
        with pytest.raises(ValueError, match="reproduced"):
            private_records.verify_source(forged, raw)
        with pytest.raises(ValueError, match="no longer matches"):
            private_records.verify_source(record, raw + b" ")


def test_private_api_enforces_auth_encoding_size_environment_and_review(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    grant = setup(repo)
    tokens = {}
    for name, person in {
        "operator": OPERATOR,
        "finance": FINANCE,
        "owner": OWNER,
        "model": actor(kind="model"),
        "foreign": actor(company="other"),
    }.items():
        tokens[name] = dict(
            sub=person.subject,
            pvc_companies=list(person.companies),
            pvc_roles=list(person.roles),
            pvc_principal_type=person.principal_type,
            scope=" ".join(person.scopes),
            client_id=person.client_id,
        )
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
    api.reset_auth()
    api.set_ctx(SimpleNamespace(repo=repo))
    path = f"/companies/{COMPANY}/private-intakes"
    upload_path = path + "/datasets/ledger"
    raw = (FIXTURES / "ledger.json").read_bytes()
    payload = {"intake": intake_request(grant).model_dump(mode="json"), "source_base64": base64.b64encode(raw).decode()}
    headers = {"Authorization": "Bearer operator"}
    try:
        with TestClient(api.app) as client:
            assert client.post(upload_path, json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "operator")
            assert client.post(upload_path, json=payload).status_code == 403
            client.cookies.clear()
            for token in ("owner", "model", "foreign"):
                # Unauthorized callers are rejected before malformed body parsing.
                assert (
                    client.post(
                        upload_path, content=b"not json", headers={"Authorization": "Bearer " + token}
                    ).status_code
                    == 404
                )
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            assert client.post(upload_path, json=payload, headers=headers).status_code == 503
            monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", "wrong")
            assert client.post(upload_path, json=payload, headers=headers).status_code == 404
            monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
            for invalid in (
                {**payload, "source_base64": "private-sensitive-invalid%%%%"},
                {**payload, "intake": {"secret-test-marker": 123}},
            ):
                response = client.post(upload_path, json=invalid, headers=headers)
                assert response.status_code == 422
                assert "secret-test-marker" not in response.text and "private-sensitive" not in response.text
            duplicate = json.dumps(payload)[:-1] + ', "source_base64":"anything"}'
            assert client.post(upload_path, content=duplicate, headers=headers).status_code == 422
            assert client.post(upload_path, content=b" " * (16 * 1024 * 1024 + 1), headers=headers).status_code == 413
            response = client.post(upload_path, json=payload, headers=headers)
            assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
            record = private_records.PrivateIntake.model_validate(response.json())
            assert client.get(upload_path, headers=headers).json()["current_intake_id"] == record.intake_id
            assert client.get(path + "/not-a-uuid/reviews", headers=headers).status_code == 404
            source_path = path + f"/{record.intake_id}/source"
            review_path = path + f"/{record.intake_id}/reviews"
            assert client.get(source_path, params={"accepted_only": True}, headers=headers).status_code == 422
            assert (
                client.post(
                    review_path, json=review_request(record, grant).model_dump(mode="json"), headers=headers
                ).status_code
                == 404
            )
            accepted = client.post(
                review_path,
                json=review_request(record, grant).model_dump(mode="json"),
                headers={"Authorization": "Bearer finance"},
            )
            assert accepted.status_code == 201
            assert len(client.get(review_path, headers=headers).json()["reviews"]) == 1
            downloaded = client.get(source_path, params={"accepted_only": True}, headers=headers)
            assert downloaded.status_code == 200 and downloaded.content == raw
            assert downloaded.headers["cache-control"] == "no-store"
            revoke(repo, grant)
            assert client.get(source_path, headers=headers).status_code == 404
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_private_database_rls_immutability_source_hash_and_downgrade(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade

    grant = setup(pg_repo)
    record = ingest(pg_repo, grant)
    review(pg_repo, record, grant)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        for table in ("private_intakes", "private_intake_reviews"):
            assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        for table in ("private_intakes", "private_intake_reviews"):
            assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 1
            for verb in (f"delete from {table}", f"update {table} set sequence=99"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(verb)
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("update private_intakes set source_bytes=%s", (b"changed",))
        parts = urlsplit(pg_database[0])
        options = dict(parse_qsl(parts.query))
        options["options"] = "-crole=pvc_migrator"
        owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
        owners = {
            table: conn.execute(
                "select pg_get_userbyid(relowner) from pg_class where oid=%s::regclass", (table,)
            ).fetchone()[0]
            for table in ("private_intakes", "private_intake_reviews")
        }
        try:
            for table in owners:
                conn.execute(f"alter table {table} owner to pvc_migrator")
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_intakes").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private source/review history"):
                downgrade(owner_url, "0008")
            assert current(pg_database[0]) == "0009"
            for table in owners:
                assert conn.execute(
                    "select relforcerowsecurity from pg_class where oid=%s::regclass", (table,)
                ).fetchone()[0]
        finally:
            for table, owner in owners.items():
                conn.execute(sql.SQL("alter table {} owner to {}").format(sql.Identifier(table), sql.Identifier(owner)))
