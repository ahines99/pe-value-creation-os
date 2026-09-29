"""Accepted private ledgers become reproducible inputs, not invented value claims."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_financials as financials
from pe_value_os.diligence.private_intake import fingerprint
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_records import (
    COMPANY,
    ENV,
    FINANCE,
    FIXTURES,
    NOW,
    OPERATOR,
    OWNER,
    actor,
    ingest,
    intake_request,
    review,
    revoke,
    setup,
)
from tests.test_private_records import fixed_clock as fixed_clock


@pytest.fixture(autouse=True)
def financial_clock(monkeypatch):
    monkeypatch.setattr(financials, "datetime", SimpleNamespace(now=lambda zone: NOW))


def request(record, accepted, grant, *, key="initial", previous=None, purpose="baseline_candidate"):
    return financials.FinancialSnapshotRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        intake_id=record.intake_id,
        expected_intake_sha256=record.content_sha256,
        expected_finance_review_sha256=accepted.content_sha256,
        expected_grant_sha256=grant.content_sha256,
        purpose=purpose,
        definition=financials.FinancialDefinition(
            accounting_basis="management_accounts",
            earnings_basis="revenue_and_operating_expense_excluding_interest_tax_da",
            cash_basis="disjoint_operating_working_capital_and_capex_flows",
            evidence_reference="fixture:reviewed-account-map",
            evidence_sha256="2" * 64,
            reviewer_attestation="Fictional review: costs exclude interest, tax and D&A; implementation is separate. Operating cash includes implementation settlements and excludes separately mapped working-capital and capex flows. Purpose is within the fictional grant; no actual company authority is represented.",
        ),
        rationale="Fictional private financial input; no claim of company savings",
    )


def snapshot(repo, record, accepted, grant, **kwargs):
    with security.principal_scope(FINANCE):
        return repo.record_private_financial_snapshot(
            COMPANY, "pilot-case", request(record, accepted, grant, **kwargs), ENV
        )


def accepted_source(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    accepted = review(repo, record, grant)
    return grant, record, accepted


def test_worked_financial_inputs_retain_source_authority_without_value_claims(repo):
    grant, record, accepted = accepted_source(repo)
    result = snapshot(repo, record, accepted, grant)
    values = result.period_totals
    assert values.mapped_ebitda == Decimal("630")
    assert values.recurring_operating_contribution == Decimal("680")
    assert values.operating_accrual_to_cash_difference == Decimal("-30")
    assert values.pre_tax_cash_proxy == Decimal("540")
    assert result.monthly[0].amounts == values
    assert result.finance_review_id == accepted.review_id and result.source_sha256 == record.source_sha256
    assert result.origin == "synthetic_test_fixture" and result.classification == "permissioned_private"
    assert (
        not result.frozen_comparison_baseline
        and not result.causal_value_claim
        and not result.operating_action_authorized
    )
    with pytest.raises(ValueError, match="public exhibits"):
        result.require_public()
    with security.principal_scope(OPERATOR):
        assert repo.usable_private_financial_snapshot(COMPANY, result.snapshot_id, ENV) == result
        assert repo.list_private_financial_snapshots(COMPANY, "pilot-case") == [result]
        assert repo.list_runs(COMPANY) == [] and repo.list_kpi_definitions(COMPANY) == []
        assert len(repo.list_audit(company_id=COMPANY)) == 4


def test_exact_bindings_and_source_finance_acceptance_are_required(repo):
    grant = setup(repo)
    record = ingest(repo, grant)
    placeholder = SimpleNamespace(content_sha256="0" * 64)
    with pytest.raises(ValueError, match="finance acceptance"):
        snapshot(repo, record, placeholder, grant)
    accepted = review(repo, record, grant)
    for field in ("expected_intake_sha256", "expected_finance_review_sha256", "expected_grant_sha256"):
        supplied = request(record, accepted, grant).model_copy(update={field: "0" * 64})
        with security.principal_scope(FINANCE), pytest.raises(ValueError, match="exact current"):
            repo.record_private_financial_snapshot(COMPANY, "pilot-case", supplied, ENV)
    with security.principal_scope(FINANCE):
        assert repo.list_private_financial_snapshots(COMPANY, "pilot-case") == []


def test_source_correction_requires_new_acceptance_and_preserves_original_financials(repo):
    grant, record, accepted = accepted_source(repo)
    original = snapshot(repo, record, accepted, grant)
    original_bytes = original.model_dump_json()
    corrected = ingest(repo, grant, key="corrected", previous=record)
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_financial_snapshot(COMPANY, original.snapshot_id, ENV)
    with pytest.raises(ValueError, match="finance acceptance"):
        snapshot(repo, corrected, accepted, grant, key="new", previous=original)
    new_acceptance = review(repo, corrected, grant)
    new = snapshot(repo, corrected, new_acceptance, grant, key="new", previous=original, purpose="observed_actuals")
    assert new.sequence == 2 and new.period_totals == original.period_totals
    assert new.request.expected_previous_sha256 == original.content_sha256
    with security.principal_scope(OPERATOR):
        assert repo.list_private_financial_snapshots(COMPANY, "pilot-case") == [original, new]
        assert repo.list_private_financial_snapshots(COMPANY, "pilot-case")[0].model_dump_json() == original_bytes
        assert repo.usable_private_financial_snapshot(COMPANY, new.snapshot_id, ENV) == new


def test_withdrawal_reacceptance_and_revocation_do_not_reactivate_old_snapshot(repo):
    grant, record, accepted = accepted_source(repo)
    original = snapshot(repo, record, accepted, grant)
    withdrawn = review(repo, record, grant, decision="withdraw", previous=accepted, key="withdraw")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="finance acceptance"):
        repo.usable_private_financial_snapshot(COMPANY, original.snapshot_id, ENV)
    reaccepted = review(repo, record, grant, previous=withdrawn, key="reaccept")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="authority changed"):
        repo.usable_private_financial_snapshot(COMPANY, original.snapshot_id, ENV)
    current = snapshot(repo, record, reaccepted, grant, previous=original, key="new")
    revoke(repo, grant)
    with security.principal_scope(OPERATOR):
        with pytest.raises(security.ScopeError):
            repo.usable_private_financial_snapshot(COMPANY, current.snapshot_id, ENV)
        assert len(repo.list_private_financial_snapshots(COMPANY, "pilot-case")) == 2
    with pytest.raises(security.ScopeError):
        snapshot(repo, record, reaccepted, grant, previous=current, key="after-revoke")
    assert snapshot(repo, record, accepted, grant) == original  # Receipt only.


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        OWNER,
        actor("finance", roles=("operator", "finance_reviewer"), scopes=("pvc.read", "pvc.approve")),
        actor("finance", roles=("operator", "finance_reviewer"), kind="model"),
        actor("finance", roles=("operator", "finance_reviewer"), client="mcp-client"),
        actor("unknown", roles=("operator", "finance_reviewer")),
    ],
)
def test_snapshot_requires_named_human_finance_and_write_rights(repo, person):
    grant, record, accepted = accepted_source(repo)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.record_private_financial_snapshot(COMPANY, "pilot-case", request(record, accepted, grant), ENV)


def test_scope_environment_and_identifier_boundaries(repo):
    grant, record, accepted = accepted_source(repo)
    with security.principal_scope(FINANCE), pytest.raises(security.ScopeError):
        repo.record_private_financial_snapshot(COMPANY, "pilot-case", request(record, accepted, grant), "wrong")
    result = snapshot(repo, record, accepted, grant)
    with security.principal_scope(OPERATOR):
        with pytest.raises(NotFound):
            repo.usable_private_financial_snapshot(COMPANY, "invalid-id", ENV)
        with pytest.raises(security.ScopeError):
            repo.usable_private_financial_snapshot(COMPANY, result.snapshot_id, "wrong")
    with security.principal_scope(actor(company="foreign")), pytest.raises(security.ScopeError):
        repo.list_private_financial_snapshots(COMPANY, "pilot-case")
    with security.principal_scope(actor(kind="model")), pytest.raises(security.ScopeError):
        repo.list_private_financial_snapshots(COMPANY, "pilot-case")


def test_replay_conflict_concurrent_heads_and_audit_rollback(repo, monkeypatch):
    grant, record, accepted = accepted_source(repo)
    original_append = repo.append_audit

    def fail(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        snapshot(repo, record, accepted, grant)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_financial_snapshots(COMPANY, "pilot-case") == []
    monkeypatch.setattr(repo, "append_audit", original_append)
    first = snapshot(repo, record, accepted, grant)
    assert snapshot(repo, record, accepted, grant) == first
    with pytest.raises(Conflict, match="idempotency"):
        snapshot(repo, record, accepted, grant, purpose="observed_actuals")

    def append(key):
        try:
            return snapshot(repo, record, accepted, grant, previous=first, key=key)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, ("a", "b")))
    assert sum(r is not None for r in results) == 1


def test_rehashing_financial_values_scope_or_raw_bytes_cannot_pass_reproduction(repo):
    grant, record, accepted = accepted_source(repo)
    result = snapshot(repo, record, accepted, grant)
    raw = (FIXTURES / "ledger.json").read_bytes()
    for update in (
        {"currency": "EUR"},
        {"period_totals": result.period_totals.model_copy(update={"mapped_ebitda": Decimal("999999")})},
    ):
        forged = result.model_copy(update=update)
        forged = forged.model_copy(update={"content_sha256": content_hash(forged)})
        with security.principal_scope(OPERATOR), pytest.raises(ValueError, match=r"scope|reproduce"):
            financials.verify_snapshot(forged, record, raw)
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="no longer matches"):
        financials.verify_snapshot(result, record, raw + b" ")


def test_multiple_months_preserve_calendar_controls_and_decimal_precision(repo):
    grant = setup(repo)
    original_rows = json.loads((FIXTURES / "ledger.json").read_bytes())["rows"]
    rows = [{**r, "period": "2026-07-01", "source_row_id": "july-" + r["source_row_id"]} for r in original_rows]
    rows += [{**r, "period": "2026-08-01", "amount": str(Decimal(r["amount"]) * 2)} for r in original_rows]
    policy = grant.request.policy
    controls = tuple(c.model_copy(update={"period": date(2026, 7, 1)}) for c in policy.controls)
    controls += tuple(
        c.model_copy(update={"period": date(2026, 8, 1), "amount": c.amount * 2}) for c in policy.controls
    )
    policy = policy.model_copy(update={"first_month": date(2026, 7, 1), "months": 2, "controls": controls})
    with security.principal_scope(OWNER):
        grant = repo.record_private_grant(
            COMPANY,
            "ledger",
            grant.request.model_copy(
                update={
                    "idempotency_key": "two-months",
                    "expected_previous_sha256": grant.content_sha256,
                    "policy": policy,
                }
            ),
        )
    raw = json.dumps({"schema_version": 1, "rows": rows}).encode()
    supplied = intake_request(grant, raw=raw)
    supplied = supplied.model_copy(
        update={
            "manifest": supplied.manifest.model_copy(
                update={
                    "policy_sha256": fingerprint(policy),
                    "record_count": len(rows),
                    "data_cutoff": date(2026, 8, 31),
                }
            )
        }
    )
    with security.principal_scope(OPERATOR):
        record = repo.record_private_intake(COMPANY, "ledger", supplied, raw, ENV)
    accepted = review(repo, record, grant)
    with localcontext() as ctx:
        ctx.prec = 2
        result = snapshot(repo, record, accepted, grant)
    assert [m.start for m in result.monthly] == [date(2026, 7, 1), date(2026, 8, 1)]
    assert [m.amounts.mapped_ebitda for m in result.monthly] == [Decimal("630"), Decimal("1260")]
    assert result.period_totals.mapped_ebitda == Decimal("1890")
    assert result.period_totals.pre_tax_cash_proxy == Decimal("1620")


def test_company_offboarding_removes_financial_snapshots(repo):
    grant, record, accepted = accepted_source(repo)
    result = snapshot(repo, record, accepted, grant)
    with security.principal_scope(OPERATOR):
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_financial_snapshots"] == 1
        assert len(repo.list_audit(company_id=COMPANY)) == 4
        with pytest.raises(NotFound):
            repo.usable_private_financial_snapshot(COMPANY, result.snapshot_id, ENV)


def test_losses_and_cash_outflows_are_not_clipped_or_called_savings(repo):
    grant = setup(repo)
    policy = grant.request.policy
    mapping = {m.account_code: m.component for m in policy.mappings}
    ledger = json.loads((FIXTURES / "ledger.json").read_bytes())
    ledger["rows"][0]["amount"] = "0.00"
    for row in ledger["rows"]:
        if mapping[row["account_code"]] in {"operating_cash", "working_capital_cash"}:
            row["amount"] = str(-abs(Decimal(row["amount"])))
    changed = {"revenue": Decimal("-20"), "operating_cash": Decimal("-600"), "working_capital_cash": Decimal("-40")}
    policy = policy.model_copy(
        update={
            "controls": tuple(
                c.model_copy(update={"amount": changed.get(c.component, c.amount)}) for c in policy.controls
            )
        }
    )
    with security.principal_scope(OWNER):
        grant = repo.record_private_grant(
            COMPANY,
            "ledger",
            grant.request.model_copy(
                update={
                    "idempotency_key": "loss-case",
                    "expected_previous_sha256": grant.content_sha256,
                    "policy": policy,
                }
            ),
        )
    raw = json.dumps(ledger).encode()
    supplied = intake_request(grant, raw=raw)
    supplied = supplied.model_copy(
        update={"manifest": supplied.manifest.model_copy(update={"policy_sha256": fingerprint(policy)})}
    )
    with security.principal_scope(OPERATOR):
        record = repo.record_private_intake(COMPANY, "ledger", supplied, raw, ENV)
    accepted = review(repo, record, grant)
    result = snapshot(repo, record, accepted, grant)
    assert result.period_totals.mapped_ebitda == Decimal("-370")
    assert result.period_totals.pre_tax_cash_proxy == Decimal("-740")
    assert not result.causal_value_claim


def test_private_financial_api_keeps_historical_receipts_separate_from_usable_inputs(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    grant, record, accepted = accepted_source(repo)
    tokens = {}
    for name, person in {"finance": FINANCE, "operator": OPERATOR, "model": actor(kind="model")}.items():
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
    path = f"/companies/{COMPANY}/private-financials"
    case_path = path + "/cases/pilot-case"
    headers = {"Authorization": "Bearer finance"}
    payload = request(record, accepted, grant).model_dump(mode="json")
    try:
        with TestClient(api.app) as client:
            assert client.post(case_path, json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "finance")
            assert client.post(case_path, json=payload).status_code == 403
            client.cookies.clear()
            for person in ("operator", "model"):
                assert (
                    client.post(
                        case_path, content=b"private-invalid", headers={"Authorization": "Bearer " + person}
                    ).status_code
                    == 404
                )
            bad = client.post(case_path, json={"confidential": "sensitive-fixture-value"}, headers=headers)
            assert bad.status_code == 422 and "sensitive-fixture-value" not in bad.text
            assert client.post(case_path, content=b" " * (1024 * 1024 + 1), headers=headers).status_code == 413
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            assert client.post(case_path, json=payload, headers=headers).status_code == 503
            monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
            created = client.post(case_path, json=payload, headers=headers)
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            result = financials.PrivateFinancialSnapshot.model_validate(created.json())
            history = client.get(case_path, headers=headers).json()
            assert history["historical_records_only"] and len(history["snapshots"]) == 1
            usable_path = path + f"/snapshots/{result.snapshot_id}/usable"
            assert client.get(usable_path, headers=headers).json()["source_currently_accepted"]
            assert client.get(path + "/snapshots/invalid/usable", headers=headers).status_code == 404
            revoke(repo, grant)
            assert client.get(usable_path, headers=headers).status_code == 404
            assert client.get(case_path, headers=headers).status_code == 200
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_financial_case_cannot_silently_change_entity(repo):
    grant, record, accepted = accepted_source(repo)
    first = snapshot(repo, record, accepted, grant)
    policy = grant.request.policy.model_copy(update={"entity_id": "another-entity"})
    with security.principal_scope(OWNER):
        grant = repo.record_private_grant(
            COMPANY,
            "ledger",
            grant.request.model_copy(
                update={
                    "idempotency_key": "entity-change",
                    "expected_previous_sha256": grant.content_sha256,
                    "policy": policy,
                }
            ),
        )
    ledger = json.loads((FIXTURES / "ledger.json").read_bytes())
    for row in ledger["rows"]:
        row["entity_id"] = "another-entity"
    raw = json.dumps(ledger).encode()
    supplied = intake_request(grant, raw=raw, previous=record, key="entity-correction")
    supplied = supplied.model_copy(
        update={"manifest": supplied.manifest.model_copy(update={"policy_sha256": fingerprint(policy)})}
    )
    with security.principal_scope(OPERATOR):
        replacement = repo.record_private_intake(COMPANY, "ledger", supplied, raw, ENV)
    new_review = review(repo, replacement, grant)
    with pytest.raises(ValueError, match="cannot mix"):
        snapshot(repo, replacement, new_review, grant, key="change", previous=first)


def test_financial_database_rls_immutability_and_populated_downgrade_guard(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade

    grant, record, accepted = accepted_source(pg_repo)
    snapshot(pg_repo, record, accepted, grant)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from private_financial_snapshots").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_financial_snapshots").fetchone()[0] == 1
        for statement in (
            "delete from private_financial_snapshots",
            "update private_financial_snapshots set sequence=99",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='private_financial_snapshots'::regclass"
        ).fetchone()[0]
        try:
            conn.execute("alter table private_financial_snapshots owner to pvc_migrator")
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_financial_snapshots").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private financial history"):
                downgrade(owner_url, "0009")
            assert current(pg_database[0]) == "0010"
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='private_financial_snapshots'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table private_financial_snapshots owner to {}").format(sql.Identifier(owner)))
