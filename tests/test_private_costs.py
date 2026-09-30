"""Hand-worked delivery-to-ledger matches; no actual company cost claim."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, localcontext

import pytest

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.diligence import private_costs as costs
from tests.test_private_attribution import clock as attribution_clock  # noqa: F401
from tests.test_private_attribution import complete
from tests.test_private_execution import binding, evidence
from tests.test_private_observations import clock as measurement_clock  # noqa: F401
from tests.test_private_records import COMPANY, ENV, OPERATOR, actor, review


@pytest.fixture
def memory(tmp_path):
    return InMemoryRepository(FileSystemEvidenceStore(tmp_path / "evidence"))


@pytest.fixture
def case(memory, request, monkeypatch):
    clock = request.getfixturevalue("attribution_clock")

    class Clock(datetime):
        @classmethod
        def now(cls, zone):
            return clock.value

    monkeypatch.setattr(costs, "datetime", Clock)
    return complete(memory, clock)


def context(memory, case):
    with security.principal_scope(OPERATOR):
        return costs.CostSourceContext(
            record=case.actual.source,
            raw=case.actual.raw,
            grants=memory.list_private_grants(COMPANY, "actuals"),
            reviews=memory.list_private_finance_reviews(COMPANY, case.actual.source.intake_id),
            current=case.actual.source,
        )


def allocation(case, *, event=None, row="fixture-3", amount="10"):
    return costs.CostAllocation(
        delivery=binding(event or case.foundation_work),
        intake_id=case.actual.source.intake_id,
        source_row_id=row,
        cost_amount=amount,
        evidence=evidence(),
        scope_and_timing_assessment="Fictional November recognition of October work; no invoice verification",
    )


def body(case, allocations=None):
    return costs.CostReconciliationRequest(
        idempotency_key="costs",
        expected_previous_sha256=None,
        expected_baseline_sha256=case.baseline.content_sha256,
        expected_execution_head_sha256=case.events[-1].content_sha256,
        sources=(
            costs.CostSourceBinding(
                intake_id=case.actual.source.intake_id,
                intake_sha256=case.actual.source.content_sha256,
                finance_review_sha256=case.actual.review.content_sha256,
                grant_sha256=case.actual.grant.content_sha256,
            ),
        ),
        allocations=tuple(allocations)
        if allocations is not None
        else (
            allocation(case),
            allocation(case, event=case.gate_work, row="fixture-6", amount="20"),
        ),
        cost_basis="expense_and_capex_cash_with_explicit_report_comparability",
        reported_cost_basis_assessment="Fictional reports compared to expense and capex payments separately; no asset-addition assertion",
        scope_and_completeness_assessment="Supplied company ledger also contains unrelated expenses",
        rationale="Fictional cost comparison for later independent review",
    )


def calculate(memory, case, request=None, sources=None, person=OPERATOR):
    contexts = sources if sources is not None else [context(memory, case)]
    with security.principal_scope(person):
        return costs.calculate_cost_reconciliation(
            request or body(case), case.baseline, case.plan, case.events, contexts, ENV
        )


def test_cost_match_retains_expense_capex_residuals_without_posting_again(memory, case):
    with localcontext() as decimal_context:
        decimal_context.prec = 3
        result = calculate(memory, case)
    assert (result.reported_cost, result.matched_expense, result.matched_capex_cash) == (30, 10, 20)
    assert result.reported_less_matched == 0 and result.all_reported_costs_matched
    assert {r["source_row_id"] for r in result.ledger_rows} == {"fixture-2", "fixture-3", "fixture-6"}
    assert sum(r["unassigned_ledger_cost"] for r in result.ledger_rows) == 460
    assert not result.finance_reviewed and not result.all_project_costs_captured
    assert not result.additional_ebitda_or_cash_posting and not result.cross_stream_reservations_checked
    with pytest.raises(ValueError, match="public"):
        result.require_public()


def test_unmatched_costs_remain_visible_and_segment_errors_cannot_net(memory, case):
    empty = calculate(memory, case, body(case, []))
    assert empty.reported_less_matched == 30 and not empty.all_reported_costs_matched
    request = body(case, [allocation(case, amount="20"), allocation(case, event=case.gate_work)])
    result = calculate(memory, case, request)
    assert result.reported_less_matched == 0 and not result.all_reported_costs_matched
    assert [r["reported_less_matched"] for r in result.deliveries] == [-10, 10]


@pytest.mark.parametrize(
    "problem",
    ["row", "cash", "sign", "overuse", "delivery", "head", "baseline", "source", "review", "grant", "duplicate"],
)
def test_rejects_wrong_versions_and_unsupported_allocations(memory, case, problem):
    request = body(case)
    if problem in {"row", "cash", "sign", "overuse", "delivery"}:
        a = allocation(case)
        updates = {
            "row": {"source_row_id": "missing"},
            "cash": {"source_row_id": "fixture-4"},
            "sign": {"cost_amount": Decimal("-10")},
            "overuse": {"cost_amount": Decimal("51")},
            "delivery": {"delivery": binding(case.foundation)},
        }[problem]
        request = request.model_copy(update={"allocations": (a.model_copy(update=updates),)})
    elif problem in {"head", "baseline"}:
        field = "expected_execution_head_sha256" if problem == "head" else "expected_baseline_sha256"
        request = request.model_copy(update={field: "f" * 64})
    elif problem in {"source", "review", "grant"}:
        field = {"source": "intake_sha256", "review": "finance_review_sha256", "grant": "grant_sha256"}[problem]
        request = request.model_copy(update={"sources": (request.sources[0].model_copy(update={field: "f" * 64}),)})
    else:
        request = request.model_copy(update={"allocations": (request.allocations[0], request.allocations[0])})
    with pytest.raises(ValueError):
        calculate(memory, case, request)


def test_rejects_tampered_bytes_withdrawn_source_and_model_identity(memory, case):
    source = context(memory, case)
    with pytest.raises(ValueError, match="no longer matches"):
        calculate(memory, case, sources=[replace(source, raw=source.raw + b" ")])
    with pytest.raises(security.ScopeError):
        calculate(memory, case, person=actor(kind="model"))
    review(
        memory, case.actual.source, case.actual.grant, decision="withdraw", previous=case.actual.review, key="withdraw"
    )
    with pytest.raises(ValueError, match="current finance acceptance"):
        calculate(memory, case)


def test_credit_allocation_keeps_signed_row_limits(memory, case):
    ledger = json.loads(case.actual.raw)
    charge = next(row for row in ledger["rows"] if row["source_row_id"] == "fixture-3")
    charge["amount"] = "60"
    ledger["rows"].append({**charge, "source_row_id": "cost-credit", "amount": "-10"})
    raw = json.dumps(ledger).encode()
    original = case.actual.source
    manifest = original.request.manifest.model_copy(
        update={"source_sha256": hashlib.sha256(raw).hexdigest(), "record_count": 8}
    )
    request = original.request.model_copy(
        update={"idempotency_key": "credit", "expected_previous_sha256": original.content_sha256, "manifest": manifest}
    )
    with security.principal_scope(OPERATOR):
        case.actual.source = memory.record_private_intake(COMPANY, "actuals", request, raw, ENV)
    case.actual.raw = raw
    case.actual.review = review(memory, case.actual.source, case.actual.grant)
    request = body(
        case,
        [
            allocation(case, amount="20"),
            allocation(case, row="cost-credit", amount="-10"),
            allocation(case, event=case.gate_work, amount="20"),
        ],
    )
    result = calculate(memory, case, request)
    assert result.matched_expense == 30 and result.all_reported_costs_matched
    credit = next(row for row in result.ledger_rows if row["source_row_id"] == "cost-credit")
    assert credit["matched_cost"] == -10 and credit["unassigned_ledger_cost"] == 0
    too_much = request.model_copy(
        update={
            "allocations": (
                *request.allocations,
                allocation(case, event=case.gate_work, row="cost-credit", amount="-1"),
            )
        }
    )
    with pytest.raises(ValueError, match="exceed"):
        calculate(memory, case, too_much)


def test_changed_export_bytes_do_not_duplicate_a_logical_cost_pool(memory, case):
    original = case.actual.source
    raw = case.actual.raw + b"\n"
    manifest = original.request.manifest.model_copy(
        update={"source_sha256": hashlib.sha256(raw).hexdigest(), "export_id": "duplicate-export"}
    )
    request = original.request.model_copy(update={"idempotency_key": "alias", "manifest": manifest})
    with security.principal_scope(OPERATOR):
        alias = memory.record_private_intake(COMPANY, "alias", request, raw, ENV)
    accepted = review(memory, alias, case.actual.grant)
    source = context(memory, case)
    alias_context = costs.CostSourceContext(alias, raw, source.grants, [accepted], alias)
    request = body(case)
    alias_binding = costs.CostSourceBinding(
        intake_id=alias.intake_id,
        intake_sha256=alias.content_sha256,
        finance_review_sha256=accepted.content_sha256,
        grant_sha256=case.actual.grant.content_sha256,
    )
    request = request.model_copy(update={"sources": (*request.sources, alias_binding)})
    with pytest.raises(ValueError, match="logical cost row"):
        calculate(memory, case, request, [source, alias_context])


@pytest.mark.parametrize("amount", [0, 1.5, True, "NaN", "Infinity"])
def test_cost_allocation_requires_nonzero_exact_amount(amount):
    with pytest.raises(ValueError):
        costs.CostAllocation(
            delivery={"event_id": "00000000-0000-0000-0000-000000000001", "sha256": "a" * 64},
            intake_id="00000000-0000-0000-0000-000000000002",
            source_row_id="row",
            cost_amount=amount,
            scope_and_timing_assessment="Fictional",
            evidence=evidence(),
        )
