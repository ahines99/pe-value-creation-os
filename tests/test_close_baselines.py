"""Frozen review-bound comparisons, authority separation, correction and persistence."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.close_baseline import CloseBaseline, CloseBaselineRequest, close_baseline_view

from .test_case_revisions import draft, principal, request, setup


def prepared(repo, mode="simulation"):
    case = setup(repo)
    original = repo.append_case_revision(case.case_id, None, draft())
    close = repo.append_case_revision(
        case.case_id, original.revision_id, draft(scheduled=True, stage="close_validation")
    )
    review = repo.review_case_revision(close.revision_id, request(close, mode=mode))
    req = CloseBaselineRequest(
        revision_id=close.revision_id,
        revision_sha256=close.content_sha256,
        review_id=review.review_id,
        mode=mode,
        scenario_id="base",
        rationale="Freeze the reviewed hypothetical close for comparison",
    )
    return case, close, review, req


def test_original_baseline_survives_reforecast_and_replay(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, close, _review, req = prepared(repo)
        baseline = repo.designate_close_baseline(case.case_id, req)
        frozen = baseline.model_dump_json()
        repo.append_case_revision(case.case_id, close.revision_id, draft(scheduled=True, stage="ownership_review"))
        monkeypatch.setattr("pe_value_os.diligence.cases.evaluate_plan", lambda *_: pytest.fail("must not recalculate"))
        result = close_baseline_view(
            baseline, close, repo.list_case_reviews(case.case_id), repo.list_close_baselines(case.case_id)
        )
        assert result["usable_for_comparison"] and result["current_designation"]
        assert result["frozen_forecast"] == next(
            s for s in json.loads(close.financial_result_json)["scenarios"] if s["scenario_id"] == "base"
        )
        assert repo.list_close_baselines(case.case_id)[0].model_dump_json() == frozen
        assert not repo.list_kpi_definitions("exercise")
        assert repo.list_audit(company_id="exercise")[-2].event_type == "close_baseline_designated"


def test_withdrawn_support_invalidates_comparison_without_erasing_baseline(repo):
    with security.principal_scope(principal()):
        case, close, review, req = prepared(repo)
        baseline = repo.designate_close_baseline(case.case_id, req)
        repo.append_case_revision(case.case_id, close.revision_id, draft(stage="ownership_review"))
        repo.review_case_revision(close.revision_id, request(close, decision="withdraw", previous=review.review_id))
        view = close_baseline_view(baseline, close, repo.list_case_reviews(case.case_id), [baseline])
        assert view["current_designation"] and not view["usable_for_comparison"]
        assert view["supporting_review_status"] == "invalidated_or_missing"
        assert repo.list_close_baselines(case.case_id) == [baseline]


@pytest.mark.parametrize("mutation", ["hash", "scenario", "mode", "review", "stage", "superseded"])
def test_invalid_designations_leave_no_baseline_or_audit(repo, mutation):
    with security.principal_scope(principal()):
        case, close, review, req = prepared(repo)
        raw = req.model_dump(mode="json")
        if mutation == "hash":
            raw["revision_sha256"] = "0" * 64
        elif mutation == "scenario":
            raw["scenario_id"] = "missing"
        elif mutation == "mode":
            raw["mode"] = "human"
        elif mutation == "review":
            raw["review_id"] = close.revision_id
        elif mutation == "stage":
            wrong = repo.append_case_revision(
                case.case_id, close.revision_id, draft(scheduled=True, stage="ownership_review")
            )
            receipt = repo.review_case_revision(wrong.revision_id, request(wrong))
            raw.update(revision_id=wrong.revision_id, revision_sha256=wrong.content_sha256, review_id=receipt.review_id)
        else:
            repo.review_case_revision(close.revision_id, request(close, decision="reject", previous=review.review_id))
        before = len(repo.list_audit(company_id="exercise"))
        with pytest.raises((ValueError, security.ScopeError)):
            repo.designate_close_baseline(case.case_id, CloseBaselineRequest.model_validate(raw))
        assert repo.list_close_baselines(case.case_id) == []
        assert len(repo.list_audit(company_id="exercise")) == before


def test_modes_are_separate_and_service_cannot_designate_human_acceptance(repo):
    with security.principal_scope(principal(kind="human")):
        case, close, _review, req = prepared(repo, "human")
    with security.principal_scope(principal()):
        with pytest.raises(security.ScopeError):
            repo.designate_close_baseline(case.case_id, req)
        simulated_review = repo.review_case_revision(close.revision_id, request(close))
        simulation = CloseBaselineRequest.model_validate(
            {**req.model_dump(mode="json"), "mode": "simulation", "review_id": simulated_review.review_id}
        )
        b = repo.designate_close_baseline(case.case_id, simulation)
    with security.principal_scope(principal(kind="human")):
        human = repo.designate_close_baseline(case.case_id, req)
        assert b.request.mode == "simulation" and human.request.mode == "human"
        assert len(repo.list_close_baselines(case.case_id)) == 2


def test_explicit_replacement_preserves_original_and_rejects_stale_writer(repo):
    with security.principal_scope(principal()):
        case, close, review, req = prepared(repo)
        first = repo.designate_close_baseline(case.case_id, req)
        with pytest.raises(Conflict):
            repo.designate_close_baseline(case.case_id, req)
        replacement = CloseBaselineRequest.model_validate(
            {
                **req.model_dump(mode="json"),
                "expected_previous_id": first.baseline_id,
                "scenario_id": "downside",
                "rationale": "Explicit adverse scenario reset",
            }
        )
        second = repo.designate_close_baseline(case.case_id, replacement)
        with pytest.raises(Conflict):
            repo.designate_close_baseline(case.case_id, replacement)
        all_records = repo.list_close_baselines(case.case_id)
        assert all_records == [first, second] and second.sequence == 2
        assert not close_baseline_view(first, close, [review], all_records)["current_designation"]
        assert close_baseline_view(first, close, [review], all_records)["usable_for_comparison"]
        assert close_baseline_view(second, close, [review], all_records)["usable_for_comparison"]


def test_simultaneous_designations_have_one_winner(repo):
    with security.principal_scope(principal()):
        case, _close, _review, req = prepared(repo)

    def create():
        with security.principal_scope(principal()):
            try:
                return repo.designate_close_baseline(case.case_id, req)
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sum(r is not None for r in results) == 1


def test_scope_audit_rollback_and_retention(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, _close, _review, req = prepared(repo)
        original_audit = repo.append_audit
        monkeypatch.setattr(repo, "append_audit", lambda _: (_ for _ in ()).throw(RuntimeError("audit failed")))
        with pytest.raises(RuntimeError, match="audit failed"):
            repo.designate_close_baseline(case.case_id, req)
        assert repo.list_close_baselines(case.case_id) == []
        monkeypatch.setattr(repo, "append_audit", original_audit)
        b = repo.designate_close_baseline(case.case_id, req)
        raw = b.model_dump(mode="json")
        raw["request"]["scenario_id"] = "upside"
        with pytest.raises(ValueError, match="hash"):
            CloseBaseline.model_validate(raw)
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            repo.list_close_baselines(case.case_id)
        with pytest.raises(NotFound):
            repo.designate_close_baseline(case.case_id, req)
    with security.principal_scope(principal()):
        assert repo.delete_company_data("exercise")["case_close_baselines"] == 1


def test_postgres_baselines_are_forced_rls_immutable_and_downgrade_protected(pg_repo, pg_database):
    import psycopg

    from pe_value_os.db.migrate import current, downgrade, upgrade

    with security.principal_scope(principal()):
        case, _close, _review, req = prepared(pg_repo)
        b = pg_repo.designate_close_baseline(case.case_id, req)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from case_close_baselines").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies','exercise',false)")
        assert conn.execute("select count(*) from case_close_baselines").fetchone()[0] == 1
        for statement in (
            "update case_close_baselines set sequence=2 where baseline_id=%s",
            "delete from case_close_baselines where baseline_id=%s",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement, (b.baseline_id,))
    try:
        with pytest.raises(RuntimeError, match="Close baseline history"):
            downgrade(pg_database[0], "0004")
        assert current(pg_database[0]) == "0005"
    finally:
        upgrade(pg_database[0])


def test_baseline_downgrade_guard_sees_history_hidden_from_its_owner(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import downgrade, upgrade

    downgrade(pg_database[0], "0005")

    with security.principal_scope(principal()):
        case, _close, _review, req = prepared(pg_repo)
        baseline = pg_repo.designate_close_baseline(case.case_id, req)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='case_close_baselines'::regclass"
        ).fetchone()[0]
        conn.execute("alter table case_close_baselines owner to pvc_migrator")
        conn.execute("grant select,update on alembic_version to pvc_migrator")
        try:
            with psycopg.connect(owner_url) as scoped_owner:
                assert scoped_owner.execute("select count(*) from case_close_baselines").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Close baseline history"):
                downgrade(owner_url, "0004")
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='case_close_baselines'::regclass"
            ).fetchone()[0]
            with security.principal_scope(principal()):
                assert pg_repo.list_close_baselines(case.case_id) == [baseline]
        finally:
            conn.execute(sql.SQL("alter table case_close_baselines owner to {}").format(sql.Identifier(owner)))
            upgrade(pg_database[0])


def test_api_keeps_bearer_scope_binding_and_invalidated_review_visible(repo, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setenv(
        "PVC_DEV_TOKENS",
        json.dumps(
            {
                "writer": {
                    "sub": "service:test",
                    "pvc_companies": ["exercise"],
                    "pvc_principal_type": "service",
                    "scope": "pvc.read pvc.write",
                },
                "reader": {
                    "sub": "service:reader",
                    "pvc_companies": ["exercise"],
                    "pvc_principal_type": "service",
                    "scope": "pvc.read",
                },
                "outsider": {
                    "sub": "service:other",
                    "pvc_companies": ["other"],
                    "pvc_principal_type": "service",
                    "scope": "pvc.read pvc.write",
                },
            }
        ),
    )
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with security.principal_scope(principal()):
        case, close, review, req = prepared(repo)
    client = TestClient(api.app)
    path = f"/cases/{case.case_id}/close-baselines"
    payload = req.model_dump(mode="json")
    assert client.post(path, json=payload).status_code == 401
    client.cookies.set("pvc_dev_session", "writer")
    assert client.post(path, json=payload).status_code == 403
    assert client.post(path, json=payload, headers={"Authorization": "Bearer reader"}).status_code == 404
    assert client.post(path, json=payload, headers={"Authorization": "Bearer outsider"}).status_code == 404
    h = {"Authorization": "Bearer writer"}
    assert client.post(path, json={**payload, "actor": "human:invented"}, headers=h).status_code == 422
    response = client.post(path, json=payload, headers=h)
    assert response.status_code == 201, response.text
    assert client.post(path, json=payload, headers=h).status_code == 409
    history = client.get(f"/cases/{case.case_id}", headers=h).json()
    assert history["close_baselines"][0]["usable_for_comparison"]
    assert history["comparison"]["actuals"] is None
    with security.principal_scope(principal()):
        repo.review_case_revision(close.revision_id, request(close, decision="withdraw", previous=review.review_id))
    assert not client.get(f"/cases/{case.case_id}", headers=h).json()["close_baselines"][0]["usable_for_comparison"]


def test_unconfirmed_capacity_blocks_designation_even_after_simulated_accept(repo):
    from pe_value_os.diligence.cases import RevisionDraft

    with security.principal_scope(principal()):
        case = setup(repo)
        original = repo.append_case_revision(case.case_id, None, draft())
        raw = draft(scheduled=True, stage="close_validation").model_dump(mode="json")
        raw["payload"]["operating_plan"]["resources"][0]["weekly_hours"] = [None] * 15
        blocked = repo.append_case_revision(case.case_id, original.revision_id, RevisionDraft.model_validate(raw))
        review = repo.review_case_revision(blocked.revision_id, request(blocked))
        req = CloseBaselineRequest(
            revision_id=blocked.revision_id,
            revision_sha256=blocked.content_sha256,
            review_id=review.review_id,
            mode="simulation",
            scenario_id="base",
            rationale="Invalid freeze attempt",
        )
        with pytest.raises(ValueError, match="blocked capacity"):
            repo.designate_close_baseline(case.case_id, req)
