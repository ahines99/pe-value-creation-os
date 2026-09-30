"""Signed claims reconcile; fictional acceptance never establishes causal impact."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.repositories import Conflict, InMemoryRepository, NotFound
from pe_value_os.diligence import private_attribution as attribution
from pe_value_os.diligence import private_execution as execution
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_execution import acceptance, at, authorize, binding, delivery, evidence, record
from tests.test_private_observations import actuals, observation_request, setup
from tests.test_private_observations import clock as measurement_clock  # noqa: F401
from tests.test_private_records import COMPANY, ENV, FINANCE, OPERATOR, actor, revoke

NOVEMBER = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def clock(monkeypatch, request):
    measured = request.getfixturevalue("measurement_clock")

    class Clock(datetime):
        @classmethod
        def now(cls, zone):
            return measured.value

    for module in (execution, attribution):
        monkeypatch.setattr(module, "datetime", Clock)
    return measured


@pytest.fixture
def memory(tmp_path):
    return InMemoryRepository(FileSystemEvidenceStore(tmp_path / "evidence"))


def complete(memory, clock, *, authorized_until=None, hold_at=None):
    case = setup(memory, months=2)
    case.authorization = authorize(memory, case, expiry=authorized_until or datetime(2026, 12, 1, tzinfo=UTC))
    clock.value = at(2)
    case.foundation_work = record(memory, case, delivery(case.authorization))
    case.foundation = record(memory, case, acceptance([case.foundation_work]))
    clock.value = at(4)
    case.gate_work = record(
        memory,
        case,
        delivery(
            case.authorization,
            task="price-gate",
            work_key="gate",
            start=at(3, 9),
            end=at(3, 17),
            cost="20",
        ),
    )
    case.gate = record(memory, case, acceptance([case.gate_work], prerequisites=(case.foundation,)))
    if hold_at:
        clock.value = hold_at
        record(memory, case, execution.AuthorizationDecision(decision="hold"))
    case.actual = actuals(memory, case.anchor, clock, first_month=NOVEMBER)
    body = observation_request(case.proposal, case.review, case.actual.snapshot).model_copy(
        update={"first_month": NOVEMBER}
    )
    with security.principal_scope(FINANCE):
        case.observation = memory.record_private_observation(COMPANY, "pilot-case", "november", body, ENV)
    with security.principal_scope(OPERATOR):
        case.events = memory.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    return case


def allocation(case, *, component="revenue", amount="60", period=NOVEMBER, initiative="price"):
    positive = Decimal(amount) > 0
    return attribution.AttributionAllocation(
        period=period,
        component=component,
        initiative_id=initiative,
        amount=amount,
        mechanism="Fictional price realization, not independently established",
        alternative_explanations="Mix, seasonality, organic movement and selection bias remain possible",
        evidence=evidence(),
        benefit_acceptance=binding(case.gate) if positive else None,
        measurement_authorization=binding(case.authorization) if positive else None,
    )


def body(case, allocations=None, *, previous=None, key="initial"):
    return attribution.AttributionRequest(
        idempotency_key=key,
        expected_previous_sha256=previous.content_sha256 if previous else None,
        observation_id=case.observation.observation_id,
        observation_sha256=case.observation.content_sha256,
        expected_execution_head_sha256=case.events[-1].content_sha256 if case.events else None,
        allocations=tuple(allocations)
        if allocations is not None
        else (
            allocation(case),
            allocation(case, component="implementation_expense", amount="-50"),
            allocation(case, component="operating_cash", amount="30"),
        ),
        rationale="Fictional signed allocations for separate finance review",
        method_and_limits="Same-sign component allocation; residual is retained; no proof of causation",
    )


def calculate(case, clock, request=None, *, current=False):
    return attribution.calculate_attribution(
        request or body(case),
        case.observation,
        case.baseline,
        case.plan,
        case.events,
        now=clock.value,
        current_support=current,
    )


def propose(case, request=None, *, key="claims", previous=None):
    with security.principal_scope(OPERATOR):
        return attribution.prepare_attribution(
            COMPANY,
            "pilot-case",
            key,
            request or body(case, previous=previous),
            case.observation,
            case.baseline,
            case.plan,
            case.events,
            previous,
        )


def review_body(proposal, *, previous=None, decision="accept"):
    return attribution.AttributionReviewRequest(
        idempotency_key=f"review-{previous.sequence + 1 if previous else 1}",
        expected_previous_sha256=previous.content_sha256 if previous else None,
        expected_attribution_sha256=proposal.content_sha256,
        expected_execution_head_sha256=proposal.request.expected_execution_head_sha256,
        decision=decision,
        rationale="Fictional review, no real finance participation",
        evidence=evidence(),
        assessment=attribution.AttributionAssessment(
            accounting_reconciliation="Signed component controls reconciled",
            mechanism_and_delivery="Exact fictional prerequisite and benefit-gate history",
            alternative_explanations="Mix and seasonality remain unexplained",
            double_counting_and_residuals="One claim window, residual remains explicit",
            attribution_limits="Not independently verified causal impact",
        )
        if decision == "accept"
        else None,
    )


def test_hand_worked_signed_costs_and_cash_reconcile_without_causal_claim(memory, clock):
    case = complete(memory, clock)
    result = calculate(case, clock)
    for kind, ebitda, cash in (("difference", 30, 20), ("proposed_attribution", 10, 30), ("residual", 20, -10)):
        assert Decimal(result["totals"][kind]["mapped_ebitda"]) == ebitda
        assert Decimal(result["totals"][kind]["pre_tax_cash_proxy"]) == cash
    for row in result["monthly"][0]["components"]:
        assert Decimal(row["difference"]) == Decimal(row["proposed_attribution"]) + Decimal(row["residual"])
    assert result["origin"] == "synthetic_test_fixture"
    assert not result["causal_impact_proven"] and not result["finance_reviewed"]
    assert case.observation.result["unattributed_difference"] == case.observation.result["totals"]["difference"]
    with localcontext() as ctx:
        ctx.prec = 6
        assert calculate(case, clock) == result


@pytest.mark.parametrize("amount", ["100.01", "-1"])
def test_overclaim_and_opposite_sign_are_rejected(memory, clock, amount):
    case = complete(memory, clock)
    with pytest.raises(ValueError, match=r"exceed|sign"):
        calculate(case, clock, body(case, [allocation(case, amount=amount)]))


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown_initiative", "outside_month", "missing_gate", "wrong_gate", "stale_head"]
)
def test_exact_claim_identity_scope_and_execution_bindings(memory, clock, mutation):
    case = complete(memory, clock)
    raw = body(case).model_dump(mode="json")
    if mutation == "duplicate":
        raw["allocations"].append(raw["allocations"][0])
    elif mutation == "unknown_initiative":
        raw["allocations"][0]["initiative_id"] = "foreign"
    elif mutation == "outside_month":
        raw["allocations"][0]["period"] = "2026-10-01"
    elif mutation == "missing_gate":
        raw["allocations"][0]["benefit_acceptance"] = None
    elif mutation == "wrong_gate":
        raw["allocations"][0]["benefit_acceptance"] = binding(case.foundation).model_dump(mode="json")
    else:
        raw["expected_execution_head_sha256"] = case.foundation.content_sha256
    with pytest.raises(ValueError):
        calculate(case, clock, attribution.AttributionRequest.model_validate(raw))


@pytest.mark.parametrize("amount", [0, 1.0, True, "0.001", "NaN", "Infinity"])
def test_claim_amounts_are_exact_nonzero_currency_amounts(memory, clock, amount):
    case = complete(memory, clock)
    raw = allocation(case).model_dump(mode="json")
    raw["amount"] = amount
    with pytest.raises(ValueError):
        attribution.AttributionAllocation.model_validate(raw)


@pytest.mark.parametrize("hold_at", [datetime(2026, 10, 30, tzinfo=UTC), datetime(2026, 11, 15, tzinfo=UTC)])
def test_hold_before_or_during_measurement_blocks_positive_allocation(memory, clock, hold_at):
    case = complete(memory, clock, hold_at=hold_at)
    with pytest.raises(ValueError, match="authorization changed"):
        calculate(case, clock)


def test_partial_authorization_month_cannot_support_whole_month_credit(memory, clock):
    case = complete(memory, clock, authorized_until=datetime(2026, 11, 15, tzinfo=UTC))
    with pytest.raises(ValueError, match="full measurement month"):
        calculate(case, clock)


def test_gate_accepted_during_month_cannot_backfill_whole_month(memory, clock):
    case = complete(memory, clock)
    # Pure temporal boundary check uses the exact accepted October event.
    october = allocation(case, period=date(2026, 10, 1))
    state = execution.replay(case.baseline, case.plan, case.events)
    with pytest.raises(ValueError, match="precede the full measurement month"):
        attribution.require_benefit_support(october, state)


def test_signed_cost_and_residual_only_proposals_do_not_require_completed_delivery(memory, clock):
    case = complete(memory, clock)
    case.events = []
    for allocations in ([], [allocation(case, component="implementation_expense", amount="-50")]):
        result = calculate(case, clock, body(case, allocations))
        assert Decimal(result["totals"]["proposed_attribution"]["mapped_ebitda"]) == (-50 if allocations else 0)
        assert not result["causal_impact_proven"]


def test_later_stop_preserves_prior_month_but_current_gate_withdrawal_removes_support(memory, clock):
    case = complete(memory, clock)
    proposal = propose(case)
    clock.value = datetime(2026, 12, 3, tzinfo=UTC)
    record(memory, case, execution.AuthorizationDecision(decision="stop"))
    with security.principal_scope(OPERATOR):
        case.events = memory.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    assert calculate(case, clock, proposal.request, current=True) == proposal.result
    record(memory, case, acceptance([case.gate_work], prerequisites=(case.foundation,), decision="withdraw"))
    with security.principal_scope(OPERATOR):
        case.events = memory.list_private_execution_events(COMPANY, case.baseline.baseline_id)
    attribution.verify_attribution(proposal, case.observation, case.baseline, case.plan, case.events)
    with pytest.raises(ValueError, match="superseded"):
        calculate(case, clock, proposal.request, current=True)


def test_distinct_finance_review_withdrawal_and_reacceptance_preserve_proposal(memory, clock):
    case = complete(memory, clock)
    proposal = propose(case)
    with security.principal_scope(FINANCE):
        accepted = attribution.prepare_attribution_review(proposal, review_body(proposal), [])
        withdrawn = attribution.prepare_attribution_review(
            proposal, review_body(proposal, previous=accepted, decision="withdraw"), [accepted]
        )
        reaccepted = attribution.prepare_attribution_review(
            proposal, review_body(proposal, previous=withdrawn), [accepted, withdrawn]
        )
    assert attribution.attribution_review_head(proposal, [accepted, withdrawn, reaccepted]) == reaccepted
    assert not proposal.finance_reviewed and not reaccepted.causal_impact_proven
    for value in (proposal, accepted):
        with pytest.raises(ValueError, match="public exhibits"):
            value.require_public()
    # Forge a valid hash to show semantic review validation, beyond checksum tests.
    raw = accepted.model_dump(mode="json")
    raw["author"] = proposal.author
    raw["content_sha256"] = content_hash(attribution.AttributionReview.model_construct(**raw))
    forged = attribution.AttributionReview.model_validate(raw)
    with pytest.raises(ValueError, match="different human"):
        attribution.attribution_review_head(proposal, [forged])
    with security.principal_scope(FINANCE), pytest.raises(ValueError, match="preceding acceptance"):
        attribution.prepare_attribution_review(proposal, review_body(proposal, decision="withdraw"), [])


def test_reproduction_detects_resigned_financial_tampering(memory, clock):
    case = complete(memory, clock)
    proposal = propose(case)
    raw = proposal.model_dump(mode="json")
    raw["result"]["totals"]["proposed_attribution"]["mapped_ebitda"] = "999"
    raw["content_sha256"] = content_hash(attribution.PrivateAttribution.model_construct(**raw))
    forged = attribution.PrivateAttribution.model_validate(raw)
    with pytest.raises(ValueError, match="does not reproduce"):
        attribution.verify_attribution(forged, case.observation, case.baseline, case.plan, case.events)


def test_window_reservation_prevents_parallel_stream_double_counting(memory, clock):
    case = complete(memory, clock)
    first = propose(case)
    second = propose(case, key="another-stream")
    with pytest.raises(ValueError, match="already reserves"):
        attribution.require_disjoint_accepted_windows(second, [first])
    attribution.require_disjoint_accepted_windows(first, [first])
    residual_only = propose(case, body(case, []), key="residual-only")
    attribution.require_disjoint_accepted_windows(residual_only, [first])
    attribution.require_disjoint_accepted_windows(second, [residual_only])


def test_stream_correction_and_source_bindings_cannot_drift(memory, clock):
    case = complete(memory, clock)
    first = propose(case)
    corrected = propose(case, body(case, [], previous=first, key="correction"), previous=first)
    assert corrected.sequence == 2 and first.request.allocations
    with pytest.raises(ValueError, match="cannot change scope"):
        propose(case, body(case, previous=first), key="foreign", previous=first)
    with pytest.raises(ValueError, match="same-scope"):
        calculate(case, clock, body(case).model_copy(update={"observation_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="unavailable"):
        attribution.execution_prefix(case.events, "0" * 64)


def save(repo, case, request=None, *, key="claims", person=OPERATOR):
    with security.principal_scope(person):
        return repo.record_private_attribution(COMPANY, "pilot-case", key, request or body(case), ENV)


def finance_review(repo, proposal, request=None, *, person=FINANCE, environment=ENV):
    with security.principal_scope(person):
        return repo.review_private_attribution(
            COMPANY, proposal.revision_id, request or review_body(proposal), environment
        )


def current(repo, proposal):
    with security.principal_scope(OPERATOR):
        return repo.usable_private_attribution(COMPANY, proposal.revision_id, ENV)


def test_persisted_attribution_requires_finance_acceptance_and_preserves_originals(repo, clock):
    case = complete(repo, clock)
    observation_json = case.observation.model_dump_json()
    proposal = save(repo, case)
    with pytest.raises(ValueError, match="finance acceptance"):
        current(repo, proposal)
    accepted = finance_review(repo, proposal)
    assert current(repo, proposal) == (proposal, accepted)
    assert case.observation.model_dump_json() == observation_json
    assert not proposal.finance_reviewed and not accepted.causal_impact_proven
    with security.principal_scope(OPERATOR):
        assert repo.list_private_attributions(COMPANY, "pilot-case", "claims") == [proposal]
        assert repo.list_private_attribution_reviews(COMPANY, proposal.revision_id) == [accepted]
        counts = repo.delete_company_data(COMPANY)
        assert counts["private_attributions"] == counts["private_attribution_reviews"] == 1
        with pytest.raises(NotFound):
            repo.list_private_attribution_reviews(COMPANY, proposal.revision_id)


def test_private_attribution_retries_and_withdrawal_survive_revoked_processing(repo, clock):
    case = complete(repo, clock)
    proposal = save(repo, case)
    accepted = finance_review(repo, proposal)
    revoke(repo, case.grant)
    assert save(repo, case) == proposal and finance_review(repo, proposal) == accepted
    with pytest.raises(security.ScopeError):
        current(repo, proposal)
    with pytest.raises(security.ScopeError):
        save(repo, case, body(case, previous=proposal, key="new"))
    withdrawn = finance_review(
        repo, proposal, review_body(proposal, previous=accepted, decision="withdraw"), environment=""
    )
    with security.principal_scope(OPERATOR):
        assert repo.list_private_attribution_reviews(COMPANY, proposal.revision_id) == [accepted, withdrawn]
    with pytest.raises(security.ScopeError):
        finance_review(repo, proposal, review_body(proposal, previous=withdrawn))


def test_independent_review_idempotency_and_stale_heads(repo, clock):
    case = complete(repo, clock)
    proposal = save(repo, case, person=FINANCE)
    with pytest.raises(ValueError, match="different human"):
        finance_review(repo, proposal)
    with pytest.raises(Conflict, match="another request or author"):
        save(repo, case)
    with pytest.raises(Conflict, match="history changed"):
        save(repo, case, body(case, key="stale"))
    with pytest.raises(security.ScopeError):
        finance_review(repo, proposal, person=OPERATOR)
    changed = body(case, previous=proposal, key="replacement").model_copy(
        update={"expected_execution_head_sha256": None}
    )
    with pytest.raises(Conflict, match="execution history"):
        save(repo, case, changed)


def test_correction_withdrawal_reacceptance_and_window_reservation(repo, clock):
    case = complete(repo, clock)
    first = save(repo, case)
    first_review = finance_review(repo, first)
    alternate = save(repo, case, key="alternative")
    with pytest.raises(ValueError, match="already reserves"):
        finance_review(repo, alternate)
    withdrawn = finance_review(repo, first, review_body(first, previous=first_review, decision="withdraw"))
    second_review = finance_review(repo, alternate)
    with pytest.raises(ValueError, match="already reserves"):
        finance_review(repo, first, review_body(first, previous=withdrawn))
    replacement = save(repo, case, body(case, [], previous=alternate, key="corrected"), key="alternative")
    with pytest.raises(ValueError, match="superseded"):
        current(repo, alternate)
    reaccepted = finance_review(repo, first, review_body(first, previous=withdrawn))
    assert current(repo, first)[1] == reaccepted
    finance_review(repo, replacement)
    assert current(repo, replacement)[0].request.allocations == ()
    with security.principal_scope(OPERATOR):
        assert repo.list_private_attribution_reviews(COMPANY, alternate.revision_id) == [second_review]


def test_observation_correction_invalidates_claim_without_rewriting_it(repo, clock):
    case = complete(repo, clock)
    proposal = save(repo, case)
    accepted = finance_review(repo, proposal)
    with security.principal_scope(FINANCE):
        newer = repo.record_private_observation(
            COMPANY,
            "pilot-case",
            "november",
            case.observation.request.model_copy(
                update={
                    "idempotency_key": "corrected",
                    "expected_previous_sha256": case.observation.content_sha256,
                    "rationale": "Corrected accounting-comparability attestation",
                }
            ),
            ENV,
        )
    with pytest.raises(ValueError, match="superseded"):
        current(repo, proposal)
    case.observation = newer
    corrected = save(repo, case, body(case, previous=proposal, key="corrected"))
    with pytest.raises(ValueError, match="finance acceptance"):
        current(repo, corrected)
    with security.principal_scope(OPERATOR):
        assert repo.list_private_attribution_reviews(COMPANY, proposal.revision_id) == [accepted]
    finance_review(repo, corrected)
    assert current(repo, corrected)[0] == corrected


def test_later_execution_and_acceptance_withdrawal_are_checked_on_current_use(repo, clock):
    case = complete(repo, clock)
    proposal = save(repo, case)
    accepted = finance_review(repo, proposal)
    clock.value = datetime(2026, 12, 3, tzinfo=UTC)
    stop = record(repo, case, execution.AuthorizationDecision(decision="stop"))
    assert current(repo, proposal) == (proposal, accepted)
    with pytest.raises(Conflict, match="execution history"):
        finance_review(repo, proposal, review_body(proposal, previous=accepted, decision="withdraw"))
    withdrawal = review_body(proposal, previous=accepted, decision="withdraw").model_copy(
        update={"expected_execution_head_sha256": stop.content_sha256}
    )
    withdrawn = finance_review(repo, proposal, withdrawal)
    reaccept = review_body(proposal, previous=withdrawn).model_copy(
        update={"expected_execution_head_sha256": stop.content_sha256}
    )
    finance_review(repo, proposal, reaccept)
    record(repo, case, acceptance([case.gate_work], prerequisites=(case.foundation,), decision="withdraw"))
    with pytest.raises(ValueError, match="superseded"):
        current(repo, proposal)


def test_concurrent_acceptance_reserves_only_one_overlapping_stream(repo, clock):
    case = complete(repo, clock)
    proposals = [save(repo, case, key=key) for key in ("one", "two")]

    def accept_one(proposal):
        try:
            finance_review(repo, proposal)
            return "accepted"
        except ValueError as exc:
            assert "already reserves" in str(exc)
            return "overlap"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept_one, proposals)) == ["accepted", "overlap"]


def test_distinct_observation_streams_cannot_duplicate_the_same_claim_window(repo, clock):
    case = complete(repo, clock)
    first = save(repo, case)
    finance_review(repo, first)
    with security.principal_scope(FINANCE):
        alternative = repo.record_private_observation(
            COMPANY, "pilot-case", "another-measurement", case.observation.request, ENV
        )
    assert alternative.measurement_key != case.observation.measurement_key
    case.observation = alternative
    second = save(repo, case, key="second-claims")
    with pytest.raises(ValueError, match="already reserves"):
        finance_review(repo, second)


@pytest.mark.parametrize("field", ["observation_sha256", "expected_execution_head_sha256"])
def test_database_rejects_missing_exact_observation_and_execution_references(pg_repo, clock, field):
    import psycopg

    case = complete(pg_repo, clock)
    proposal = propose(case)
    altered = proposal.model_copy(update={"request": proposal.request.model_copy(update={field: "0" * 64})})
    altered = altered.model_copy(update={"content_sha256": content_hash(altered)})
    attribution.PrivateAttribution.model_validate(altered.model_dump(mode="json"))
    with security.principal_scope(OPERATOR):
        with pytest.raises(psycopg.errors.ForeignKeyViolation), pg_repo.approval_transaction():
            pg_repo._save_private_attribution(altered)
        assert pg_repo.list_private_attributions(COMPANY, "pilot-case", "claims") == []


@pytest.mark.parametrize("operation", ["proposal", "review"])
def test_attribution_receipt_and_audit_rollback_are_atomic(repo, clock, monkeypatch, operation):
    case = complete(repo, clock)
    proposal = save(repo, case) if operation == "review" else None

    def fail_audit(event):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(repo, "append_audit", fail_audit)
    with pytest.raises(RuntimeError, match="fixture audit failure"):
        finance_review(repo, proposal) if proposal else save(repo, case)
    with security.principal_scope(OPERATOR):
        records = (
            repo.list_private_attribution_reviews(COMPANY, proposal.revision_id)
            if proposal
            else repo.list_private_attributions(COMPANY, "pilot-case", "claims")
        )
        assert records == []


@pytest.mark.parametrize("kind", ["model", "service"])
def test_models_services_and_foreign_scope_cannot_use_private_attribution(repo, clock, kind):
    case = complete(repo, clock)
    proposal = save(repo, case)
    with pytest.raises(security.ScopeError):
        save(repo, case, person=actor(kind=kind))
    with security.principal_scope(actor(kind=kind)), pytest.raises(security.ScopeError):
        repo.list_private_attribution_reviews(COMPANY, proposal.revision_id)
    with security.principal_scope(actor(company="foreign")), pytest.raises(security.ScopeError):
        repo.list_private_attributions(COMPANY, "pilot-case", "claims")
    with security.principal_scope(OPERATOR), pytest.raises(NotFound):
        repo.list_private_attribution_reviews(COMPANY, "not-a-uuid")


def test_concurrent_revocation_serializes_with_attribution_acceptance(repo, clock, monkeypatch):
    from threading import Event

    case = complete(repo, clock)
    proposal = save(repo, case)
    original = attribution.prepare_attribution_review
    entered, attempted, release = Event(), Event(), Event()

    def wait_review(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    def revoke_source():
        attempted.set()
        return revoke(repo, case.grant)

    monkeypatch.setattr(attribution, "prepare_attribution_review", wait_review)
    with ThreadPoolExecutor(max_workers=2) as pool:
        decision = pool.submit(finance_review, repo, proposal)
        try:
            assert entered.wait(10)
            revoked = pool.submit(revoke_source)
            assert attempted.wait(10) and not revoked.done()
        finally:
            release.set()
        decision.result(timeout=15)
        revoked.result(timeout=15)
    with pytest.raises(security.ScopeError):
        current(repo, proposal)


def test_attribution_api_bounded_human_writes_and_withdrawal_after_revocation(repo, clock, monkeypatch):
    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    case = complete(repo, clock)
    people = {"operator": OPERATOR, "finance": FINANCE, "model": actor(kind="model")}
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
    path = f"/companies/{COMPANY}/private-attributions"
    stream = path + "/cases/pilot-case/streams/claims"

    def headers(person):
        return {"Authorization": "Bearer " + person}

    try:
        with TestClient(api.app) as client:
            request = body(case).model_dump(mode="json")
            assert client.post(stream, json=request).status_code == 401
            client.cookies.set("pvc_dev_session", "operator")
            assert client.post(stream, json=request).status_code == 403
            client.cookies.clear()
            assert client.post(stream, content=b"private-invalid", headers=headers("model")).status_code == 404
            invalid = client.post(stream, json={"secret": "private-fixture"}, headers=headers("operator"))
            assert invalid.status_code == 422 and "private-fixture" not in invalid.text
            assert client.post(stream, content=b" " * (1024 * 1024 + 1), headers=headers("operator")).status_code == 413
            created = client.post(stream, json=request, headers=headers("operator"))
            assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
            proposal = attribution.PrivateAttribution.model_validate(created.json())
            revision = path + "/revisions/" + proposal.revision_id
            assert client.get(revision + "/usable", headers=headers("operator")).status_code == 422
            assert (
                client.post(revision + "/reviews", content=b"private-invalid", headers=headers("operator")).status_code
                == 404
            )
            accepted_response = client.post(
                revision + "/reviews", json=review_body(proposal).model_dump(mode="json"), headers=headers("finance")
            )
            assert accepted_response.status_code == 201
            accepted = attribution.AttributionReview.model_validate(accepted_response.json())
            usable = client.get(revision + "/usable", headers=headers("operator"))
            assert usable.json()["usable_for_reviewed_attribution"] and not usable.json()["causal_impact_proven"]
            revoke(repo, case.grant)
            assert client.get(revision + "/usable", headers=headers("operator")).status_code == 404
            monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
            withdrew = client.post(
                revision + "/reviews",
                json=review_body(proposal, previous=accepted, decision="withdraw").model_dump(mode="json"),
                headers=headers("finance"),
            )
            assert withdrew.status_code == 201
            assert len(client.get(revision + "/reviews", headers=headers("operator")).json()["reviews"]) == 2
            assert len(client.get(stream, headers=headers("operator")).json()["revisions"]) == 1
    finally:
        api.set_ctx(None)
        api.reset_auth()


def test_attribution_rls_immutability_and_populated_owner_downgrade_guard(pg_repo, pg_database, clock):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    import psycopg
    from psycopg import sql

    from pe_value_os.db.migrate import current as migration_current
    from pe_value_os.db.migrate import downgrade, upgrade

    case = complete(pg_repo, clock)
    proposal = save(pg_repo, case)
    finance_review(pg_repo, proposal)
    tables = ("private_attributions", "private_attribution_reviews")
    with psycopg.connect(pg_database[1], autocommit=True) as conn:
        for table in tables:
            assert conn.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table))).fetchone()[0] == 0
        conn.execute("select set_config('pvc.companies',%s,false)", (COMPANY,))
        for table in tables:
            assert conn.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table))).fetchone()[0] == 1
            for statement in ("delete from {}", "update {} set sequence=99"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql.SQL(statement).format(sql.Identifier(table)))
    parts = urlsplit(pg_database[0])
    options = dict(parse_qsl(parts.query))
    options["options"] = "-crole=pvc_migrator"
    owner_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(options), parts.fragment))
    head = migration_current(pg_database[0])
    downgrade(pg_database[0], "0016")
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
                assert hidden.execute("select count(*) from private_attribution_reviews").fetchone()[0] == 0
            with pytest.raises(RuntimeError, match="Private attribution history"):
                downgrade(owner_url, "0015")
            assert migration_current(pg_database[0]) == "0016"
            for table in tables:
                assert conn.execute(
                    "select relforcerowsecurity from pg_class where oid=%s::regclass", (table,)
                ).fetchone()[0]
        finally:
            for table, owner in owners.items():
                conn.execute(sql.SQL("alter table {} owner to {}").format(sql.Identifier(table), sql.Identifier(owner)))
            upgrade(pg_database[0])
            assert migration_current(pg_database[0]) == head
