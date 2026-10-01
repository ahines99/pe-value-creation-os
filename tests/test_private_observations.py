"""Fictional accounting observations never establish actual company or causal impact."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence import (
    private_baselines,
    private_capacity,
    private_financials,
    private_grants,
    private_records,
    private_underwriting,
)
from pe_value_os.diligence import private_observations as observations
from pe_value_os.diligence.private_intake import IntakeManifest, IntakePolicy, fingerprint
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_baselines import freeze, reviewed
from tests.test_private_baselines import review as review_plan
from tests.test_private_financials import snapshot
from tests.test_private_records import COMPANY, ENV, FINANCE, FIXTURES, NOW, OPERATOR, OWNER, actor
from tests.test_private_records import review as review_source

OCTOBER = date(2026, 10, 1)
AFTER_CLOSE = datetime(2026, 11, 2, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock:
        value = NOW

        @staticmethod
        def now(zone):
            return Clock.value

    for module in (
        private_baselines,
        private_capacity,
        private_financials,
        private_grants,
        private_records,
        private_underwriting,
        observations,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "approval-ui")
    return Clock


def proposal_request(baseline, *, key="initial", previous=None, months=1, timing="prospective"):
    adjustments = {"revenue": "20", "implementation_expense": "50", "operating_cash": "50"}
    return observations.CounterfactualRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        baseline_id=baseline.baseline_id,
        baseline_sha256=baseline.content_sha256,
        first_month=OCTOBER,
        months=months,
        design_timing=timing,
        timing_rationale="Fictional estimate, with explicit authoring and review dates",
        scope_and_limits="Entity-level fixture; excludes causal attribution",
        components=tuple(
            observations.CounterfactualComponent(
                period=observations.month_start(OCTOBER, n),
                component=component,
                anchor_month=date(2026, 1, 1),
                rationale="Historical monthly fixture plus explicit organic growth/removal of a historical one-off",
                adjustments=(
                    ()
                    if component not in adjustments
                    else (
                        observations.CounterfactualAdjustment(
                            adjustment_id="adjustment",
                            amount=adjustments[component],
                            rationale="Fictional organic growth or one-off removal",
                            evidence_reference="fixture:counterfactual",
                            evidence_sha256="3" * 64,
                        ),
                    )
                ),
            )
            for n in range(months)
            for component in observations.COMPONENTS
        ),
    )


def propose(repo, baseline, **kwargs):
    with security.principal_scope(OPERATOR):
        return repo.record_private_counterfactual(
            COMPANY, "pilot-case", "without-intervention", proposal_request(baseline, **kwargs), ENV
        )


def review_request(proposal, *, key="initial", previous=None, decision="accept"):
    return observations.CounterfactualReviewRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        expected_counterfactual_sha256=proposal.content_sha256,
        decision=decision,
        rationale="Fictional finance decision",
        evidence_reference="fixture:review",
        evidence_sha256="4" * 64,
        assessment=(
            observations.CounterfactualAssessment(
                perimeter_units_and_definitions="Same fixture entity, accounting definition and USD units",
                anchor_and_adjustments="January anchor, authored organic growth and removal of prior one-off",
                alternative_explanations="Seasonality and mix remain unproven; all differences unattributed",
                timing_and_comparison_limits="Whole closed months; no causal or day-100 claim",
            )
            if decision == "accept"
            else None
        ),
    )


def accept(repo, proposal, **kwargs):
    with security.principal_scope(FINANCE):
        return repo.review_private_counterfactual(
            COMPANY, proposal.revision_id, review_request(proposal, **kwargs), ENV
        )


def setup(repo, **kwargs):
    grant, source, accepted, anchor, underwriting, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    proposal = propose(repo, baseline, **kwargs)
    review = accept(repo, proposal)
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
        proposal=proposal,
        review=review,
    )


def actuals(repo, anchor, clock, *, first_month=OCTOBER):
    next_month = observations.month_start(first_month, 1)
    clock.value = datetime(next_month.year, next_month.month, 2, 18, tzinfo=UTC)
    ledger = json.loads((FIXTURES / "ledger.json").read_bytes())
    for row, amount in zip(ledger["rows"], ("1120", "-20", "320", "50", "700", "30", "120"), strict=True):
        row.update(period=first_month.isoformat(), amount=amount)
    raw = json.dumps(ledger).encode()
    policy = json.loads((FIXTURES / "policy.json").read_bytes())
    policy["first_month"] = first_month.isoformat()
    for control, amount in zip(policy["controls"], ("1100", "-320", "-50", "700", "30", "-120"), strict=True):
        control.update(period=first_month.isoformat(), amount=amount)
    policy = IntakePolicy.model_validate(policy)
    with security.principal_scope(OWNER):
        grant = repo.record_private_grant(
            COMPANY,
            "actuals",
            private_grants.GrantRequest(
                idempotency_key="initial",
                action="grant",
                expected_previous_sha256=None,
                policy=policy,
                operator_subjects=(OPERATOR.subject, FINANCE.subject),
                environment_id=ENV,
                rationale="Separate fictional actuals source",
                authority_attestation="No actual permission represented",
            ),
        )
    manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    manifest.update(
        export_id=f"fixture-{first_month.isoformat()}",
        extracted_at=clock.value.isoformat(),
        data_cutoff=observations.month_end(first_month).isoformat(),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        policy_sha256=fingerprint(policy),
    )
    request = private_records.IntakeRequest(
        idempotency_key="initial",
        grant_key="actuals",
        expected_grant_sha256=grant.content_sha256,
        expected_previous_sha256=None,
        policy=policy,
        manifest=IntakeManifest.model_validate(manifest),
        rationale="Fictional monthly records",
    )
    with security.principal_scope(OPERATOR):
        source = repo.record_private_intake(COMPANY, "actuals", request, raw, ENV)
    accepted = review_source(repo, source, grant)
    result = snapshot(repo, source, accepted, grant, key="actuals", previous=anchor, purpose="observed_actuals")
    return SimpleNamespace(grant=grant, source=source, review=accepted, snapshot=result, raw=raw)


def observation_request(proposal, review, actual, *, key="initial", previous=None, **patch):
    return observations.PrivateObservationRequest.model_validate(
        dict(
            idempotency_key=key,
            expected_previous_sha256=previous.content_sha256 if previous else None,
            counterfactual_revision_id=proposal.revision_id,
            counterfactual_sha256=proposal.content_sha256,
            counterfactual_review_sha256=review.content_sha256,
            actual_snapshot_id=actual.snapshot_id,
            actual_snapshot_sha256=actual.content_sha256,
            first_month=OCTOBER,
            months=1,
            scope_comparability_attestation="Same fixture entity, units, period and accounting basis; unexplained changes remain unattributed",
            rationale="Fictional comparison only",
            **patch,
        )
    )


def observe(repo, proposal, review, actual, **kwargs):
    with security.principal_scope(FINANCE):
        return repo.record_private_observation(
            COMPANY, "pilot-case", "october", observation_request(proposal, review, actual, **kwargs), ENV
        )


def current(repo, result):
    with security.principal_scope(OPERATOR):
        return repo.usable_private_observation(COMPANY, result.observation_id, ENV)


def test_hand_worked_actuals_counterfactual_and_frozen_variance_reconcile(repo, clock):
    case = setup(repo)
    frozen = case.baseline.model_dump_json()
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    totals = result.result["totals"]
    for kind, ebitda, cash in (
        ("actual", "730", "610"),
        ("counterfactual", "700", "590"),
        ("difference", "30", "20"),
        ("frozen_forecast", "-28.50", "-50"),
        ("variance", "58.50", "70"),
    ):
        assert Decimal(totals[kind]["mapped_ebitda"]) == Decimal(ebitda)
        assert Decimal(totals[kind]["pre_tax_cash_proxy"]) == Decimal(cash)
    assert result.result["unattributed_difference"] == totals["difference"]
    assert all(Decimal(c["attributed"]) == 0 for c in result.result["monthly"][0]["components"])
    assert not result.causal_value_claim and not result.operating_action_authorized
    assert result.origin == "synthetic_test_fixture" and result.result["counterfactual_design_timing"] == "prospective"
    assert current(repo, result) == result and case.baseline.model_dump_json() == frozen
    for record in (case.proposal, case.review, result):
        with pytest.raises(ValueError, match="public exhibits"):
            record.require_public()
    with security.principal_scope(OPERATOR):
        assert len(repo.list_audit(company_id=COMPANY)) == 16


@pytest.mark.parametrize(
    "invalid", ["missing", "duplicate", "wrong_anchor", "outside_forecast", "float", "too_precise"]
)
def test_counterfactual_rejects_incomplete_or_inexact_inputs(repo, invalid):
    *_, plan, finance, operating = reviewed(repo)
    baseline = freeze(repo, plan, finance, operating)
    raw = proposal_request(baseline).model_dump(mode="json")
    if invalid == "missing":
        raw["components"].pop()
    elif invalid == "duplicate":
        raw["components"][-1] = raw["components"][0]
    elif invalid == "wrong_anchor":
        raw["components"][0]["anchor_month"] = "2025-01-01"
    elif invalid == "outside_forecast":
        raw["first_month"] = "2030-10-01"
        for c in raw["components"]:
            c["period"] = "2030-10-01"
    else:
        raw["components"][0]["adjustments"][0]["amount"] = 20.0 if invalid == "float" else "20.001"
    with security.principal_scope(OPERATOR), pytest.raises(ValueError):
        repo.record_private_counterfactual(
            COMPANY, "pilot-case", "without-intervention", observations.CounterfactualRequest.model_validate(raw), ENV
        )


def test_late_creation_and_acceptance_require_explicit_retrospective_version(repo, clock):
    case = setup(repo)
    clock.value = AFTER_CLOSE
    with pytest.raises(ValueError, match="authored before"):
        propose(repo, case.baseline, key="late", previous=case.proposal)
    with pytest.raises(ValueError, match="accepted before"):
        accept(repo, case.proposal, key="late", previous=case.review)
    retrospective = propose(repo, case.baseline, key="retrospective", previous=case.proposal, timing="retrospective")
    accepted = accept(repo, retrospective)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, retrospective, accepted, actual.snapshot)
    assert result.result["counterfactual_design_timing"] == "retrospective"
    with security.principal_scope(OPERATOR), pytest.raises(ValueError, match="superseded"):
        repo.usable_private_counterfactual(COMPANY, case.proposal.revision_id, ENV)


@pytest.mark.parametrize("field", ["counterfactual_sha256", "counterfactual_review_sha256", "actual_snapshot_sha256"])
def test_exact_source_and_review_versions_are_required(repo, clock, field):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    request = observation_request(case.proposal, case.review, actual.snapshot).model_copy(update={field: "0" * 64})
    with security.principal_scope(FINANCE), pytest.raises(ValueError, match="exact accepted"):
        repo.record_private_observation(COMPANY, "pilot-case", "october", request, ENV)


def test_review_withdrawal_reacceptance_and_correction_preserve_history(repo, clock):
    case = setup(repo, timing="retrospective")
    actual = actuals(repo, case.anchor, clock)
    original = observe(repo, case.proposal, case.review, actual.snapshot)
    saved = original.model_dump_json()
    withdrawn = accept(repo, case.proposal, key="withdraw", previous=case.review, decision="withdraw")
    with pytest.raises(ValueError, match="finance acceptance"):
        current(repo, original)
    reaccepted = accept(repo, case.proposal, key="reaccept", previous=withdrawn)
    with pytest.raises(ValueError, match="exact accepted"):
        current(repo, original)
    corrected = observe(repo, case.proposal, reaccepted, actual.snapshot, key="corrected", previous=original)
    assert current(repo, corrected) == corrected
    with pytest.raises(ValueError, match="superseded"):
        current(repo, original)
    assert original.model_dump_json() == saved
    assert observe(repo, case.proposal, case.review, actual.snapshot) == original  # Historical replay only.


@pytest.mark.parametrize("changed", ["baseline_review", "baseline_source", "actual_review", "actual_source"])
def test_changed_support_invalidates_current_use(repo, clock, changed):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    if changed == "baseline_review":
        review_plan(repo, case.plan, "finance", key="withdraw", previous=case.finance, decision="withdraw")
    elif changed == "baseline_source":
        review_source(repo, case.source, case.grant, key="withdraw", previous=case.accepted, decision="withdraw")
    elif changed == "actual_review":
        review_source(repo, actual.source, actual.grant, key="withdraw", previous=actual.review, decision="withdraw")
    else:
        request = actual.source.request.model_copy(
            update={"idempotency_key": "correction", "expected_previous_sha256": actual.source.content_sha256}
        )
        with security.principal_scope(OPERATOR):
            repo.record_private_intake(COMPANY, "actuals", request, actual.raw, ENV)
    with pytest.raises(ValueError):
        current(repo, result)


@pytest.mark.parametrize("grant_key", ["ledger", "actuals"])
def test_each_processing_grant_is_required_but_history_and_withdrawal_survive_revocation(repo, clock, grant_key):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    grant = case.grant if grant_key == "ledger" else actual.grant
    with security.principal_scope(OWNER):
        repo.record_private_grant(
            COMPANY,
            grant_key,
            private_grants.GrantRequest(
                idempotency_key="revoke",
                action="revoke",
                expected_previous_sha256=grant.content_sha256,
                rationale="End fictional processing",
                authority_attestation="Fictional decision",
            ),
        )
    with pytest.raises(security.ScopeError):
        current(repo, result)
    assert observe(repo, case.proposal, case.review, actual.snapshot) == result
    accept(repo, case.proposal, key="withdraw", previous=case.review, decision="withdraw")
    with security.principal_scope(OPERATOR):
        assert repo.list_private_observations(COMPANY, "pilot-case", "october") == [result]


@pytest.mark.parametrize(
    "person",
    [
        OPERATOR,
        OWNER,
        actor("finance", kind="model", roles=("operator", "finance_reviewer")),
        actor("finance", kind="service", roles=("operator", "finance_reviewer")),
        actor("finance", client="mcp-client", roles=("operator", "finance_reviewer")),
        actor("finance", company="other", roles=("operator", "finance_reviewer")),
        actor("finance", scopes=("pvc.read", "pvc.approve"), roles=("operator", "finance_reviewer")),
    ],
)
def test_observations_require_scoped_human_finance_and_write_rights(repo, clock, person):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    with security.principal_scope(person), pytest.raises(security.ScopeError):
        repo.record_private_observation(
            COMPANY, "pilot-case", "october", observation_request(case.proposal, case.review, actual.snapshot), ENV
        )


def test_atomic_audit_rollback_and_competing_observation_heads(repo, clock, monkeypatch):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    original_audit = repo.append_audit

    def fail(event):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(repo, "append_audit", fail)
    with pytest.raises(RuntimeError, match="injected"):
        observe(repo, case.proposal, case.review, actual.snapshot)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_observations(COMPANY, "pilot-case", "october") == []
    monkeypatch.setattr(repo, "append_audit", original_audit)

    def submit(key):
        try:
            return observe(repo, case.proposal, case.review, actual.snapshot, key=key)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("first", "second")))
    assert sum(r is not None for r in results) == 1


def test_closed_subset_missing_period_and_low_decimal_context(repo, clock):
    case = setup(repo, months=2)
    actual = actuals(repo, case.anchor, clock)
    with localcontext() as ctx:
        ctx.prec = 3
        result = observe(repo, case.proposal, case.review, actual.snapshot)
    assert Decimal(result.result["totals"]["difference"]["mapped_ebitda"]) == 30
    clock.value = datetime(2026, 12, 2, tzinfo=UTC)
    request = observation_request(case.proposal, case.review, actual.snapshot).model_copy(update={"months": 2})
    with security.principal_scope(FINANCE), pytest.raises(ValueError, match="missing"):
        repo.record_private_observation(COMPANY, "pilot-case", "two-months", request, ENV)
    clock.value = datetime(2026, 10, 31, 23, tzinfo=UTC)
    with pytest.raises(ValueError, match="completed calendar"):
        observations.calculate_observation(
            observation_request(case.proposal, case.review, actual.snapshot),
            case.proposal,
            case.review,
            case.baseline,
            actual.snapshot,
            case.anchor,
            now=clock.value,
        )


def test_rehashed_counterfactual_and_observation_tampering_fail_reproduction(repo, clock):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    raw = result.model_dump(mode="json")
    raw["result"]["totals"]["difference"]["mapped_ebitda"] = "999999"
    altered = observations.PrivateObservation.model_construct(**raw)
    raw["content_sha256"] = content_hash(altered)
    altered = observations.PrivateObservation.model_validate(raw)
    with pytest.raises(ValueError, match="reproduce"):
        observations.verify_observation(
            altered, case.proposal, case.review, case.baseline, actual.snapshot, case.anchor
        )
    raw = case.proposal.model_dump(mode="json")
    raw["period_totals"]["mapped_ebitda"] = "999999"
    raw["content_sha256"] = content_hash(observations.PrivateCounterfactual.model_construct(**raw))
    with pytest.raises(ValueError, match="reproduce"):
        observations.verify_counterfactual(
            observations.PrivateCounterfactual.model_validate(raw), case.baseline, case.anchor
        )


def test_rehashed_false_chronology_and_unsupported_withdrawal_are_rejected(repo):
    from datetime import timedelta

    case = setup(repo)
    altered = case.proposal.model_copy(update={"recorded_at": NOW - timedelta(days=1)})
    altered = altered.model_copy(update={"content_sha256": content_hash(altered)})
    with pytest.raises(ValueError, match="predates"):
        observations.verify_counterfactual(altered, case.baseline, case.anchor)
    request = case.review.request.model_copy(update={"decision": "withdraw", "assessment": None})
    altered_review = case.review.model_copy(update={"request": request})
    altered_review = altered_review.model_copy(update={"content_sha256": content_hash(altered_review)})
    with pytest.raises(ValueError, match="no prior acceptance"):
        observations.counterfactual_review_head(case.proposal, [altered_review])


def test_scoped_metadata_and_offboarding(repo, clock):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    with security.principal_scope(actor(company="other")), pytest.raises(security.ScopeError):
        repo.list_private_observations(COMPANY, "pilot-case", "october")
    with security.principal_scope(actor(kind="model")), pytest.raises(security.ScopeError):
        repo.list_private_counterfactuals(COMPANY, "pilot-case", "without-intervention")
    with security.principal_scope(OPERATOR):
        for bad_id in ("bad", "00000000-0000-0000-0000-000000000000"):
            with pytest.raises(NotFound):
                repo.usable_private_observation(COMPANY, bad_id, ENV)
        counts = repo.delete_company_data(COMPANY)
        assert (
            counts["private_counterfactuals"]
            == counts["private_counterfactual_reviews"]
            == counts["private_observations"]
            == 1
        )
        with pytest.raises(NotFound):
            repo.usable_private_observation(COMPANY, result.observation_id, ENV)


@pytest.mark.parametrize("change", ["purpose", "definition", "case"])
def test_actual_financial_scope_must_match_the_frozen_anchor(repo, clock, change):
    from tests.test_private_financials import request as financial_request

    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    request = financial_request(
        actual.source,
        actual.review,
        actual.grant,
        key="different",
        previous=actual.snapshot,
        purpose="observed_actuals",
    )
    if change == "purpose":
        request = request.model_copy(update={"purpose": "baseline_candidate"})
    elif change == "definition":
        request = request.model_copy(
            update={"definition": request.definition.model_copy(update={"accounting_basis": "IFRS"})}
        )
    else:
        request = request.model_copy(update={"expected_previous_sha256": None})
    with security.principal_scope(FINANCE):
        other = repo.record_private_financial_snapshot(
            COMPANY, "another-case" if change == "case" else "pilot-case", request, ENV
        )
    with pytest.raises(ValueError, match=r"(purpose|definitions)"):
        observe(repo, case.proposal, case.review, other)


@pytest.mark.parametrize("decision", ["reject", "request_changes", "withdraw"])
def test_unaccepted_counterfactual_never_supports_observation(repo, clock, decision):
    case = setup(repo)
    accept(repo, case.proposal, key="change", previous=case.review, decision=decision)
    actual = actuals(repo, case.anchor, clock)
    with pytest.raises(ValueError, match="finance acceptance"):
        observe(repo, case.proposal, case.review, actual.snapshot)


def test_idempotency_cannot_change_request_or_author_and_wrong_environment_denies(repo, clock):
    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    result = observe(repo, case.proposal, case.review, actual.snapshot)
    altered = observation_request(case.proposal, case.review, actual.snapshot).model_copy(
        update={"rationale": "different"}
    )
    with security.principal_scope(FINANCE), pytest.raises(Conflict, match="idempotency"):
        repo.record_private_observation(COMPANY, "pilot-case", "october", altered, ENV)
    with (
        security.principal_scope(actor("other-finance", roles=("operator", "finance_reviewer"))),
        pytest.raises(Conflict, match="author"),
    ):
        repo.record_private_observation(COMPANY, "pilot-case", "october", result.request, ENV)
    with security.principal_scope(OPERATOR), pytest.raises(security.ScopeError):
        repo.usable_private_observation(COMPANY, result.observation_id, "another-environment")
    with pytest.raises(Conflict):
        propose(repo, case.baseline, key="other")
    with pytest.raises(Conflict):
        accept(repo, case.proposal, key="other")


def test_observation_and_review_withdrawal_share_atomic_company_lock(repo, clock, monkeypatch):
    import importlib
    from threading import Event

    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    # Both backends run the shared record rules defined beside InMemoryRepository.
    module = importlib.import_module("pe_value_os.adapters.repositories")
    original = module.prepare_private_observation
    entered, attempted, release = Event(), Event(), Event()

    def gate(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    def withdraw():
        attempted.set()
        return accept(repo, case.proposal, key="withdraw", previous=case.review, decision="withdraw")

    monkeypatch.setattr(module, "prepare_private_observation", gate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(observe, repo, case.proposal, case.review, actual.snapshot)
        try:
            assert entered.wait(10)
            withdrawal = pool.submit(withdraw)
            assert attempted.wait(10)
            assert not withdrawal.done()
        finally:
            release.set()
        result = future.result(timeout=10)
        withdrawal.result(timeout=10)
    with pytest.raises(ValueError, match="finance acceptance"):
        current(repo, result)


def test_private_comparison_api_authentication_body_boundaries_and_withdrawal(repo, clock, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    case = setup(repo)
    actual = actuals(repo, case.anchor, clock)
    people = {"operator": OPERATOR, "finance": FINANCE, "model": actor(kind="model"), "foreign": actor(company="other")}
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
    cf = f"/companies/{COMPANY}/private-counterfactuals"
    cf_stream = cf + "/cases/pilot-case/streams/without-intervention"
    cf_revision = cf + f"/revisions/{case.proposal.revision_id}"
    obs = f"/companies/{COMPANY}/private-observations"
    obs_stream = obs + "/cases/pilot-case/streams/october"

    def headers(name):
        return {"Authorization": "Bearer " + name}

    try:
        with TestClient(api.app) as client:
            payload = observation_request(case.proposal, case.review, actual.snapshot).model_dump(mode="json")
            assert client.post(obs_stream, json=payload).status_code == 401
            client.cookies.set("pvc_dev_session", "finance")
            assert client.post(obs_stream, json=payload).status_code == 403
            client.cookies.clear()
            for name in ("operator", "model", "foreign"):
                for path in (obs_stream, cf_revision + "/reviews"):
                    assert (
                        client.post(path, content=b"invalid-private-payload", headers=headers(name)).status_code == 404
                    )
            for path in (obs_stream, cf_stream, cf_revision + "/reviews"):
                bad = client.post(path, json={"secret": "sensitive-fixture"}, headers=headers("finance"))
                assert bad.status_code == 422 and "sensitive-fixture" not in bad.text
                assert (
                    client.post(path, content=b" " * (1024 * 1024 + 1), headers=headers("finance")).status_code == 413
                )
            assert (
                client.post(
                    cf_stream, json=case.proposal.request.model_dump(mode="json"), headers=headers("operator")
                ).status_code
                == 201
            )
            assert (
                client.post(
                    cf_revision + "/reviews",
                    json=case.review.request.model_dump(mode="json"),
                    headers=headers("finance"),
                ).status_code
                == 201
            )
            assert client.get(cf_revision + "/usable", headers=headers("operator")).json()["usable_for_comparison"]
            created = client.post(obs_stream, json=payload, headers=headers("finance"))
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            result = observations.PrivateObservation.model_validate(created.json())
            path = obs + f"/observations/{result.observation_id}/usable"
            assert client.get(path, headers=headers("operator")).json()["usable_for_comparison"]
            assert client.get(obs_stream, headers=headers("operator")).json()["historical_records_only"]
            from tests.test_private_records import revoke

            revoke(repo, case.grant)
            assert client.get(path, headers=headers("operator")).status_code == 404
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            withdrawal = review_request(case.proposal, key="withdraw", previous=case.review, decision="withdraw")
            assert (
                client.post(
                    cf_revision + "/reviews", json=withdrawal.model_dump(mode="json"), headers=headers("finance")
                ).status_code
                == 201
            )
            assert len(client.get(cf_revision + "/reviews", headers=headers("operator")).json()["reviews"]) == 2
            assert client.get(cf_stream, headers=headers("operator")).status_code == 200
            assert client.get(obs_stream, headers=headers("operator")).status_code == 200
    finally:
        api.set_ctx(None)
        api.reset_auth()


@pytest.mark.parametrize("stage", ["proposal", "review", "observation"])
def test_measurement_rls_append_only_and_populated_owner_downgrade_guard(pg_repo, pg_database, clock, stage):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current, downgrade, upgrade

    *_, anchor, _underwriting, plan, finance, operating = reviewed(pg_repo)
    baseline = freeze(pg_repo, plan, finance, operating)
    proposal = propose(pg_repo, baseline)
    if stage != "proposal":
        review = accept(pg_repo, proposal)
        if stage == "observation":
            actual = actuals(pg_repo, anchor, clock)
            observe(pg_repo, proposal, review, actual.snapshot)
    tables = ("private_counterfactuals", "private_counterfactual_reviews", "private_observations")
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        for table in tables:
            assert conn.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table))).fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        assert conn.execute("select count(*) from private_counterfactuals").fetchone()[0] == 1
        for table in tables:
            for statement in ("delete from {}", "update {} set sequence=99"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql.SQL(statement).format(sql.Identifier(table)))
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = current(pg_database[0])
    downgrade(pg_database[0], "0014")
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
            with pytest.raises(RuntimeError, match="Private measurement history"):
                downgrade(owner_url, "0013")
            assert current(pg_database[0]) == "0014"
            for table in tables:
                assert conn.execute(
                    "select relforcerowsecurity from pg_class where oid=%s::regclass", (table,)
                ).fetchone()[0]
        finally:
            for table, owner in owners.items():
                conn.execute(sql.SQL("alter table {} owner to {}").format(sql.Identifier(table), sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert current(pg_database[0]) == head
