"""PVC-050..058, PVC-121: MCP tools, resources and prompts through the in-process client."""

from __future__ import annotations

import io
import json

import pytest
from mcp import Client

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.mcp_server import build_server
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.tools import _runtime
from pe_value_os.workflows.steps import RunContext

pytestmark = pytest.mark.anyio
configure_logging(stream=io.StringIO())

ALL = ("acme-healthy", "beacon-pricing", "cedar-churn", "delta-broken")


@pytest.fixture
def ctx(tmp_path):
    c = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")),
        adapter=FixtureAdapter(),
        policy=get_policy(),
        actor="mcp",
    )
    _runtime.set_ctx(c)
    yield c
    _runtime.set_ctx(None)


@pytest.fixture
def server(ctx):
    return build_server()


def as_(*companies, kind="model"):
    return security.principal_scope(
        security.Principal(subject=f"{kind}:tester", companies=frozenset(companies), principal_type=kind)
    )


async def call(client, name, args):
    r = await client.call_tool(name, args)
    return r


def text(r):
    return " ".join(getattr(c, "text", "") for c in r.content)


async def test_healthcheck(server):
    async with Client(server) as c:
        r = await c.call_tool("healthcheck", {})
        assert r.is_error is False
        assert r.structured_content == {"status": "ok", "version": "0.1.0"}


READ_TOOLS = [
    ("get_company_profile", {}),
    ("get_financials", {"period_start": "2025-09", "period_end": "2026-08"}),
    ("get_churn_summary", {}),
    ("get_usage_metrics", {"period": "2026-08"}),
    ("get_support_metrics", {}),
    ("price_waterfall", {"segment": "mid_market"}),
    ("check_data_sufficiency", {"analysis": "pricing"}),
    ("compute_saas_metrics", {"period": "2026-08"}),
    ("compute_retention_cohorts", {}),
    ("get_kpi_status", {}),
]


@pytest.mark.parametrize("tool,args", READ_TOOLS, ids=[t for t, _ in READ_TOOLS])
async def test_read_tools_success_and_scope(server, tool, args):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            ok = await c.call_tool(tool, {"company_id": "beacon-pricing", **args})
            assert ok.is_error is False, text(ok)
            assert ok.structured_content is not None
            denied = await c.call_tool(tool, {"company_id": "cedar-churn", **args})
            assert denied.is_error and "Access denied" in text(denied)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("get_financials", {"company_id": "beacon-pricing", "period_end": "last year"}),
        ("check_data_sufficiency", {"company_id": "beacon-pricing", "analysis": "vibes"}),
        ("compute_retention_cohorts", {"company_id": "beacon-pricing", "cohort_grain": "decade"}),
        ("get_benchmarks", {"metric": "grr", "peer_set": "vertical_saas_smb_heavy"}),
        ("get_benchmarks", {"metric": "made_up", "peer_set": "b2b_saas_10_50m_arr"}),
        ("price_waterfall", {"company_id": "beacon-pricing", "period": "2026-13"}),
    ],
)
async def test_invalid_arguments_are_errors(server, tool, args):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            r = await c.call_tool(tool, args)
            assert r.is_error


async def test_sufficiency_reports_gaps_for_broken_company(server):
    with as_("delta-broken"):
        async with Client(server) as c:
            r = await c.call_tool("check_data_sufficiency", {"company_id": "delta-broken", "analysis": "pricing"})
            assert r.structured_content["status"] == "INSUFFICIENT"
            assert {g["code"] for g in r.structured_content["gaps"]} >= {"missing_dataset", "stale_dataset"}


async def test_benchmarks_return_distribution_only(server):
    async with Client(server) as c:
        r = await c.call_tool("get_benchmarks", {"metric": "grr", "peer_set": "b2b_saas_10_50m_arr"})
        assert set(r.structured_content) >= {"p25", "p50", "p75", "n", "synthetic", "dataset_sha256"}
        assert r.structured_content["synthetic"] is True


async def _interactive_run(c, company):
    r = await c.call_tool("start_diagnostic_run", {"company_id": company, "mode": "interactive"})
    assert r.is_error is False, text(r)
    return r.structured_content["run_id"]


def scen(i, r):
    return {"improvement_rate": i, "realization_rate": r}


async def test_propose_rejects_caller_supplied_baseline(server):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            run_id = await _interactive_run(c, "beacon-pricing")
            args = {
                "run_id": run_id,
                "lever": "pricing",
                "baseline_metric": "legacy_price_book_arr",
                "title": "Legacy migration",
                "low": scen("0.1", "0.4"),
                "base": scen("0.2", "0.55"),
                "high": scen("0.25", "0.7"),
                "confidence": "medium",
                "rationale": "legacy share high",
                "evidence_ids": [],
            }
            with pytest.raises(Exception, match=r"does not accept arguments .*baseline_value"):
                await c.call_tool("propose_opportunity", {**args, "baseline_value": "999999999"})
            with pytest.raises(Exception, match="ebitda_flow_through"):
                await c.call_tool("propose_opportunity", {**args, "ebitda_flow_through": "1"})


async def test_record_finding_enforces_citations(server):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            run_id = await _interactive_run(c, "beacon-pricing")
            r = await c.call_tool(
                "record_finding",
                {
                    "run_id": run_id,
                    "finding_type": "value_claim",
                    "title": "t",
                    "statement": "s",
                    "confidence": "high",
                    "evidence_ids": [],
                },
            )
            assert r.is_error and "PolicyViolation" in text(r)


async def test_mutating_tools_write_audit(server, ctx):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            run_id = await _interactive_run(c, "beacon-pricing")
            ev = (await c.call_tool("get_company_profile", {"company_id": "beacon-pricing"})).structured_content
            await c.call_tool(
                "record_finding",
                {
                    "run_id": run_id,
                    "finding_type": "observation",
                    "title": "t",
                    "statement": "s",
                    "confidence": "low",
                    "evidence_ids": ev["evidence_ids"],
                },
            )
        events = [e.event_type for e in ctx.repo.list_audit(run_id=run_id)]
        assert "finding_recorded" in events
        assert all(e.actor == "model:tester" for e in ctx.repo.list_audit(run_id=run_id) if e.step.startswith("tool:"))


async def test_no_tool_can_record_an_approval_decision(server, ctx):
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert not {n for n in names if any(w in n for w in ("approve", "decide", "decision", "reject"))}
    with as_("beacon-pricing"):
        async with Client(server) as c:
            run_id = await _golden_pricing_flow(c)
            for name in names:
                try:
                    await c.call_tool(name, {"run_id": run_id, "company_id": "beacon-pricing"})
                except Exception:  # noqa: S110 - strict-argument rejections are expected for many tools
                    pass
        assert all(a.decision is None for a in ctx.repo.list_approvals(run_id))


async def _golden_pricing_flow(c) -> str:
    """Skill-driven flow: interactive run -> findings -> proposal -> sizing -> priorities -> plan -> approval."""
    run_id = await _interactive_run(c, "beacon-pricing")
    pw = (await c.call_tool("price_waterfall", {"company_id": "beacon-pricing"})).structured_content
    ev = pw["evidence_ids"]
    f = await c.call_tool(
        "record_finding",
        {
            "run_id": run_id,
            "finding_type": "observation",
            "title": "Legacy price books",
            "statement": f"{pw['legacy']['legacy_arr_share']} of ARR on legacy price books",
            "confidence": "high",
            "evidence_ids": ev,
        },
    )
    assert f.is_error is False, text(f)
    o = await c.call_tool(
        "propose_opportunity",
        {
            "run_id": run_id,
            "lever": "pricing",
            "baseline_metric": "legacy_price_book_arr",
            "title": "Migrate legacy price-book customers",
            "low": scen("0.1", "0.4"),
            "base": scen("0.2", "0.55"),
            "high": scen("0.25", "0.7"),
            "confidence": "medium",
            "rationale": "Legacy share above policy",
            "evidence_ids": ev,
            "one_time_cost": "75000",
        },
    )
    assert o.is_error is False, text(o)
    opp = o.structured_content
    assert opp["baseline_value"] == pw["legacy"]["legacy_arr"]  # server-derived, not caller-supplied
    vc = await c.call_tool(
        "size_value_case",
        {"company_id": "beacon-pricing", "opportunity_id": opp["opportunity_id"], "ev_multiple": "10"},
    )
    assert vc.is_error is False and vc.structured_content["calc_version"] == "value-case/1"
    ev_list = await c.call_tool(
        "list_evidence", {"company_id": "beacon-pricing", "opportunity_id": opp["opportunity_id"]}
    )
    assert {e["evidence_id"] for e in ev_list.structured_content["result"]} >= set(ev)
    pr = await c.call_tool("prioritize_opportunities", {"run_id": run_id})
    assert pr.structured_content["result"][0]["rank"] == 1
    plan = await c.call_tool("draft_100_day_plan", {"run_id": run_id})
    assert plan.is_error is False and plan.structured_content["workstreams"]
    req = await c.call_tool("request_approval", {"run_id": run_id})
    assert req.structured_content["status"] == "awaiting_approval"
    return run_id


async def test_golden_1_interactive_pricing_flow(server, ctx):
    with as_("beacon-pricing"):
        async with Client(server) as c:
            run_id = await _golden_pricing_flow(c)
            st = await c.call_tool("get_run_status", {"run_id": run_id})
            assert st.structured_content["status"] == "awaiting_approval"


async def test_golden_2_automated_run_via_worker(server, ctx):
    from pe_value_os.worker import Worker

    with as_("cedar-churn"):
        async with Client(server) as c:
            r = await c.call_tool("start_diagnostic_run", {"company_id": "cedar-churn", "idempotency_key": "g2"})
            run_id = r.structured_content["run_id"]
            assert r.structured_content["status"] == "pending"
    await Worker(ctx, frozenset({"cedar-churn"})).run_queue()
    with as_("cedar-churn"):
        async with Client(server) as c:
            st = (await c.call_tool("get_run_status", {"run_id": run_id})).structured_content
            assert st["status"] == "awaiting_approval"
            summary = await c.read_resource(f"run://{run_id}/summary")
            data = json.loads(summary.contents[0].text)
            assert {o["lever"] for o in data["opportunities"]} >= {"retention"}


async def test_golden_3_broken_company_is_explicit_about_gaps(server):
    with as_("delta-broken"):
        async with Client(server) as c:
            fin = await c.call_tool("get_financials", {"company_id": "delta-broken"})
            assert len(fin.structured_content["missing_months"]) == 2  # third gap is outside the default window
            m = await c.call_tool("compute_saas_metrics", {"company_id": "delta-broken"})
            gm = m.structured_content["metrics"]["subscription_gross_margin"]
            assert gm["value"] is None and "missing months" in gm["note"]


async def test_golden_4_retention_proposal_sized_from_company_data(server):
    with as_("cedar-churn"):
        async with Client(server) as c:
            run_id = await _interactive_run(c, "cedar-churn")
            ra = (await c.call_tool("compute_retention_cohorts", {"company_id": "cedar-churn"})).structured_content
            assert ra["involuntary_payment_share"] is not None
            o = await c.call_tool(
                "propose_opportunity",
                {
                    "run_id": run_id,
                    "lever": "retention",
                    "baseline_metric": "failed_payment_churned_arr",
                    "title": "Dunning",
                    "low": scen("0.3", "0.6"),
                    "base": scen("0.45", "0.75"),
                    "high": scen("0.6", "0.85"),
                    "confidence": "medium",
                    "rationale": "failed payments",
                    "evidence_ids": ra["evidence_ids"],
                },
            )
            assert o.structured_content["ebitda_flow_through"] != "1"  # gross-margin flow-through for retention
            bad = await c.call_tool(
                "propose_opportunity",
                {
                    "run_id": run_id,
                    "lever": "retention",
                    "baseline_metric": "s_and_m_expense",
                    "title": "Wrong metric",
                    "low": scen("0.1", "0.5"),
                    "base": scen("0.1", "0.5"),
                    "high": scen("0.1", "0.5"),
                    "confidence": "low",
                    "rationale": "x",
                    "evidence_ids": ra["evidence_ids"],
                },
            )
            assert bad.is_error and "not a valid baseline" in text(bad)


async def test_golden_5_resources_and_prompt(server):
    with as_("acme-healthy"):
        async with Client(server) as c:
            pol = await c.read_resource("project://policies")
            assert "No uncited value claim" in pol.contents[0].text and "Policy version" in pol.contents[0].text
            inv = json.loads((await c.read_resource("company://acme-healthy/data-inventory")).contents[0].text)
            assert {d["kind"] for d in inv["datasets"]} >= {"pnl", "arr", "invoices"}
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            assert "review_run" in prompts
            p = await c.get_prompt("review_run", {"run_id": "abc"})
            assert "Do not approve" in p.messages[0].content.text
            with pytest.raises(Exception):  # noqa: B017 - scope violation on a resource
                await c.read_resource("company://beacon-pricing/data-inventory")
