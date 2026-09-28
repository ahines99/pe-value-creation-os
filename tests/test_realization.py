"""Ledger invariants tested through memory and restricted PostgreSQL repositories."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import digest
from pe_value_os.diligence.realization import (
    COMPONENTS,
    Attribution,
    AttributionRequest,
    Observation,
    ObservationRequest,
    SourceBook,
)
from pe_value_os.diligence.scheduling import fingerprint

from .test_case_revisions import draft, principal, request
from .test_close_baselines import prepared


def observation_request(case, baseline, close, *, key="oct-v1", previous=None, changes=None):
    common = dict(
        classification="constructed_operating_records",
        case_id=case.case_id,
        currency="USD",
        unit_scale=1,
        start="2026-10-01",
        end="2026-10-31",
        scope_explanation="All three constructed first-wave initiatives.",
        method_and_limits="Authored exercise totals, independent of the forecast. No company operating records.",
    )
    observed = [110000, -63000, -2000, 44000, 180000, -1500]
    counter = [100000, -60000, 0, 40000, 0, 0]

    def book(kind, amounts):
        rows = [
            dict(row_id=c, label=c.replace("_", " "), component=c, amount=str(v))
            for c, v in zip(COMPONENTS, amounts, strict=True)
        ]
        return SourceBook(
            **common,
            kind=kind,
            source_id=kind + "-oct",
            locator="authored:test",
            rows=rows,
            controls={**dict(zip(COMPONENTS, map(str, amounts), strict=True)), "ebitda": str(sum(amounts[:3]))},
        )

    a, b = book("observed", observed), book("no_intervention_counterfactual", counter)
    raw = dict(
        ingestion_key=key,
        baseline_id=baseline.baseline_id,
        baseline_sha256=baseline.content_sha256,
        observed=a.model_dump(mode="json"),
        counterfactual=b.model_dump(mode="json"),
        observed_sha256=fingerprint(a),
        counterfactual_sha256=fingerprint(b),
        initiative_ids=json.loads(close.financial_result_json)["selected_initiatives"],
        scope_mapping_rationale="Complete scoped accounting comparison; no whole-company attribution.",
        reason="Constructed monthly close",
        expected_previous_id=previous,
    )
    if changes:
        changes(raw)
        raw["observed_sha256"] = fingerprint(SourceBook.model_validate(raw["observed"]))
        raw["counterfactual_sha256"] = fingerprint(SourceBook.model_validate(raw["counterfactual"]))
    return ObservationRequest.model_validate(raw)


def claim(observation, *, key="claim-v1", previous=None, amount="6000", mode="simulation"):
    content = "Constructed cohort comparison assigns only part of the favorable revenue difference to pricing; volume and mix remain alternatives."
    return AttributionRequest(
        ingestion_key=key,
        observation_id=observation.observation_id,
        observation_sha256=observation.content_sha256,
        mode=mode,
        evidence=[
            dict(
                evidence_id="cohort",
                classification="constructed_attribution_evidence",
                content=content,
                sha256=digest(content),
            )
        ],
        allocations=[
            dict(
                row_id="revenue",
                initiative_id="pricing-renewals",
                amount=amount,
                evidence_ids=["cohort"],
                rationale="Authored partial contribution estimate",
                confidence="limited",
                alternative_explanation="Volume and mix",
            )
        ],
        rationale="Constructed claim, not an observed causal result",
        expected_previous_id=previous,
    )


def ready(repo, *, mode="simulation"):
    case, close, review, req = prepared(repo, mode)
    baseline = repo.designate_close_baseline(case.case_id, req)
    obs = observation_request(case, baseline, close)
    return case, close, review, baseline, obs


def revised(model, **changes):
    return type(model).model_validate({**model.model_dump(mode="json"), **changes})


def test_comparable_periods_residuals_and_cash_are_not_causal_earnings(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, req = ready(repo)
        o = repo.record_case_observation(case.case_id, req)
        report = repo.case_realization(case.case_id, baseline.baseline_id)
        first = report["periods"][0]
        assert first["status"] == "reconciled" and first["attribution_status"] == "unassigned"
        assert first["measured_difference"]["incremental_ebitda"] == Decimal("5000")
        assert first["measured_difference"]["pre_tax_cash_proxy"] == Decimal("182500")
        assert first["attributed_difference"]["incremental_ebitda"] == 0
        assert first["unassigned_residual"] == first["measured_difference"]
        assert report["periods"][1]["measured_difference"] is None
        assert report["submitted_periods"] == report["eligible_periods"] == 1
        assert report["actual_company_realized_value"] is report["day_100_actual"] is None
        attribution = repo.record_case_attribution(case.case_id, claim(o))
        repo.append_case_revision(case.case_id, close.revision_id, draft(stage="ownership_review"))
        report = repo.case_realization(case.case_id, baseline.baseline_id)
        totals = report["aggregate_recorded_periods"]
        assert totals["attributed_difference"]["incremental_ebitda"] == 6000
        assert totals["unassigned_residual"]["incremental_ebitda"] == -1000
        assert totals["attributed_difference"]["pre_tax_cash_proxy"] == 0
        assert totals["unassigned_residual"]["pre_tax_cash_proxy"] == 182500
        assert totals["close_forecast"] == {
            k: Decimal(report["periods"][0]["close_forecast"][k]) for k in ("incremental_ebitda", "pre_tax_cash_proxy")
        }
        assert report["periods"][0]["original_forecast"] == report["periods"][0]["current_forecast"]
        assert report["periods"][0]["attribution_id"] == attribution.attribution_id


def test_corrections_retain_history_require_new_claims_and_allow_withdrawal(repo):
    with security.principal_scope(principal()):
        case, close, _, b, req = ready(repo)
        o = repo.record_case_observation(case.case_id, req)
        a = repo.record_case_attribution(case.case_id, claim(o))

        def correct(raw):
            raw["observed"]["rows"][0]["amount"] = "108000"
            raw["observed"]["controls"].update(revenue="108000", ebitda="43000")

        o2 = repo.record_case_observation(
            case.case_id, observation_request(case, b, close, key="oct-v2", previous=o.observation_id, changes=correct)
        )
        view = repo.case_realization(case.case_id, b.baseline_id)
        assert len(view["observations"]) == 2 and len(view["attributions"]) == 1
        assert view["periods"][0]["attribution_status"] == "unassigned"
        assert view["aggregate_recorded_periods"]["measured_difference"]["incremental_ebitda"] == 3000
        with pytest.raises(Conflict, match="Corrected"):
            repo.record_case_attribution(case.case_id, claim(o, key="stale", previous=a.attribution_id))
        a2 = repo.record_case_attribution(case.case_id, claim(o2, key="new-snapshot"))
        withdrawal = revised(
            a2.request, ingestion_key="withdraw", expected_previous_id=a2.attribution_id, allocations=[], evidence=[]
        )
        a3 = repo.record_case_attribution(case.case_id, withdrawal)
        assert a3.sequence == 2
        assert repo.case_realization(case.case_id, b.baseline_id)["periods"][0]["attribution_status"] == "unassigned"
        assert repo.list_case_attributions(case.case_id) == [a, a2, a3]


@pytest.mark.parametrize("kind", ["observation", "attribution"])
def test_import_retries_are_idempotent_and_changed_keys_conflict(repo, kind):
    with security.principal_scope(principal()):
        case, _, _, _, req = ready(repo)
        if kind == "attribution":
            req = claim(repo.record_case_observation(case.case_id, req))
        record = getattr(repo, "record_case_" + kind)
        a = record(case.case_id, req)
        count = len(repo.list_audit(company_id="exercise"))
        assert record(case.case_id, req) == a
        assert len(repo.list_audit(company_id="exercise")) == count
        change = {"reason": "Changed request"} if kind == "observation" else {"rationale": "Changed request"}
        with pytest.raises(Conflict, match="Ingestion key"):
            record(case.case_id, revised(req, **change))
        with security.principal_scope(principal(subject="service:another")):
            with pytest.raises(Conflict):
                record(case.case_id, req)
        with pytest.raises(Conflict, match="changed"):
            record(case.case_id, revised(req, ingestion_key="same-period-new-key"))


@pytest.mark.parametrize("kind", ["observation", "attribution"])
def test_parallel_new_records_have_one_head(repo, kind):
    with security.principal_scope(principal()):
        case, _, _, _, req = ready(repo)
        if kind == "attribution":
            req = claim(repo.record_case_observation(case.case_id, req))

    def run(index):
        with security.principal_scope(principal()):
            try:
                return getattr(repo, "record_case_" + kind)(
                    case.case_id, revised(req, ingestion_key=f"concurrent-{index}")
                )
            except Conflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, range(2)))
    assert sum(o is not None for o in outcomes) == 1


@pytest.mark.parametrize("mutation", ["over", "sign", "row", "initiative", "hash", "mode", "overlap"])
def test_bad_claims_cannot_overstate_or_cross_source_bindings(repo, mutation):
    with security.principal_scope(principal()):
        case, _, _, _, req = ready(repo)
        o = repo.record_case_observation(case.case_id, req)
        raw = claim(o).model_dump(mode="json")
        if mutation == "over":
            raw["allocations"][0]["amount"] = "10000.01"
        elif mutation == "sign":
            raw["allocations"][0]["amount"] = "-1"
        elif mutation == "row":
            raw["allocations"][0]["row_id"] = "absent"
        elif mutation == "initiative":
            raw["allocations"][0]["initiative_id"] = "absent"
        elif mutation == "hash":
            raw["observation_sha256"] = "0" * 64
        elif mutation == "mode":
            raw["mode"] = "human"
        else:
            raw["allocations"].append({**raw["allocations"][0], "initiative_id": "service-automation"})
        before = len(repo.list_audit(company_id="exercise"))
        with pytest.raises((ValueError, security.ScopeError)):
            repo.record_case_attribution(case.case_id, AttributionRequest.model_validate(raw))
        assert repo.list_case_attributions(case.case_id) == []
        assert len(repo.list_audit(company_id="exercise")) == before


def test_mismatched_controls_are_visible_but_excluded_until_corrected(repo):
    with security.principal_scope(principal()):
        case, close, _, b, req = ready(repo)

        def wrong(raw):
            raw["observed"]["controls"]["revenue"] = "999999"

        bad = repo.record_case_observation(case.case_id, observation_request(case, b, close, changes=wrong))
        report = repo.case_realization(case.case_id, b.baseline_id)
        assert report["periods"][0]["status"] == "unreconciled"
        assert report["aggregate_recorded_periods"] is None
        with pytest.raises(ValueError, match="unreconciled"):
            repo.record_case_attribution(case.case_id, claim(bad))
        repo.record_case_observation(
            case.case_id, revised(req, ingestion_key="fixed", expected_previous_id=bad.observation_id)
        )
        assert repo.case_realization(case.case_id, b.baseline_id)["periods"][0]["status"] == "reconciled"


def test_withdrawn_baseline_support_blocks_new_records_and_report_totals(repo):
    with security.principal_scope(principal()):
        case, close, review, b, req = ready(repo)
        o = repo.record_case_observation(case.case_id, req)
        repo.record_case_attribution(case.case_id, claim(o))
        repo.review_case_revision(close.revision_id, request(close, decision="withdraw", previous=review.review_id))
        view = repo.case_realization(case.case_id, b.baseline_id)
        assert view["periods"][0]["status"] == "baseline_review_invalidated"
        assert view["aggregate_recorded_periods"] is None
        with pytest.raises(ValueError, match="invalidated"):
            repo.record_case_observation(
                case.case_id, revised(req, ingestion_key="correct", expected_previous_id=o.observation_id)
            )


@pytest.mark.parametrize("kind", ["observation", "attribution"])
def test_atomic_audit_scope_hash_integrity_and_retention(repo, monkeypatch, kind):
    with security.principal_scope(principal()):
        case, _, _, b, req = ready(repo)
        if kind == "attribution":
            req = claim(repo.record_case_observation(case.case_id, req))
        record = getattr(repo, "record_case_" + kind)
        audit = repo.append_audit
        monkeypatch.setattr(repo, "append_audit", lambda _: (_ for _ in ()).throw(RuntimeError("audit failure")))
        with pytest.raises(RuntimeError, match="audit failure"):
            record(case.case_id, req)
        assert getattr(repo, "list_case_" + kind + "s")(case.case_id) == []
        monkeypatch.setattr(repo, "append_audit", audit)
        result = record(case.case_id, req)
        raw = result.model_dump(mode="json")
        raw["actor"] = "invented"
        with pytest.raises(ValueError, match="hash"):
            (Observation if kind == "observation" else Attribution).model_validate(raw)
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            record(case.case_id, req)
        with pytest.raises(NotFound):
            repo.case_realization(case.case_id, b.baseline_id)
        with pytest.raises(NotFound):
            getattr(repo, "list_case_" + kind + "s")(case.case_id)
    with security.principal_scope(principal(scopes=frozenset({"pvc.read"}))):
        assert repo.case_realization(case.case_id, b.baseline_id)["submitted_periods"] == 1
        with pytest.raises(security.ScopeError):
            record(case.case_id, req)
    with security.principal_scope(principal()):
        assert repo.delete_company_data("exercise")["case_" + kind + "s"] == 1


def test_human_attribution_requires_human_baseline_and_approver(repo):
    with security.principal_scope(principal(kind="human")):
        case, _, _, _, req = ready(repo, mode="human")
        o = repo.record_case_observation(case.case_id, req)
    with security.principal_scope(principal()):
        with pytest.raises(security.ScopeError):
            repo.record_case_attribution(case.case_id, claim(o, mode="human"))
        with pytest.raises(ValueError, match="mode"):
            repo.record_case_attribution(case.case_id, claim(o))
    with security.principal_scope(principal(kind="human")):
        assert repo.record_case_attribution(case.case_id, claim(o, mode="human")).actor_type == "human"


@pytest.mark.parametrize(
    "mutation", ["currency", "period", "scope", "baseline", "rows", "precision", "evidence_hash", "unknown_evidence"]
)
def test_invalid_input_boundaries(repo, mutation):
    with security.principal_scope(principal()):
        case, _, _, _, req = ready(repo)
        raw = req.model_dump(mode="json")
        if mutation == "currency":
            raw["counterfactual"]["currency"] = "EUR"
        elif mutation == "period":
            raw["observed"]["end"] = "2026-10-30"
        elif mutation == "scope":
            raw["initiative_ids"] = ["pricing-renewals"]
        elif mutation == "baseline":
            raw["baseline_sha256"] = "0" * 64
        elif mutation == "rows":
            raw["observed"]["rows"].pop()
        elif mutation == "precision":
            raw["observed"]["rows"][0]["amount"] = "1.001"
        if mutation.startswith("evidence") or mutation == "unknown_evidence":
            o = repo.record_case_observation(case.case_id, req)
            raw = claim(o).model_dump(mode="json")
            if mutation == "evidence_hash":
                raw["evidence"][0]["content"] = "Changed content"
            else:
                raw["allocations"][0]["evidence_ids"] = ["unregistered"]
            with pytest.raises(ValueError):
                AttributionRequest.model_validate(raw)
        else:
            with pytest.raises(ValueError):
                repo.record_case_observation(case.case_id, ObservationRequest.model_validate(raw))


def test_api_uses_bearer_and_preserves_scope_claims_and_retry_semantics(repo, monkeypatch):
    from pe_value_os.api import app as api

    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    tokens = {
        name: dict(sub="service:" + name, pvc_companies=[company], pvc_principal_type="service", scope=scope)
        for name, company, scope in [
            ("writer", "exercise", "pvc.read pvc.write"),
            ("reader", "exercise", "pvc.read"),
            ("outsider", "other", "pvc.read pvc.write"),
        ]
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with security.principal_scope(principal()):
        case, _, _, b, req = ready(repo)
    client = TestClient(api.app)
    path = f"/cases/{case.case_id}/observations"
    payload = req.model_dump(mode="json")
    assert client.post(path, json=payload).status_code == 401
    client.cookies.set("pvc_dev_session", "writer")
    assert client.post(path, json=payload).status_code == 403
    for name in ("reader", "outsider"):
        assert client.post(path, json=payload, headers={"Authorization": "Bearer " + name}).status_code == 404
    h = {"Authorization": "Bearer writer"}
    assert client.post(path, json={**payload, "actor": "invented"}, headers=h).status_code == 422
    response = client.post(path, json=payload, headers=h)
    assert response.status_code == 201, response.text
    o = Observation.model_validate(response.json())
    assert client.post(path, json=payload, headers=h).json() == response.json()
    a = client.post(f"/cases/{case.case_id}/attributions", json=claim(o).model_dump(mode="json"), headers=h)
    assert a.status_code == 201, a.text
    view = client.get(f"/cases/{case.case_id}/realization/{b.baseline_id}", headers={"Authorization": "Bearer reader"})
    assert view.status_code == 200 and view.json()["submitted_periods"] == 1
    assert Decimal(view.json()["aggregate_recorded_periods"]["measured_difference"]["incremental_ebitda"]) == 5000


def test_postgres_ledger_is_immutable_forced_rls_and_downgrade_safe(pg_repo, pg_database):
    import psycopg

    from pe_value_os.db.migrate import current, downgrade, upgrade

    with security.principal_scope(principal()):
        case, _, _, _, req = ready(pg_repo)
        o = pg_repo.record_case_observation(case.case_id, req)
        pg_repo.record_case_attribution(case.case_id, claim(o))
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        for table in ("case_observations", "case_attributions"):
            assert conn.execute("select count(*) from " + table).fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies','exercise',false)")
        for table in ("case_observations", "case_attributions"):
            assert conn.execute("select count(*) from " + table).fetchone()[0] == 1
            for statement in ("update " + table + " set sequence=99", "delete from " + table):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(statement)
    try:
        with pytest.raises(RuntimeError, match="Realization history"):
            downgrade(pg_database[0], "0005")
        assert current(pg_database[0]) == "0006"
    finally:
        upgrade(pg_database[0])


def test_signed_adverse_costs_and_collections_remain_separate(repo):
    with security.principal_scope(principal()):
        case, _, _, b, req = ready(repo)
        o = repo.record_case_observation(case.case_id, req)
        raw = claim(o).model_dump(mode="json")
        sample = raw["allocations"][0]
        raw["allocations"] = [
            {**sample, "row_id": row, "initiative_id": initiative, "amount": amount}
            for row, initiative, amount in (
                ("operating_expense", "service-automation", "-3000"),
                ("implementation_expense", "service-automation", "-2000"),
                ("working_capital_cash", "collections-timing", "180000"),
                ("capex_cash", "service-automation", "-1500"),
            )
        ]
        repo.record_case_attribution(case.case_id, AttributionRequest.model_validate(raw))
        totals = repo.case_realization(case.case_id, b.baseline_id)["aggregate_recorded_periods"]
        assert totals["attributed_difference"] == {
            "incremental_ebitda": Decimal(-5000),
            "pre_tax_cash_proxy": Decimal(178500),
        }
        assert totals["unassigned_residual"] == {
            "incremental_ebitda": Decimal(10000),
            "pre_tax_cash_proxy": Decimal(4000),
        }


def test_realization_report_uses_stored_forecasts_and_not_live_recalculation(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, _, _, b, req = ready(repo)
        repo.record_case_observation(case.case_id, req)
        monkeypatch.setattr("pe_value_os.diligence.cases.evaluate", lambda *_: pytest.fail("must use stored forecast"))
        monkeypatch.setattr(
            "pe_value_os.diligence.cases.evaluate_plan", lambda *_: pytest.fail("must use stored schedule")
        )
        assert repo.case_realization(case.case_id, b.baseline_id)["eligible_periods"] == 1


def test_constructed_walkthrough_reproduces_corrections_and_three_month_economics(tmp_path):
    from pathlib import Path

    from pe_value_os.diligence.realization_render import build_realization_demo

    base = Path("data/constructed/progress")
    output = tmp_path / "custom-review"
    html = build_realization_demo(
        base / "underwriting.json", base / "operating-plan.json", base / "realization.json", output
    )
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["submitted_periods"] == report["eligible_periods"] == 3
    assert len(report["observations"]) == len(report["attributions"]) == 4
    assert len(report["revisions"]) == 3 and report["human_review_count"] == 0
    sums = report["aggregate_recorded_periods"]
    assert sums["measured_difference"] == {"incremental_ebitda": "-16000", "pre_tax_cash_proxy": "118000"}
    assert sums["attributed_difference"] == {"incremental_ebitda": "-32000", "pre_tax_cash_proxy": "112000"}
    assert sums["unassigned_residual"] == {"incremental_ebitda": "16000", "pre_tax_cash_proxy": "6000"}
    assert report["transitions"][2]["before_new_claims"] == "unassigned"
    assert report["periods"][5]["status"] == "not_recorded"
    # Capture changes later benefits; it must not invent a timing effect in Q4.
    assert sums["close_forecast"] == sums["current_forecast"]
    close = json.loads(report["revisions"][1]["financial_result_json"])["scenarios"][1]
    current = json.loads(report["revisions"][2]["financial_result_json"])["scenarios"][1]
    assert close["year_one"]["incremental_ebitda"] != current["year_one"]["incremental_ebitda"]
    assert "custom-review.json" in html.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        build_realization_demo(
            base / "underwriting.json", base / "operating-plan.json", base / "realization.json", base / "realization"
        )


def test_readonly_database_identity_can_read_coherent_ledger(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    from pe_value_os.adapters.postgres import PostgresRepository

    with security.principal_scope(principal()):
        case, _, _, baseline, req = ready(pg_repo)
        pg_repo.record_case_observation(case.case_id, req)
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
            assert reader.case_realization(case.case_id, baseline.baseline_id)["eligible_periods"] == 1
    finally:
        reader.close()


def test_replay_copy_reflects_a_shorter_recorded_calendar():
    from pathlib import Path

    from pe_value_os.diligence.realization_render import (
        RealizationExercise,
        demonstrate_realization,
        render_realization,
    )
    from pe_value_os.diligence.scheduling import OperatingPlan
    from pe_value_os.diligence.underwriting import UnderwritingCase

    base = Path("data/constructed/progress")
    raw = json.loads((base / "realization.json").read_text(encoding="utf-8"))
    raw["months"] = raw["months"][:1]
    report = demonstrate_realization(
        UnderwritingCase.model_validate_json((base / "underwriting.json").read_bytes()),
        OperatingPlan.model_validate_json((base / "operating-plan.json").read_bytes()),
        RealizationExercise.model_validate(raw),
    )
    html = render_realization(report, "short.json")
    assert "1 recorded months" in html and "23 forecast months have no observation" in html
    assert "Recorded months: 2026-10." in html
    assert "-43,000" in html and "118,000" not in html
    assert "first November source snapshot" not in html


def test_replay_reports_unreconciled_controls_as_an_input_error():
    from pathlib import Path

    from pe_value_os.diligence.realization_render import RealizationExercise, demonstrate_realization
    from pe_value_os.diligence.scheduling import OperatingPlan
    from pe_value_os.diligence.underwriting import UnderwritingCase

    base = Path("data/constructed/progress")
    raw = json.loads((base / "realization.json").read_text(encoding="utf-8"))
    raw["months"][0]["observed"]["controls"]["revenue"] = "999"
    with pytest.raises(ValueError, match="reconciled source controls"):
        demonstrate_realization(
            UnderwritingCase.model_validate_json((base / "underwriting.json").read_bytes()),
            OperatingPlan.model_validate_json((base / "operating-plan.json").read_bytes()),
            RealizationExercise.model_validate(raw),
        )


def test_realization_downgrade_guard_sees_unscoped_owner_records(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import downgrade, upgrade

    downgrade(pg_database[0], "0006")

    with security.principal_scope(principal()):
        case, _, _, _, req = ready(pg_repo)
        pg_repo.record_case_observation(case.case_id, req)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='case_observations'::regclass"
        ).fetchone()[0]
        conn.execute("alter table case_observations owner to pvc_migrator")
        conn.execute("grant select,update on alembic_version to pvc_migrator")
        try:
            with psycopg.connect(owner_url) as scoped_owner:
                assert scoped_owner.execute("select count(*) from case_observations").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Realization history"):
                downgrade(owner_url, "0005")
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='case_observations'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table case_observations owner to {}").format(sql.Identifier(owner)))
            upgrade(pg_database[0])
