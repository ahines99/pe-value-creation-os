"""Signed claims reconcile; fictional acceptance never establishes causal impact."""

from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.diligence import private_attribution as attribution
from pe_value_os.diligence import private_execution as execution
from pe_value_os.diligence.private_records import content_hash
from tests.test_private_execution import acceptance, at, authorize, binding, delivery, evidence, record
from tests.test_private_observations import actuals, observation_request, setup
from tests.test_private_observations import clock as measurement_clock  # noqa: F401
from tests.test_private_records import COMPANY, ENV, FINANCE, OPERATOR

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
