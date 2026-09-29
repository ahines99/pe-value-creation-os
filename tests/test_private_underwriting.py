"""Private inputs, reproducible forecasts, and current-use authority stay distinct."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import private_underwriting as underwriting
from pe_value_os.diligence.private_records import content_hash
from pe_value_os.diligence.underwriting_models import parse_underwriting
from tests.test_private_financials import accepted_source, snapshot
from tests.test_private_financials import financial_clock as financial_clock
from tests.test_private_records import COMPANY, ENV, FINANCE, NOW, OPERATOR, actor, ingest, review, revoke
from tests.test_private_records import fixed_clock as fixed_clock


@pytest.fixture(autouse=True)
def underwriting_clock(monkeypatch):
    monkeypatch.setattr(underwriting, "datetime", SimpleNamespace(now=lambda zone: NOW))


def inputs(financials):
    assumptions = [
        dict(
            assumption_id=name,
            value=value,
            unit=unit,
            rationale="Fictional test assumption",
            owner="test operator",
            invalidated_by="Source correction or challenged eligibility",
            evidence_ids=["eligibility"],
        )
        for name, value, unit in (
            ("revenue", "980", "currency"),
            ("uplift", "0.1", "fraction"),
            ("capture", "0.5", "fraction"),
            ("churn", "0", "fraction"),
            ("variable", "0.2", "fraction"),
            ("implementation", "50", "currency"),
        )
    ]
    scenarios = [
        dict(
            scenario_id=scenario,
            assumptions=assumptions,
            drivers=[
                dict(
                    kind="pricing",
                    initiative_id="price",
                    title="Fictional bounded price experiment",
                    benefit_pool="fixture-contracts",
                    effective_on="2026-10-01",
                    monthly_eligible_revenue="revenue",
                    uplift="uplift",
                    capture="capture",
                    incremental_churn="churn",
                    variable_cost_rate="variable",
                    collection_lag_months=1,
                    variable_cost_payment_lag_months=1,
                )
            ],
            costs=[
                dict(
                    cost_id="setup",
                    initiative_ids=["price"],
                    kind="implementation",
                    amount="implementation",
                    recognized_on="2026-10-01",
                    paid_on="2026-10-01",
                    retained_if_excluded=True,
                )
            ],
        )
        for scenario in ("downside", "base", "upside")
    ]
    return underwriting.PrivateUnderwritingInputs.model_validate(
        dict(
            case_key="pilot-case",
            company_id=COMPANY,
            entity_id=financials.entity_id,
            currency="USD",
            financial_snapshot_id=financials.snapshot_id,
            financial_snapshot_sha256=financials.content_sha256,
            start="2026-10-01",
            evidence=[dict(evidence_id="eligibility", locator="fixture:eligibility-review", sha256="3" * 64)],
            scenarios=scenarios,
            assumption_bases=[
                dict(
                    scenario_id=s["scenario_id"],
                    assumption_id=a["assumption_id"],
                    **(
                        dict(kind="financial_component", month="2026-01-01", component="revenue", transform="identity")
                        if a["assumption_id"] == "revenue"
                        else dict(kind="operator_judgment", rationale="Fictional experiment hypothesis")
                    ),
                )
                for s in scenarios
                for a in assumptions
            ],
            initiative_bases=[
                dict(
                    initiative_id="price",
                    evidence_ids=["eligibility"],
                    eligibility_rationale="Fictional fixture assumes all contracts eligible; ledger alone does not establish this.",
                    constraints="Contract notice and caps must be independently reviewed before action.",
                    falsification_test="Stop if measured churn exceeds approved threshold.",
                )
            ],
            selected_initiatives=["price"],
            selection_rationale="Fictional arithmetic test only",
            multiples=["8", "10"],
            multiple_rationale="Sensitivity only; no maintainability or valuation approval",
        )
    )


def request(financials, *, key="initial", previous=None, supplied=None):
    return underwriting.UnderwritingRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        inputs=supplied or inputs(financials),
        rationale="Fictional private forecast; no operating authorization",
    )


def prepare(repo):
    grant, record, accepted = accepted_source(repo)
    return grant, record, accepted, snapshot(repo, record, accepted, grant)


def save(repo, financials, **kwargs):
    with security.principal_scope(OPERATOR):
        return repo.record_private_underwriting(COMPANY, "pilot-case", request(financials, **kwargs), ENV)


def test_worked_earnings_cash_and_valuation_are_incremental_private_unapproved(repo):
    *_, financials = prepare(repo)
    with localcontext() as ctx:
        ctx.prec = 2
        result = save(repo, financials)
    base = result.forecast["scenarios"][1]
    assert Decimal(base["year_one"]["incremental_ebitda"]) == Decimal("420.40")
    assert Decimal(base["year_one"]["pre_tax_cash_proxy"]) == Decimal("381.20")
    assert Decimal(base["year_two"]["recurring_contribution"]) == Decimal("470.40")
    assert Decimal(base["cash_settlement_after_horizon"]) == Decimal("39.20")
    assert Decimal(base["maximum_dated_funding_need"]) == Decimal("50")
    assert Decimal(base["valuation"][0]["incremental_ev_sensitivity"]) == Decimal("3763.20")
    assert result.origin == "synthetic_test_fixture" and result.classification == "permissioned_private"
    assert not any(
        (
            result.finance_reviewed,
            result.operating_reviewed,
            result.frozen_comparison_baseline,
            result.causal_value_claim,
            result.operating_action_authorized,
        )
    )
    with pytest.raises(ValueError, match="public exhibits"):
        result.require_public()
    with pytest.raises(ValueError):
        parse_underwriting(result.request.inputs.model_dump(mode="json"))
    with security.principal_scope(OPERATOR):
        assert repo.usable_private_underwriting(COMPANY, result.revision_id, ENV) == result
        assert repo.list_runs(COMPANY) == []
        assert len(repo.list_audit(company_id=COMPANY)) == 5


@pytest.mark.parametrize(
    "mutation",
    [
        "mismatched-value",
        "unknown-month",
        "wrong-unit",
        "missing-basis",
        "duplicate-basis",
        "wrong-case",
        "wrong-entity",
        "wrong-currency",
        "wrong-hash",
        "overlap",
        "unknown-selection",
        "missing-eligibility",
        "constructed-evidence",
        "historical-overlap",
    ],
)
def test_source_and_assumption_contract_rejects_unsupported_inputs(repo, mutation):
    *_, financials = prepare(repo)
    body = inputs(financials).model_dump(mode="json")
    if mutation == "mismatched-value":
        body["scenarios"][0]["assumptions"][0]["value"] = "981"
    elif mutation == "unknown-month":
        body["assumption_bases"][0]["month"] = "2025-12-01"
    elif mutation == "wrong-unit":
        body["assumption_bases"][1] = {**body["assumption_bases"][0], "assumption_id": "uplift"}
    elif mutation == "missing-basis":
        body["assumption_bases"].pop()
    elif mutation == "duplicate-basis":
        body["assumption_bases"].append(body["assumption_bases"][0])
    elif mutation.startswith("wrong-"):
        field = {
            "wrong-case": "case_key",
            "wrong-entity": "entity_id",
            "wrong-currency": "currency",
            "wrong-hash": "financial_snapshot_sha256",
        }[mutation]
        body[field] = "EUR" if field == "currency" else "0" * 64
    elif mutation == "overlap":
        for scenario in body["scenarios"]:
            scenario["drivers"].append({**scenario["drivers"][0], "initiative_id": "duplicate-pool"})
    elif mutation == "unknown-selection":
        body["selected_initiatives"] = ["missing"]
    elif mutation == "missing-eligibility":
        body["initiative_bases"] = []
    elif mutation == "constructed-evidence":
        body["evidence"][0]["classification"] = "constructed"
    else:
        body["start"] = "2026-01-01"
    with pytest.raises(ValueError):
        save(repo, financials, supplied=underwriting.PrivateUnderwritingInputs.model_validate(body))
    with security.principal_scope(OPERATOR):
        assert repo.list_private_underwriting(COMPANY, "pilot-case") == []


def test_observed_actuals_cannot_silently_become_forecast_baseline(repo):
    grant, record, accepted = accepted_source(repo)
    financials = snapshot(repo, record, accepted, grant, purpose="observed_actuals")
    with pytest.raises(ValueError, match="baseline-candidate"):
        save(repo, financials)


@pytest.mark.parametrize("number", ["1e999999", "0.0000000000001", "1234567890123456789012345"])
def test_unbounded_decimal_inputs_are_rejected_before_arithmetic(repo, number):
    *_, financials = prepare(repo)
    body = inputs(financials).model_dump(mode="json")
    body["multiples"] = [number]
    with pytest.raises(ValueError, match="24 digits"):
        underwriting.PrivateUnderwritingInputs.model_validate(body)


def test_private_service_caps_cash_reversals_and_absolute_component_mapping(repo):
    *_, financials = prepare(repo)
    body = inputs(financials).model_dump(mode="json")
    for basis in body["assumption_bases"]:
        if basis["assumption_id"] == "implementation":
            basis.pop("rationale")
            basis.update(
                kind="financial_component", month="2026-01-01", component="implementation_expense", transform="absolute"
            )
    for scenario in body["scenarios"]:
        for name, value, unit in (
            ("contacts", "100", "count"),
            ("coverage", "0.5", "fraction"),
            ("resolution", "0.8", "fraction"),
            ("hours", "0.5", "hours"),
            ("hourly", "10", "currency_per_hour"),
            ("action", "180", "currency"),
            ("spend", "150", "currency"),
            ("receivables", "1000", "currency"),
            ("accelerated", "0.2", "fraction"),
        ):
            scenario["assumptions"].append(
                dict(
                    assumption_id=name,
                    value=value,
                    unit=unit,
                    rationale="Fictional mechanism",
                    owner="operator",
                    invalidated_by="Source challenge",
                    evidence_ids=["eligibility"],
                )
            )
            body["assumption_bases"].append(
                dict(
                    scenario_id=scenario["scenario_id"],
                    assumption_id=name,
                    kind="operator_judgment",
                    rationale="Fictional operating inputs",
                )
            )
        scenario["drivers"].extend(
            [
                dict(
                    kind="service",
                    initiative_id="service",
                    title="Service fixture",
                    benefit_pool="service-pool",
                    effective_on="2026-10-01",
                    monthly_contacts="contacts",
                    coverage="coverage",
                    resolution="resolution",
                    hours_per_contact="hours",
                    avoidable_cost_per_hour="hourly",
                    monthly_cost_action="action",
                    monthly_addressable_spend="spend",
                    cost_action="vendor_reduction",
                    payment_lag_months=0,
                ),
                dict(
                    kind="collections",
                    initiative_id="collect",
                    title="Collection fixture",
                    benefit_pool="collection-pool",
                    effective_on="2026-10-01",
                    receivables_balance="receivables",
                    accelerated_fraction="accelerated",
                    counterfactual_collection_on="2027-01-01",
                ),
            ]
        )
    for initiative in ("service", "collect"):
        body["selected_initiatives"].append(initiative)
        body["initiative_bases"].append({**body["initiative_bases"][0], "initiative_id": initiative})
    revision = save(repo, financials, supplied=underwriting.PrivateUnderwritingInputs.model_validate(body))
    base = revision.forecast["scenarios"][1]
    assert Decimal(base["monthly"][0]["cost_removed"]) == Decimal("150")  # min(200 of work, 180 action, 150 spend)
    assert Decimal(base["monthly"][0]["capacity_hours"]) == Decimal("20")
    assert Decimal(base["monthly"][0]["working_capital_cash"]) == Decimal("200")
    assert Decimal(base["monthly"][3]["working_capital_cash"]) == Decimal("-200")
    assert Decimal(base["total"]["working_capital_cash"]) == 0
    assert Decimal(base["year_one"]["incremental_ebitda"]) == Decimal("2220.40")


def test_negative_economics_and_exclusion_retain_explicit_costs(repo):
    *_, financials = prepare(repo)
    body = inputs(financials).model_dump(mode="json")
    for scenario in body["scenarios"]:
        scenario["assumptions"][3]["value"] = "0.1"
    negative = save(repo, financials, supplied=underwriting.PrivateUnderwritingInputs.model_validate(body))
    assert Decimal(negative.forecast["scenarios"][1]["year_one"]["incremental_ebitda"]) == Decimal("-567.44")
    assert Decimal(negative.forecast["scenarios"][1]["valuation"][0]["incremental_ev_sensitivity"]) < 0
    body["selected_initiatives"] = []
    excluded = save(
        repo,
        financials,
        key="excluded",
        previous=negative,
        supplied=underwriting.PrivateUnderwritingInputs.model_validate(body),
    )
    assert Decimal(excluded.forecast["scenarios"][1]["total"]["incremental_ebitda"]) == Decimal("-50")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_underwriting(COMPANY, negative.revision_id, ENV)


def test_source_correction_preserves_forecast_history_but_requires_new_binding(repo):
    grant, record, _accepted, financials = prepare(repo)
    first = save(repo, financials)
    original = json.dumps(first.model_dump(mode="json"), sort_keys=True)
    corrected = ingest(repo, grant, key="corrected", previous=record)
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_underwriting(COMPANY, first.revision_id, ENV)
    new_review = review(repo, corrected, grant)
    new_financials = snapshot(repo, corrected, new_review, grant, key="corrected", previous=financials)
    replacement = save(repo, new_financials, key="corrected", previous=first)
    with security.principal_scope(OPERATOR):
        history = repo.list_private_underwriting(COMPANY, "pilot-case")
        assert (
            history == [first, replacement]
            and json.dumps(history[0].model_dump(mode="json"), sort_keys=True) == original
        )
        assert repo.usable_private_underwriting(COMPANY, replacement.revision_id, ENV) == replacement


def test_finance_withdrawal_reacceptance_and_revocation_invalidate_use(repo):
    grant, record, accepted, financials = prepare(repo)
    first = save(repo, financials)
    withdrawn = review(repo, record, grant, decision="withdraw", previous=accepted, key="withdraw")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="finance acceptance"):
        repo.usable_private_underwriting(COMPANY, first.revision_id, ENV)
    review(repo, record, grant, previous=withdrawn, key="reaccept")
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="authority changed"):
        repo.usable_private_underwriting(COMPANY, first.revision_id, ENV)
    revoke(repo, grant)
    assert save(repo, financials) == first  # Historical receipt, not processing authorization.
    with security.principal_scope(OPERATOR):
        assert repo.list_private_underwriting(COMPANY, "pilot-case") == [first]
        with pytest.raises(security.ScopeError):
            repo.usable_private_underwriting(COMPANY, first.revision_id, ENV)
    with pytest.raises(security.ScopeError):
        save(repo, financials, key="revoked", previous=first)


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
def test_only_scoped_named_human_operator_can_create(repo, person):
    *_, financials = prepare(repo)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.record_private_underwriting(COMPANY, "pilot-case", request(financials), ENV)


def test_environment_identity_hash_tampering_and_offboarding(repo):
    *_, financials = prepare(repo)
    with security.principal_scope(OPERATOR), pytest.raises(security.ScopeError):
        repo.record_private_underwriting(COMPANY, "pilot-case", request(financials), "wrong")
    first = save(repo, financials)
    forged = first.model_dump(mode="json")
    forged["forecast"]["scenarios"][0]["total"]["incremental_ebitda"] = "999999"
    temporary = first.model_copy(update={"forecast": forged["forecast"]})
    forged["content_sha256"] = content_hash(temporary)
    with pytest.raises(ValueError, match="reproduce"):
        underwriting.verify_revision(underwriting.PrivateUnderwritingRevision.model_validate(forged), financials)
    with security.principal_scope(OPERATOR):
        with pytest.raises(NotFound):
            repo.usable_private_underwriting(COMPANY, "invalid", ENV)
        with pytest.raises(security.ScopeError):
            repo.usable_private_underwriting(COMPANY, first.revision_id, "wrong")
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_underwriting"] == 1
        with pytest.raises(NotFound):
            repo.usable_private_underwriting(COMPANY, first.revision_id, ENV)


def test_concurrent_heads_idempotency_actor_and_atomic_audit(repo, monkeypatch):
    *_, financials = prepare(repo)
    append = repo.append_audit

    def fail(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        save(repo, financials)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_underwriting(COMPANY, "pilot-case") == []
    monkeypatch.setattr(repo, "append_audit", append)
    first = save(repo, financials)
    assert save(repo, financials) == first
    with security.principal_scope(FINANCE), pytest.raises(Conflict, match="idempotency"):
        repo.record_private_underwriting(COMPANY, "pilot-case", request(financials), ENV)
    changed = inputs(financials).model_copy(update={"selection_rationale": "changed"})
    with pytest.raises(Conflict, match="idempotency"):
        save(repo, financials, supplied=changed)

    def append_revision(key):
        try:
            return save(repo, financials, key=key, previous=first)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(r is not None for r in pool.map(append_revision, ["one", "two"])) == 1


def test_private_api_authentication_bounded_body_and_current_use(repo, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    grant, _record, _accepted, financials = prepare(repo)
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
    path = f"/companies/{COMPANY}/private-underwriting"
    case_path = path + "/cases/pilot-case"
    headers = {"Authorization": "Bearer operator"}
    payload = request(financials).model_dump(mode="json")
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
            revision = underwriting.PrivateUnderwritingRevision.model_validate(created.json())
            usable = path + f"/revisions/{revision.revision_id}/usable"
            assert client.get(usable, headers=headers).json()["source_currently_accepted"]
            assert client.get(case_path, headers=headers).json()["historical_records_only"]
            revoke(repo, grant)
            assert client.get(usable, headers=headers).status_code == 404
            assert client.get(case_path, headers=headers).status_code == 200
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_underwriting_database_rls_immutability_and_populated_downgrade_guard(pg_repo, pg_database):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade, upgrade

    grant, record, accepted = accepted_source(pg_repo)
    save(pg_repo, snapshot(pg_repo, record, accepted, grant))
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        assert conn.execute("select count(*) from private_underwriting").fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_underwriting").fetchone()[0] == 1
        for statement in (
            "delete from private_underwriting",
            "update private_underwriting set sequence=99",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = current(pg_database[0])
    downgrade(pg_database[0], "0011")
    with psycopg.connect(pg_database[0], autocommit=True) as conn:
        owner = conn.execute(
            "select pg_get_userbyid(relowner) from pg_class where oid='private_underwriting'::regclass"
        ).fetchone()[0]
        try:
            conn.execute("alter table private_underwriting owner to pvc_migrator")
            conn.execute("grant select,update on alembic_version to pvc_migrator")
            with psycopg.connect(owner_url) as hidden:
                assert hidden.execute("select count(*) from private_underwriting").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private underwriting history"):
                downgrade(owner_url, "0010")
            assert current(pg_database[0]) == "0011"
            assert conn.execute(
                "select relforcerowsecurity from pg_class where oid='private_underwriting'::regclass"
            ).fetchone()[0]
        finally:
            conn.execute(sql.SQL("alter table private_underwriting owner to {}").format(sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert current(pg_database[0]) == head
