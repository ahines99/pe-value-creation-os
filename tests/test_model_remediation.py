"""Regression evidence for A02/A06/A10/A20/A21/A23, using offline clients only."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import anyio
import pytest
from mcp import Client

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.domain.project_models import Lever
from pe_value_os.evals import harness
from pe_value_os.llm.client import AnthropicJsonClient, ModelUnavailable, ScriptedLLMClient, Usage, usage_scope
from pe_value_os.llm.eligibility import branch_context, eligibility_error
from pe_value_os.llm.guardrails import source_numbers, unsupported_numbers
from pe_value_os.llm.proposer import ModelProposer
from pe_value_os.llm.quantities import render_claims, source_quantities
from pe_value_os.mcp_server import build_server
from pe_value_os.policy import get_policy
from pe_value_os.tools import _runtime
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext


@pytest.mark.parametrize(
    "text", ["Revenue is 2e9 dollars", ".99 billion dollars", "ARR is 100 dollars", "Profit is 2026 dollars"]
)
def test_ordinary_numeric_notation_is_not_structural(text):
    assert unsupported_numbers(text, [])


def test_ids_and_numeric_strings_are_not_typed_numeric_evidence():
    assert source_numbers({"id": "evidence-987654", "claim": "$987654", "string": "987654"}) == []
    facts = source_quantities(
        {"arr": Decimal("987654"), "id": "evidence-987654"}, company_id="a", evidence_ids=["ev"], period="2026-08"
    )
    assert set(facts) == {"analysis.arr"}
    with pytest.raises(ValueError, match="bound tool output"):
        render_claims("EBITDA is $987654", facts)
    rendered = render_claims("Observed ARR: {{quantity:analysis.arr}}", facts)
    assert "analysis.arr: 987654" in rendered and "company=a" in rendered and "period=2026-08" in rendered
    with pytest.raises(ValueError, match="unknown numeric source"):
        render_claims("{{quantity:other.arr}}", facts)


def test_healthy_company_cannot_receive_false_positive_proposal():
    data = FixtureAdapter().load("acme-healthy")
    ctx = branch_context(data, "pricing", get_policy())
    response = {
        "proposals": [
            harness._proposal("", "pricing", "legacy_price_book_arr", "Migration", "Legacy migration may help.")
        ],
        "suspicious_content": [],
    }
    response["proposals"][0]["evidence_ids"] = ctx.evidence_ids[:1]
    assert ModelProposer(ScriptedLLMClient([response])).propose(ctx) == []
    assert "threshold breach" in ctx.report["rejected"][0]["reason"]


def test_aggregate_baselines_keep_policy_screening_support():
    data = FixtureAdapter().load("beacon-pricing")
    ctx = branch_context(data, "pricing", get_policy())
    assert eligibility_error(ctx, Lever.PRICING, "total_arr", {}) is None
    healthy = branch_context(FixtureAdapter().load("acme-healthy"), "pricing", get_policy())
    assert eligibility_error(healthy, Lever.PRICING, "total_arr", {})


def test_company_document_exclusion_happens_before_model_call(monkeypatch):
    ctx = branch_context(FixtureAdapter().load("beacon-pricing"), "pricing", get_policy())
    ctx.documents = [{"document_id": "d", "title": "restricted", "text": "EXCLUDED_DOCUMENT_SENTINEL"}]
    monkeypatch.setenv("PVC_MODEL_DOCUMENT_EXCLUDED_COMPANIES", "beacon-pricing")
    client = ScriptedLLMClient([{"proposals": [], "suspicious_content": []}])
    ModelProposer(client).propose(ctx)
    assert "EXCLUDED_DOCUMENT_SENTINEL" not in client.prompts[0]["user"]
    assert ctx.report["documents_excluded"] == 1


def test_cache_creation_reads_and_rejected_attempts_are_durable(tmp_path):
    cid = "beacon-pricing"
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path)), adapter=FixtureAdapter(), policy=get_policy()
    )
    response = SimpleNamespace(
        model="claude-opus-5",
        stop_reason="refusal",
        content=[],
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=50,
            cache_creation_input_tokens=80,
            cache_creation=SimpleNamespace(ephemeral_1h_input_tokens=30),
        ),
    )
    api = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
    client = AnthropicJsonClient(client=api, use_fallbacks=False)
    with security.principal_scope(security.system_principal(cid)):
        run, _ = primary.start(ctx, cid, "test")
        for _ in range(2):
            with usage_scope(ctx.repo, run.run_state(), "test"), pytest.raises(ModelUnavailable):
                client.complete_json("system", "user", {}, purpose="narrative")
        events = [e for e in ctx.repo.list_audit(run_id=run.run_id) if e.event_type == "model_usage"]
    expected = Usage("claude-opus-5", 100, 20, 50, 80, 30)
    assert expected.total_tokens == 250
    assert expected.cost_usd == round((100 * 5 + 20 * 25 + 50 * 0.5 + 50 * 5 * 1.25 + 30 * 5 * 2) / 1e6, 6)
    assert len(events) == 2 and sum(e.payload["total_tokens"] for e in events) == 500
    assert all(e.payload["cost_usd"] == expected.cost_usd for e in events)
    assert len({e.payload["call_id"] for e in events}) == 2


def test_model_gate_checks_negative_outcomes_and_missing_evidence():
    base = {
        "case": "healthy",
        "opportunities": [{"lever": "pricing"}],
        "accepted": 1,
        "rejected": [],
        "model_cost_usd": 0.01,
        "evidence_fidelity": True,
        "calculation_fidelity": True,
        "permission_fidelity": True,
        "checks": [{"key": "no_opportunities", "ok": False}],
        "has_plan": True,
        "narrator_reports": [{"status": "accepted"}],
        "usage_complete": True,
    }
    ms = harness.model_scores([base], {"healthy": {"expect": {"no_opportunities": True}}})
    failures = harness.model_gate(ms, {})
    assert any("negative_control_precision" in f for f in failures)
    assert any("outcome_validity" in f for f in failures)
    assert harness.model_gate({}, {}) and harness.gate({}, {})


@pytest.mark.parametrize(
    "suites,ids", [(["golden"], {"NOT_A_CASE"}), (["golden"], set()), (["golden", "adversarial"], {"G01"}), ([], None)]
)
def test_eval_rejects_unknown_empty_or_unexecuted_requested_suites(suites, ids):
    with pytest.raises(ValueError):
        harness.run_suites(suites, case_ids=ids)


def test_narrator_is_exercised_and_billed_by_harness():
    case = {
        "id": "N01",
        "company": {"fixture": "beacon-pricing"},
        "proposer": "scripted:invent_numbers",
        "narrator": "scripted:invent_numbers",
        "expect": {"narrative_rejected": True},
    }
    result = harness.run_case(case)
    assert result["passed"]
    assert result["branch_model_usage"]["narrative"]["calls"] == 1
    assert result["model_tokens"] == sum(u["tokens"] for u in result["branch_model_usage"].values())


def test_interactive_duplicate_and_invented_claim_cannot_reach_approval(tmp_path):
    cid = "beacon-pricing"
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path)), adapter=FixtureAdapter(), policy=get_policy()
    )
    _runtime.set_ctx(ctx)

    async def exercise():
        async with Client(build_server()) as client:
            started = await client.call_tool("start_diagnostic_run", {"company_id": cid, "mode": "interactive"})
            run_id = started.structured_content["run_id"]
            ev = (await client.call_tool("price_waterfall", {"company_id": cid})).structured_content["evidence_ids"]
            args = {
                "run_id": run_id,
                "lever": "pricing",
                "baseline_metric": "legacy_price_book_arr",
                "title": "Migration",
                "low": harness._scen(0.1, 0.4),
                "base": harness._scen(0.2, 0.55),
                "high": harness._scen(0.25, 0.7),
                "confidence": "medium",
                "rationale": "Legacy share above policy",
                "evidence_ids": ev,
            }
            bad = await client.call_tool("propose_opportunity", args | {"rationale": "Guaranteed $999 billion uplift"})
            assert bad.is_error and ctx.repo.list_opportunities(run_id) == []
            first = await client.call_tool("propose_opportunity", args)
            assert not first.is_error
            duplicate = await client.call_tool("propose_opportunity", args)
            assert duplicate.is_error and len(ctx.repo.list_opportunities(run_id)) == 1
            oid = first.structured_content["opportunity_id"]
            await client.call_tool("size_value_case", {"company_id": cid, "opportunity_id": oid})
            await client.call_tool("prioritize_opportunities", {"run_id": run_id})
            draft = await client.call_tool("draft_100_day_plan", {"run_id": run_id})
            assert not draft.is_error
            # Prove the submission boundary rechecks persisted state, even if a
            # legacy record bypassed the newly hardened proposal tool.
            original = ctx.repo.get_opportunity(cid, oid)
            ctx.repo.add_opportunity(
                original.model_copy(update={"opportunity_id": "legacy-duplicate"}),
                proposer="legacy",
                flow_through_rule="test",
            )
            submit = await client.call_tool("request_approval", {"run_id": run_id})
            assert submit.is_error and ctx.repo.list_approvals(run_id) == []

    try:
        with security.principal_scope(security.system_principal(cid)):
            anyio.run(exercise)
    finally:
        _runtime.set_ctx(None)
