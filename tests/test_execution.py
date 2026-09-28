"""Delivery acceptance stays distinct from authorization and attributed value."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import digest
from pe_value_os.diligence.execution import ExecutionEvent, ExecutionRequest

from .test_case_revisions import principal
from .test_case_revisions import request as review_request
from .test_realization import claim, observation_request, ready, revised


def binding(event):
    return {"event_id": event.event_id, "sha256": event.content_sha256}


def event_request(baseline, payload, *, key, day="2026-10-01", previous=None):
    content = (
        "Constructed execution support for " + key + "; no company activity or actual staff identity is represented."
    )
    return ExecutionRequest(
        baseline_id=baseline.baseline_id,
        baseline_sha256=baseline.content_sha256,
        mode=baseline.request.mode,
        ingestion_key=key,
        effective_on=day,
        payload=payload,
        evidence=[
            dict(
                evidence_id=key,
                classification="constructed_execution_evidence",
                content=content,
                sha256=digest(content),
            )
        ],
        rationale="Explicit constructed receipt for " + key,
        expected_previous_id=previous,
    )


def assign(repo, case, baseline, resource="finance", operator=None):
    prefix = "human:" if baseline.request.mode == "human" else "simulated:"
    return repo.record_execution_event(
        case.case_id,
        event_request(
            baseline,
            dict(
                kind="assignment",
                resource_id=resource,
                status="assigned",
                operator_subject=operator or prefix + resource,
                sponsor_subject=prefix + "sponsor",
            ),
            key="assign-" + resource,
        ),
    )


def complete(repo, case, baseline, assignment, task, *, start="2026-10-02", end="2026-10-03", deps=(), key=None):
    key = key or task
    delivery = repo.record_execution_event(
        case.case_id,
        event_request(
            baseline,
            dict(
                kind="delivery",
                task_id=task,
                assignment=binding(assignment),
                state="completed",
                started_on=start,
                completed_on=end,
            ),
            key=key + "-delivery",
            day=end,
        ),
    )
    accepted = repo.record_execution_event(
        case.case_id,
        event_request(
            baseline,
            dict(
                kind="acceptance",
                task_id=task,
                delivery=binding(delivery),
                decision="accept",
                prerequisite_acceptances=[binding(e) for e in deps],
            ),
            key=key + "-accept",
            day=end,
        ),
    )
    return delivery, accepted


def service_chain(repo, case, baseline):
    finance = assign(repo, case, baseline)
    _, foundation = complete(repo, case, baseline, finance, "foundation")
    operator = assign(repo, case, baseline, "service")
    _, trial = complete(
        repo, case, baseline, operator, "service-trial", start="2026-10-04", end="2026-10-10", deps=[foundation]
    )
    delivery, gate = complete(
        repo, case, baseline, operator, "service-gate", start="2026-10-11", end="2026-10-20", deps=[trial]
    )
    return foundation, trial, delivery, gate


def service_claim(repo, case, baseline, close):
    def november(raw):
        for name in ("observed", "counterfactual"):
            raw[name].update(start="2026-11-01", end="2026-11-30")
        raw["observed"]["rows"][1]["amount"] = "-58000"
        raw["observed"]["controls"].update(operating_expense="-58000", ebitda="50000")

    obs = repo.record_case_observation(
        case.case_id, observation_request(case, baseline, close, key="november", changes=november)
    )
    raw = claim(obs).model_dump(mode="json")
    raw["allocations"][0].update(row_id="operating_expense", initiative_id="service-automation", amount="2000")
    attribution = repo.record_case_attribution(case.case_id, type(claim(obs)).model_validate(raw))
    return obs, attribution


def link_request(baseline, attribution, gate, *, key="link", day="2026-11-30", previous=None):
    return event_request(
        baseline,
        dict(
            kind="claim_link",
            attribution_id=attribution.attribution_id,
            attribution_sha256=attribution.content_sha256,
            row_id="operating_expense",
            initiative_id="service-automation",
            acceptance=binding(gate),
        ),
        key=key,
        day=day,
        previous=previous,
    )


def test_missing_assignment_completion_and_acceptance_are_separate(repo):
    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(repo)
        initial = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert all(t["assignment"] is None and not t["acceptance_valid"] for t in initial["tasks"])
        finance = assign(repo, case, baseline)
        delivery = repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(
                    kind="delivery",
                    task_id="foundation",
                    assignment=binding(finance),
                    state="completed",
                    started_on="2026-10-02",
                    completed_on="2026-10-03",
                ),
                key="foundation-delivery",
                day="2026-10-03",
            ),
        )
        view = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        foundation = next(t for t in view["tasks"] if t["task_id"] == "foundation")
        assert foundation["delivery"]["request"]["payload"]["state"] == "completed"
        assert not foundation["acceptance_valid"]
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="acceptance", task_id="foundation", delivery=binding(delivery), decision="accept"),
                key="review",
                day="2026-10-04",
            ),
        )
        assert repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))["tasks"][0][
            "acceptance_valid"
        ]
        assert repo.list_kpi_definitions("exercise") == []
        assert view["actual_company_execution"] is view["actual_company_realized_value"] is None


def test_supported_claim_links_require_gate_and_proceed_without_certifying_value(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        _, a = service_claim(repo, case, baseline, close)
        before = repo.case_realization(case.case_id, baseline.baseline_id)
        with pytest.raises(ValueError, match="proceed"):
            repo.record_execution_event(case.case_id, link_request(baseline, a, gate))
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        linked = repo.record_execution_event(case.case_id, link_request(baseline, a, gate))
        report = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert report["claim_links"][0]["event_id"] == linked.event_id
        assert (
            report["claim_links"][0]["delivery_support_valid"] and not report["claim_links"][0]["causality_validated"]
        )
        assert repo.case_realization(case.case_id, baseline.baseline_id) == before


def test_withdrawn_prerequisite_invalidates_downstream_gate_and_link_but_retains_records(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        foundation, _, _, gate = service_chain(repo, case, baseline)
        _, a = service_claim(repo, case, baseline, close)
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        repo.record_execution_event(case.case_id, link_request(baseline, a, gate))
        repo.record_execution_event(
            case.case_id,
            revised(
                foundation.request,
                ingestion_key="withdraw",
                expected_previous_id=foundation.event_id,
                effective_on="2026-12-01",
                payload={**foundation.request.payload.model_dump(mode="json"), "decision": "withdraw"},
            ),
        )
        report = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert not next(i for i in report["initiatives"] if i["initiative_id"] == "service-automation")[
            "gate_acceptance_valid"
        ]
        assert not report["claim_links"][0]["delivery_support_valid"]
        assert "superseded" in report["claim_links"][0]["limitation"]
        assert any(e["event_id"] == foundation.event_id for e in report["events"])


@pytest.mark.parametrize("change", ["delivery", "attribution", "observation", "baseline"])
def test_corrected_support_invalidates_link_without_erasing_financials(repo, change):
    with security.principal_scope(principal()):
        case, close, review, baseline, _ = ready(repo)
        _, _, delivery, gate = service_chain(repo, case, baseline)
        obs, a = service_claim(repo, case, baseline, close)
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        repo.record_execution_event(case.case_id, link_request(baseline, a, gate))
        if change == "delivery":
            repo.record_execution_event(
                case.case_id,
                revised(
                    delivery.request,
                    ingestion_key="delivery-correction",
                    expected_previous_id=delivery.event_id,
                    effective_on="2026-12-01",
                    payload={
                        **delivery.request.payload.model_dump(mode="json"),
                        "state": "blocked",
                        "completed_on": None,
                    },
                ),
            )
        elif change == "attribution":
            repo.record_case_attribution(
                case.case_id,
                revised(
                    a.request,
                    ingestion_key="claim-withdraw",
                    expected_previous_id=a.attribution_id,
                    allocations=[],
                    evidence=[],
                ),
            )
        elif change == "observation":
            repo.record_case_observation(
                case.case_id,
                revised(
                    obs.request,
                    ingestion_key="source-correction",
                    expected_previous_id=obs.observation_id,
                    reason="Restated source",
                ),
            )
        else:
            repo.review_case_revision(
                close.revision_id, review_request(close, decision="withdraw", previous=review.review_id)
            )
        report = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert not report["claim_links"][0]["delivery_support_valid"]
        assert len(repo.list_case_observations(case.case_id)) >= 1
        assert repo.list_case_attributions(case.case_id)[0] == a


def test_hold_within_month_blocks_support_and_later_hold_does_not_erase_prior_month(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        _, a = service_claim(repo, case, baseline, close)
        go = repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        hold = repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="hold"),
                key="hold",
                day="2026-11-15",
                previous=go.event_id,
            ),
        )
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="resume",
                day="2026-11-20",
                previous=hold.event_id,
            ),
        )
        with pytest.raises(ValueError, match="whole observation month"):
            repo.record_execution_event(case.case_id, link_request(baseline, a, gate))


def test_later_hold_retains_prior_whole_month_support(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        _, a = service_claim(repo, case, baseline, close)
        go = repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        repo.record_execution_event(case.case_id, link_request(baseline, a, gate))
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="hold"),
                key="hold",
                day="2026-12-01",
                previous=go.event_id,
            ),
        )
        report = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert report["claim_links"][0]["delivery_support_valid"]
        assert (
            next(i for i in report["initiatives"] if i["initiative_id"] == "service-automation")["steering_decision"]
            == "hold"
        )


@pytest.mark.parametrize("bad", ["missing_prerequisite", "wrong_task", "hash", "before_start", "assignment", "mode"])
def test_invalid_execution_bindings_leave_no_record_or_audit(repo, bad):
    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(repo)
        operator = assign(repo, case, baseline, "service")
        delivery = repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(
                    kind="delivery",
                    task_id="service-trial",
                    assignment=binding(operator),
                    state="completed",
                    started_on="2026-10-02",
                    completed_on="2026-10-03",
                ),
                key="delivery",
                day="2026-10-03",
            ),
        )
        req = event_request(
            baseline,
            dict(kind="acceptance", task_id="service-trial", delivery=binding(delivery), decision="accept"),
            key="review",
            day="2026-10-04",
        )
        raw = req.model_dump(mode="json")
        if bad == "wrong_task":
            raw["payload"]["task_id"] = "foundation"
        elif bad == "hash":
            raw["payload"]["delivery"]["sha256"] = "0" * 64
        elif bad == "before_start":
            raw["effective_on"] = "2026-09-01"
        elif bad == "assignment":
            raw["payload"] = {
                "kind": "assignment",
                "resource_id": "unknown",
                "status": "assigned",
                "operator_subject": "simulated:operator",
                "sponsor_subject": "simulated:sponsor",
            }
        elif bad == "mode":
            raw["mode"] = "human"
        count = len(repo.list_audit(company_id="exercise"))
        with pytest.raises((ValueError, security.ScopeError)):
            repo.record_execution_event(case.case_id, ExecutionRequest.model_validate(raw))
        assert len(repo.list_audit(company_id="exercise")) == count


def test_idempotency_concurrent_heads_scope_atomicity_and_retention(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(repo)
        assignment = assign(repo, case, baseline)
        audit = len(repo.list_audit(company_id="exercise"))
        assert repo.record_execution_event(case.case_id, assignment.request) == assignment
        assert len(repo.list_audit(company_id="exercise")) == audit
        with pytest.raises(Conflict):
            repo.record_execution_event(case.case_id, revised(assignment.request, rationale="changed"))
        req = event_request(
            baseline,
            dict(kind="assignment", resource_id="finance", status="withdrawn"),
            key="withdraw",
            day="2026-10-02",
            previous=assignment.event_id,
        )
        append = repo.append_audit
        monkeypatch.setattr(repo, "append_audit", lambda _: (_ for _ in ()).throw(RuntimeError("audit failed")))
        with pytest.raises(RuntimeError):
            repo.record_execution_event(case.case_id, req)
        assert repo.list_execution_events(case.case_id) == [assignment]
        monkeypatch.setattr(repo, "append_audit", append)

    def record(index):
        with security.principal_scope(principal()):
            try:
                return repo.record_execution_event(case.case_id, revised(req, ingestion_key="withdraw-" + str(index)))
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(record, range(2)))
    assert sum(e is not None for e in outcomes) == 1
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            repo.list_execution_events(case.case_id)
        with pytest.raises(NotFound):
            repo.record_execution_event(case.case_id, req)
        with pytest.raises(NotFound):
            repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
    with security.principal_scope(principal()):
        raw = assignment.model_dump(mode="json")
        raw["actor"] = "invented"
        with pytest.raises(ValueError, match="hash"):
            ExecutionEvent.model_validate(raw)
        assert repo.delete_company_data("exercise")["case_execution_events"] == 2


def test_human_delivery_requires_named_operator_and_separate_human_acceptance(repo):
    with security.principal_scope(principal(kind="human", subject="human:sponsor")):
        case, _, _, baseline, _ = ready(repo, mode="human")
        assignment = assign(repo, case, baseline, operator="human:operator")
    req = event_request(
        baseline,
        dict(
            kind="delivery",
            task_id="foundation",
            assignment=binding(assignment),
            state="completed",
            started_on="2026-10-02",
            completed_on="2026-10-03",
        ),
        key="delivery",
        day="2026-10-03",
    )
    with security.principal_scope(principal()):
        with pytest.raises(security.ScopeError):
            repo.record_execution_event(case.case_id, req)
    with security.principal_scope(principal(kind="human", subject="human:other")):
        with pytest.raises(security.ScopeError):
            repo.record_execution_event(case.case_id, req)
    with security.principal_scope(principal(kind="human", subject="human:operator")):
        delivery = repo.record_execution_event(case.case_id, req)
        acceptance = event_request(
            baseline,
            dict(kind="acceptance", task_id="foundation", delivery=binding(delivery), decision="accept"),
            key="accept",
            day="2026-10-04",
        )
        with pytest.raises(security.ScopeError):
            repo.record_execution_event(case.case_id, acceptance)
    with security.principal_scope(principal(kind="human", subject="human:reviewer")):
        assert repo.record_execution_event(case.case_id, acceptance).actor == "human:reviewer"


def test_forced_rls_immutability_and_populated_downgrade_guard(pg_repo, pg_database):
    import psycopg

    from pe_value_os.db.migrate import current, downgrade

    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(pg_repo)
        assign(pg_repo, case, baseline)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from case_execution_events").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies','exercise',false)")
        assert conn.execute("select count(*) from case_execution_events").fetchone()[0] == 1
        for statement in ("update case_execution_events set sequence=99", "delete from case_execution_events"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    with pytest.raises(RuntimeError, match="Execution history"):
        downgrade(pg_database[0], "0006")
    assert current(pg_database[0]) == "0007"


def test_link_withdrawal_is_explicit_and_does_not_remove_the_claim(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        _, attribution = service_claim(repo, case, baseline, close)
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="steering", initiative_id="service-automation", decision="proceed"),
                key="go",
                day="2026-10-21",
            ),
        )
        link = repo.record_execution_event(case.case_id, link_request(baseline, attribution, gate))
        repo.record_execution_event(
            case.case_id,
            revised(
                link.request,
                ingestion_key="link-withdraw",
                expected_previous_id=link.event_id,
                effective_on="2026-12-01",
                payload={**link.request.payload.model_dump(mode="json"), "status": "withdrawn"},
            ),
        )
        view = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert not view["claim_links"][0]["delivery_support_valid"]
        assert "explicitly withdrawn" in view["claim_links"][0]["limitation"]
        assert view["claim_coverage"][0]["status"] == "delivery_support_invalidated"
        assert repo.list_case_attributions(case.case_id) == [attribution]


def test_assignment_change_preserves_completed_history_but_cannot_span_unassigned_work(repo):
    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(repo)
        assignment = assign(repo, case, baseline)
        _, accepted = complete(repo, case, baseline, assignment, "foundation")
        repo.record_execution_event(
            case.case_id,
            event_request(
                baseline,
                dict(kind="assignment", resource_id="finance", status="withdrawn"),
                key="withdraw-operator",
                day="2026-10-05",
                previous=assignment.event_id,
            ),
        )
        view = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        task = next(t for t in view["tasks"] if t["task_id"] == "foundation")
        assert task["acceptance_valid"] and task["assignment"]["request"]["payload"]["status"] == "withdrawn"
        delivery = event_request(
            baseline,
            dict(
                kind="delivery",
                task_id="collections-review",
                assignment=binding(assignment),
                state="completed",
                started_on="2026-10-04",
                completed_on="2026-10-06",
            ),
            key="spans-withdrawal",
            day="2026-10-06",
        )
        with pytest.raises(ValueError, match="cover the reported work interval"):
            repo.record_execution_event(case.case_id, delivery)
        assert repo.list_execution_events(case.case_id)[2] == accepted


def test_early_and_adverse_claims_cannot_be_promoted_by_a_gate(repo):
    with security.principal_scope(principal()):
        case, _close, _, baseline, req = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        obs = repo.record_case_observation(case.case_id, req)
        raw = claim(obs).model_dump(mode="json")
        raw["allocations"][0].update(row_id="operating_expense", initiative_id="service-automation", amount="-1000")
        attribution = repo.record_case_attribution(case.case_id, type(claim(obs)).model_validate(raw))
        with pytest.raises(ValueError, match="positive benefit claim"):
            repo.record_execution_event(case.case_id, link_request(baseline, attribution, gate, day="2026-10-31"))
        report = repo.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))
        assert report["claim_coverage"][0]["status"] == "adverse_or_cost_claim"
        assert (
            repo.case_realization(case.case_id, baseline.baseline_id)["aggregate_recorded_periods"][
                "attributed_difference"
            ]["incremental_ebitda"]
            == -1000
        )


def test_execution_api_requires_explicit_bearer_and_exercise_date(repo, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setenv(
        "PVC_DEV_TOKENS",
        json.dumps(
            {
                name: dict(sub="service:" + name, pvc_companies=[company], pvc_principal_type="service", scope=scopes)
                for name, company, scopes in [
                    ("writer", "exercise", "pvc.read pvc.write"),
                    ("reader", "exercise", "pvc.read"),
                    ("outsider", "elsewhere", "pvc.read pvc.write"),
                ]
            }
        ),
    )
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(repo)
    payload = event_request(
        baseline,
        dict(
            kind="assignment",
            resource_id="finance",
            status="assigned",
            operator_subject="simulated:finance",
            sponsor_subject="simulated:sponsor",
        ),
        key="api-assignment",
    ).model_dump(mode="json")
    client = TestClient(api.app)
    path = f"/cases/{case.case_id}/execution-events"
    assert client.post(path, json=payload).status_code == 401
    client.cookies.set("pvc_dev_session", "writer")
    assert client.post(path, json=payload).status_code == 403
    for name in ("reader", "outsider"):
        assert client.post(path, json=payload, headers={"Authorization": "Bearer " + name}).status_code == 404
    headers = {"Authorization": "Bearer writer"}
    assert client.post(path, json={**payload, "actor": "human:invented"}, headers=headers).status_code == 422
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    assert client.post(path, json=payload, headers=headers).json() == response.json()
    view = f"/cases/{case.case_id}/execution/{baseline.baseline_id}"
    assert client.get(view, headers=headers).status_code == 422
    assert (
        client.get(view, params={"as_of": "2026-12-31"}, headers={"Authorization": "Bearer reader"}).status_code == 200
    )
    assert (
        client.get(view, params={"as_of": "2026-12-31"}, headers={"Authorization": "Bearer outsider"}).status_code
        == 404
    )


def test_rehearsal_retains_adverse_challenges_and_five_month_comparison(tmp_path):
    from pathlib import Path

    from pe_value_os.diligence.execution_demo import build_execution_demo

    base = Path("data/constructed/progress")
    output = tmp_path / "custom-execution"
    html = build_execution_demo(
        base / "underwriting.json",
        base / "operating-plan.json",
        base / "realization.json",
        base / "execution.json",
        output,
    )
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    view = report["execution"]["final"]
    assert sum(t["acceptance_valid"] for t in view["tasks"]) == 6
    assert [c["delivery_support_valid"] for c in view["claim_links"]] == [True, True, False]
    assert len([c for c in report["execution"]["checkpoints"] if c["result"] == "rejected"]) == 3
    dates = [c["effective_on"] for c in report["execution"]["checkpoints"]]
    assert dates == sorted(dates)
    assert report["submitted_periods"] == 5
    assert report["aggregate_recorded_periods"]["measured_difference"] == {
        "incremental_ebitda": "61000",
        "pre_tax_cash_proxy": "185000",
    }
    assert report["actual_company_realized_value"] is view["actual_company_execution"] is None
    assert "custom-execution.json" in html.read_text(encoding="utf-8")
    assert report["human_review_count"] == 0


def test_database_enforces_baseline_mode_and_guard_sees_unscoped_owner(pg_repo, pg_database):
    import uuid
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import downgrade

    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(pg_repo)
        assignment = assign(pg_repo, case, baseline)
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        conn.execute("select set_config('pvc.companies','exercise',false)")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                """insert into case_execution_events(event_id,company_id,case_id,baseline_id,baseline_sha256,mode,kind,stream_key,sequence,ingestion_key,actor_type,effective_on,content_sha256,recorded_at,record)
            select %s,company_id,case_id,baseline_id,baseline_sha256,'human',kind,%s,1,'wrong-mode','human',effective_on,content_sha256,recorded_at,record from case_execution_events where event_id=%s""",
                (str(uuid.uuid4()), "f" * 64, assignment.event_id),
            )
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='case_execution_events'::regclass"
        ).fetchone()[0]
        conn.execute("alter table case_execution_events owner to pvc_migrator")
        conn.execute("grant select,update on alembic_version to pvc_migrator")
        try:
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from case_execution_events").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Execution history"):
                downgrade(owner_url, "0006")
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='case_execution_events'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table case_execution_events owner to {}").format(sql.Identifier(owner)))


def test_readonly_database_role_reads_execution(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    from pe_value_os.adapters.postgres import PostgresRepository

    with security.principal_scope(principal()):
        case, _, _, baseline, _ = ready(pg_repo)
        assign(pg_repo, case, baseline)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_readonly"
    reader = PostgresRepository(
        urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment)),
        pg_repo.evidence_store,
        max_size=1,
    )
    try:
        with security.principal_scope(principal(scopes=frozenset({"pvc.read"}))):
            assert len(reader.case_execution(case.case_id, baseline.baseline_id, date(2026, 12, 31))["events"]) == 1
    finally:
        reader.close()


def test_request_for_changes_cannot_support_a_financial_claim(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, _ = ready(repo)
        _, _, _, gate = service_chain(repo, case, baseline)
        _, attribution = service_claim(repo, case, baseline, close)
        changes = repo.record_execution_event(
            case.case_id,
            revised(
                gate.request,
                ingestion_key="request-changes",
                expected_previous_id=gate.event_id,
                effective_on="2026-10-21",
                payload={**gate.request.payload.model_dump(mode="json"), "decision": "request_changes"},
            ),
        )
        with pytest.raises(ValueError, match="task has no accepted receipt"):
            repo.record_execution_event(case.case_id, link_request(baseline, attribution, changes))
