"""Exact-version review, preserved economics and real restricted-role persistence."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from pydantic import ValidationError
from scripts.build_operating_plan_example import example as plan_example
from scripts.build_underwriting_example import example

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import CasePayload, CaseRevision, ReviewRequest, RevisionDraft, compare_revisions
from pe_value_os.domain.source_models import CompanyProfile


def principal(company="exercise", *, kind="service", scopes=None, subject=None):
    return security.Principal(
        subject=subject or f"{kind}:test",
        companies=frozenset({company}),
        principal_type=kind,
        roles=frozenset({"approver"}) if kind == "human" else frozenset(),
        scopes=scopes,
    )


def draft(*, scheduled=False, stage="underwriting", reason="Initial constructed economics"):
    return RevisionDraft(
        stage=stage,
        effective_on=date(2026, 10, 1),
        reason=reason,
        payload=CasePayload(
            underwriting=example(),
            operating_plan=plan_example() if scheduled else None,
            decision_question="Is the constructed first wave feasible under its disclosed assumptions?",
            counterevidence=("No actual operating data or confirmed capacity",),
            unresolved_items=("Actual pilot sponsor and management review absent",),
        ),
    )


def setup(repo, company="exercise"):
    repo.upsert_company(
        CompanyProfile(
            company_id=company,
            name="Constructed exercise",
            business_model="example",
            vertical="example",
            currency="USD",
            fiscal_year_start_month=1,
        )
    )
    return repo.create_investment_case(company, example().case_id, "Research exercise", "USD")


def request(revision, mode="simulation", decision="accept", previous=None):
    return ReviewRequest(
        expected_revision_sha256=revision.content_sha256,
        mode=mode,
        decision=decision,
        rationale="Review of modeled assumptions only; no actual outcome or execution approval.",
        supersedes_review_id=previous,
    )


def test_revisions_preserve_original_and_stored_results(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        original = repo.append_case_revision(case.case_id, None, draft())
        before = original.model_dump_json()
        review = repo.review_case_revision(original.revision_id, request(original))
        revised = repo.append_case_revision(
            case.case_id,
            original.revision_id,
            draft(scheduled=True, stage="ownership_review", reason="Resource feasibility delays service"),
        )
        assert repo.get_case_revision(original.revision_id).model_dump_json() == before
        assert repo.get_investment_case(case.case_id).original_revision_id == original.revision_id
        assert repo.get_investment_case(case.case_id).current_revision_id == revised.revision_id
        assert [r.sequence for r in repo.list_case_revisions(case.case_id)] == [1, 2]
        assert repo.list_case_reviews(case.case_id) == [review]
        result = compare_revisions(original, revised)
        assert result["actuals"] is None and result["measurement_state"] == "modeled_only"
        assert result["original_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"] == "228266.97"
        assert result["current_financials"]["scenarios"][1]["year_one"]["incremental_ebitda"] == "218976.65"
        assert original.financial_result_json != revised.financial_result_json
        assert len(repo.list_audit(company_id="exercise")) == 4
        assert repo.list_kpi_definitions("exercise") == []
        assert repo.list_runs("exercise") == []
        with pytest.raises(ValidationError):
            original.draft.reason = "overwrite"
        corrupt = original.model_dump(mode="json")
        corrupt["financial_result_json"] = "{}"
        with pytest.raises(ValueError, match="hash"):
            CaseRevision.model_validate(corrupt)


def test_stale_parent_and_review_hash_rejected(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        first = repo.append_case_revision(case.case_id, None, draft())
        with pytest.raises(Conflict):
            repo.append_case_revision(case.case_id, None, draft())
        bad = request(first).model_copy(update={"expected_revision_sha256": "0" * 64})
        with pytest.raises(ValueError, match="exact"):
            repo.review_case_revision(first.revision_id, bad)
        repo.append_case_revision(case.case_id, first.revision_id, draft(scheduled=True))
        with pytest.raises(Conflict, match="stale"):
            repo.review_case_revision(first.revision_id, request(first))
        assert repo.list_case_reviews(case.case_id) == []


def test_append_only_review_correction_and_withdrawal(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        first = repo.append_case_revision(case.case_id, None, draft())
        accepted = repo.review_case_revision(first.revision_id, request(first))
        with pytest.raises(Conflict):
            repo.review_case_revision(first.revision_id, request(first))
        corrected = repo.review_case_revision(
            first.revision_id, request(first, decision="request_changes", previous=accepted.review_id)
        )
        with pytest.raises(Conflict):
            repo.review_case_revision(first.revision_id, request(first, decision="reject", previous=accepted.review_id))
        repo.append_case_revision(case.case_id, first.revision_id, draft(scheduled=True))
        withdrawn = repo.review_case_revision(
            first.revision_id, request(first, decision="withdraw", previous=corrected.review_id)
        )
        assert repo.list_case_reviews(case.case_id) == [accepted, corrected, withdrawn]


def test_model_and_service_cannot_sign_human_review(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        first = repo.append_case_revision(case.case_id, None, draft())
    for kind in ("service", "model"):
        with security.principal_scope(principal(kind=kind)):
            with pytest.raises(security.ScopeError):
                repo.review_case_revision(first.revision_id, request(first, mode="human"))
            simulated = repo.review_case_revision(first.revision_id, request(first))
            assert simulated.mode == "simulation" and simulated.actor_type == kind
    with security.principal_scope(principal(kind="human")):
        actual = repo.review_case_revision(first.revision_id, request(first, mode="human"))
        assert actual.mode == "human" and actual.actor == "human:test"
        assert repo.list_kpi_definitions("exercise") == []
        assert repo.get_investment_case(case.case_id).version == 1


def test_scope_and_foreign_review_reference_rejected(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        first = repo.append_case_revision(case.case_id, None, draft())
        receipt = repo.review_case_revision(first.revision_id, request(first))
    with security.principal_scope(principal("outsider")):
        for lookup in (
            lambda: repo.get_investment_case(case.case_id),
            lambda: repo.get_case_revision(first.revision_id),
            lambda: repo.list_case_reviews(case.case_id),
            lambda: repo.list_case_revisions(case.case_id),
        ):
            with pytest.raises(NotFound):
                lookup()
    with security.principal_scope(principal(subject="service:another")):
        with pytest.raises(security.ScopeError):
            repo.review_case_revision(first.revision_id, request(first, previous=receipt.review_id))
    with security.principal_scope(principal(kind="human")):
        with pytest.raises(ValueError, match="mode"):
            repo.review_case_revision(first.revision_id, request(first, mode="human", previous=receipt.review_id))


def test_write_scope_and_company_currency_enforced(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
    with security.principal_scope(principal(scopes=frozenset())):
        with pytest.raises(security.ScopeError):
            repo.append_case_revision(case.case_id, None, draft())
    with security.principal_scope(principal()):
        wrong = draft().model_dump(mode="json")
        wrong["payload"]["underwriting"]["currency"] = "EUR"
        with pytest.raises(ValueError, match="currency"):
            repo.append_case_revision(case.case_id, None, RevisionDraft.model_validate(wrong))
        with pytest.raises(ValueError, match="first"):
            repo.append_case_revision(case.case_id, None, draft(stage="exit_review"))
        assert repo.list_case_revisions(case.case_id) == []


def test_audit_failure_rolls_back_case_head_and_receipt(repo, monkeypatch):
    with security.principal_scope(principal()):
        case = setup(repo)
        initial = repo.append_case_revision(case.case_id, None, draft())

        def fail(*args, **kwargs):
            raise RuntimeError("injected audit failure")

        monkeypatch.setattr(repo, "append_audit", fail)
        with pytest.raises(RuntimeError):
            repo.append_case_revision(case.case_id, initial.revision_id, draft(scheduled=True))
        assert repo.get_investment_case(case.case_id).version == 1
        assert repo.list_case_revisions(case.case_id) == [initial]
        with pytest.raises(RuntimeError):
            repo.review_case_revision(initial.revision_id, request(initial))
        assert repo.list_case_reviews(case.case_id) == []


def test_two_writers_cannot_lose_history(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        initial = repo.append_case_revision(case.case_id, None, draft())

    def append():
        with security.principal_scope(principal()):
            try:
                return repo.append_case_revision(case.case_id, initial.revision_id, draft(scheduled=True))
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: append(), range(2)))
    assert sum(r is not None for r in results) == 1
    with security.principal_scope(principal()):
        assert len(repo.list_case_revisions(case.case_id)) == 2


def test_whole_company_offboarding_removes_case_records(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        initial = repo.append_case_revision(case.case_id, None, draft())
        repo.review_case_revision(initial.revision_id, request(initial))
        counts = repo.delete_company_data("exercise")
        assert counts["case_revisions"] == counts["case_reviews"] == counts["investment_cases"] == 1
        with pytest.raises(NotFound):
            repo.get_investment_case(case.case_id)


def test_postgres_rls_and_immutable_rows(pg_repo, pg_database):
    import psycopg
    from psycopg.types.json import Jsonb

    with security.principal_scope(principal()):
        case = setup(pg_repo)
        initial = pg_repo.append_case_revision(case.case_id, None, draft())
        review = pg_repo.review_case_revision(initial.revision_id, request(initial))
    _, app_url = pg_database
    with psycopg.connect(app_url, autocommit=True) as conn:
        for table in ("investment_cases", "case_revisions", "case_reviews"):
            assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies','exercise',false)")
        for table, id_column, record_id in (
            ("case_revisions", "revision_id", initial.revision_id),
            ("case_reviews", "review_id", review.review_id),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"update {table} set record='{{}}' where {id_column}=%s", (record_id,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"delete from {table} where {id_column}=%s", (record_id,))
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("update investment_cases set original_revision_id=null where case_id=%s", (case.case_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into case_revisions(revision_id,company_id,case_id,sequence,content_sha256,record) values(%s,'outsider',%s,2,%s,%s)",
                (str(uuid.uuid4()), case.case_id, initial.content_sha256, Jsonb(initial.model_dump(mode="json"))),
            )


def test_composite_foreign_keys_reject_cross_company_parent(pg_repo, pg_database):
    import psycopg
    from psycopg.types.json import Jsonb

    with security.principal_scope(principal()):
        case = setup(pg_repo)
        initial = pg_repo.append_case_revision(case.case_id, None, draft())
    with security.principal_scope(principal("outsider")):
        pg_repo.upsert_company(
            CompanyProfile(
                company_id="outsider",
                name="Other",
                business_model="example",
                vertical="example",
                currency="USD",
                fiscal_year_start_month=1,
            )
        )
        pg_repo.create_investment_case("outsider", "other-case", "Other case", "USD")
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        conn.execute("select set_config('pvc.companies','exercise,outsider',false)")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "insert into case_revisions(revision_id,company_id,case_id,sequence,parent_revision_id,content_sha256,record) values(%s,'outsider','other-case',1,%s,%s,%s)",
                (
                    str(uuid.uuid4()),
                    initial.revision_id,
                    initial.content_sha256,
                    Jsonb(initial.model_dump(mode="json")),
                ),
            )


def test_populated_legacy_upgrade_and_safe_downgrade(pg_repo, pg_database):
    from datetime import UTC, datetime

    from pe_value_os.db.migrate import current, downgrade, upgrade
    from pe_value_os.domain.runs import PlanRecord

    admin_url, _ = pg_database
    with security.principal_scope(principal()):
        pg_repo.upsert_company(
            CompanyProfile(
                company_id="exercise",
                name="Legacy company",
                business_model="example",
                vertical="example",
                currency="USD",
                fiscal_year_start_month=1,
            )
        )
        run, _ = pg_repo.create_run("exercise", "legacy-user")
        legacy = PlanRecord(
            plan_id=str(uuid.uuid4()),
            run_id=run.run_id,
            company_id="exercise",
            status="approved",
            plan={"legacy": "original"},
            approved_plan={"legacy": "approved"},
            created_at=datetime.now(UTC),
            approved_at=datetime.now(UTC),
        )
        pg_repo.save_plan(legacy)
        try:
            downgrade(admin_url, "0003")
            assert current(admin_url) == "0003"
            upgrade(admin_url)
            assert pg_repo.get_plan(legacy.plan_id) == legacy
            assert pg_repo.get_run(run.run_id) == run
            pg_repo.create_investment_case("exercise", example().case_id, "New research", "USD")
            pg_repo.append_case_revision(example().case_id, None, draft())
            with pytest.raises(RuntimeError, match="Case history exists"):
                downgrade(admin_url, "0003")
            assert current(admin_url) == "0004"
            assert pg_repo.get_plan(legacy.plan_id) == legacy
        finally:
            upgrade(admin_url)


def test_case_api_preserves_auth_csrf_and_exact_version(repo, monkeypatch):
    import json
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    tokens = {
        "writer": {
            "sub": "service:test",
            "pvc_companies": ["exercise"],
            "pvc_principal_type": "service",
            "scope": "pvc.read pvc.write",
        },
        "reviewer": {
            "sub": "human:test",
            "pvc_companies": ["exercise"],
            "pvc_principal_type": "human",
            "pvc_roles": ["approver"],
            "scope": "pvc.read pvc.approve",
        },
        "model": {
            "sub": "model:test",
            "pvc_companies": ["exercise"],
            "pvc_principal_type": "model",
            "pvc_roles": ["approver"],
            "scope": "pvc.read pvc.write pvc.approve",
        },
        "outsider": {
            "sub": "human:other",
            "pvc_companies": ["outsider"],
            "pvc_principal_type": "human",
            "scope": "pvc.read",
        },
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with security.principal_scope(principal()):
        repo.upsert_company(
            CompanyProfile(
                company_id="exercise",
                name="Exercise",
                business_model="example",
                vertical="example",
                currency="USD",
                fiscal_year_start_month=1,
            )
        )
    client = TestClient(api.app)
    create = {"company_id": "exercise", "case_id": example().case_id, "label": "Example", "currency": "USD"}
    assert client.post("/cases", json=create).status_code == 401
    client.cookies.set("pvc_dev_session", "writer")
    assert client.post("/cases", json=create).status_code == 403
    h = {"Authorization": "Bearer writer"}
    assert client.post("/cases", json=create, headers=h).status_code == 201
    path = f"/cases/{example().case_id}"
    saved = client.post(
        path + "/revisions",
        headers=h,
        json={"expected_parent_revision_id": None, "draft": draft().model_dump(mode="json")},
    )
    assert saved.status_code == 201, saved.text
    record = CaseRevision.model_validate(saved.json())
    review_path = f"/case-revisions/{record.revision_id}/reviews"
    body = request(record, mode="human").model_dump(mode="json")
    assert client.post(review_path, headers={"Authorization": "Bearer model"}, json=body).status_code == 404
    assert (
        client.post(
            review_path, headers={"Authorization": "Bearer writer"}, json={**body, "actor": "human:forged"}
        ).status_code
        == 422
    )
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "allowed-review-ui")
    assert client.post(review_path, headers={"Authorization": "Bearer reviewer"}, json=body).status_code == 404
    monkeypatch.delenv("PVC_API_CLIENT_IDS")
    assert client.post(review_path, headers={"Authorization": "Bearer reviewer"}, json=body).status_code == 201
    assert client.post(review_path, headers={"Authorization": "Bearer reviewer"}, json=body).status_code == 409
    assert client.get(path, headers={"Authorization": "Bearer outsider"}).status_code == 404
    assert client.get(path, headers=h).json()["comparison"]["actuals"] is None
    assert (
        client.post(
            path + "/revisions",
            headers=h,
            json={"expected_parent_revision_id": None, "draft": draft().model_dump(mode="json")},
        ).status_code
        == 409
    )
    assert client.post("/case-revisions/not-a-uuid/reviews", headers=h, json=body).status_code == 404


def test_case_replay_never_fabricates_human_or_actual_evidence(tmp_path):
    import json
    from pathlib import Path

    from pe_value_os.cli import main
    from pe_value_os.diligence.case_render import build_case_demo, demonstrate_revisions, render_case_history

    output = tmp_path / "history"
    underwriting = Path("data/constructed/progress/underwriting.json")
    plan = Path("data/constructed/progress/operating-plan.json")
    assert (
        main(
            [
                "case-history-demo",
                "--underwriting",
                str(underwriting),
                "--operating-plan",
                str(plan),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["human_review_count"] == 0
    assert [r["mode"] for r in report["reviews"]] == ["simulation", "simulation"]
    assert all(r["actor_type"] == "service" for r in report["reviews"])
    assert report["comparison"]["actuals"] is None
    assert len(report["audit"]) == 5
    second = demonstrate_revisions(example(), plan_example())
    assert second["comparison"]["current_financials"] == report["comparison"]["current_financials"]
    assert second["reviews"][0]["review_id"] != report["reviews"][0]["review_id"]
    report["revisions"][0]["draft"]["reason"] = "<script>injection</script>"
    html = render_case_history(report)
    assert "<script>injection</script>" not in html and "&lt;script&gt;" in html
    assert "Observed financial result" in html and "Unavailable" in html
    assert "Simulated accept" in html
    with pytest.raises(ValueError, match="overwrite"):
        build_case_demo(underwriting, plan, underwriting)


def test_private_sources_rejected_before_revision_capture():
    raw = draft().model_dump(mode="json")
    raw["payload"]["underwriting"]["evidence"][1]["classification"] = "licensed_private"
    with pytest.raises(ValueError, match="private"):
        RevisionDraft.model_validate(raw)


def test_case_history_reads_work_with_a_single_database_connection(pg_repo, pg_database):
    from pe_value_os.adapters.postgres import PostgresRepository

    single = PostgresRepository(pg_database[1], pg_repo.evidence_store, min_size=1, max_size=1)
    single.pool.timeout = 0.5
    try:
        with security.principal_scope(principal()):
            case = setup(single)
            revision = single.append_case_revision(case.case_id, None, draft())
            receipt = single.review_case_revision(revision.revision_id, request(revision))
            assert single.list_case_revisions(case.case_id) == [revision]
            assert single.list_case_reviews(case.case_id) == [receipt]
    finally:
        single.close()


def test_downgrade_guard_sees_history_for_non_superuser_owner(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import downgrade

    with security.principal_scope(principal()):
        case = setup(pg_repo)
        original = pg_repo.append_case_revision(case.case_id, None, draft())
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='investment_cases'::regclass"
        ).fetchone()[0]
        conn.execute("alter table investment_cases owner to pvc_migrator")
        conn.execute("grant select,update on alembic_version to pvc_migrator")
        try:
            with psycopg.connect(owner_url) as as_owner:
                assert as_owner.execute("select current_user").fetchone()[0] == "pvc_migrator"
                assert (
                    as_owner.execute("select count(*) from investment_cases").fetchone()[0] == 0
                )  # FORCE RLS hides it.
            with pytest.raises(RuntimeError, match="Case history exists"):
                downgrade(owner_url, "0003")
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='investment_cases'::regclass"
            ).fetchone()[0]
            with security.principal_scope(principal()):
                assert pg_repo.get_case_revision(original.revision_id) == original
        finally:
            conn.execute(sql.SQL("alter table investment_cases owner to {}").format(sql.Identifier(owner)))
