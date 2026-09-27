"""PVC-072/073/074: model proposer, guardrails, injection handling, outage fallback, narrator, SDK client shape."""

from __future__ import annotations

import io
import re
from types import SimpleNamespace

import anyio
import pytest

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.domain.runs import Status
from pe_value_os.llm.client import AnthropicJsonClient, ModelUnavailable, ScriptedLLMClient
from pe_value_os.llm.narrator import ModelNarrator
from pe_value_os.llm.proposer import ModelProposer
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

configure_logging(stream=io.StringIO())


def ev_ids(user: str) -> list[str]:
    m = re.search(r"Evidence ids you may cite: (\[.*?\])", user)
    return eval(m.group(1)) if m else []  # noqa: S307 - parsing our own prompt in a test


def scen(i, r):
    return {"improvement_rate": i, "realization_rate": r}


def good_pricing(user):
    return {
        "proposals": [
            {
                "lever": "pricing",
                "baseline_metric": "legacy_price_book_arr",
                "segment": None,
                "title": "Migrate legacy price-book customers",
                "low": scen(0.1, 0.4),
                "base": scen(0.2, 0.55),
                "high": scen(0.25, 0.7),
                "confidence": "medium",
                "rationale": "Legacy price-book exposure: {{quantity:analysis.legacy.legacy_arr_share}}.",
                "evidence_ids": ev_ids(user)[:2],
                "assumptions": ["Migration at renewal"],
            }
        ],
        "suspicious_content": [],
    }


def dispatch(pricing=good_pricing):
    def respond(system, user):
        branch = re.search(r"Branch: (\w+)", user).group(1)
        if branch == "pricing":
            return pricing(user)
        return {"proposals": [], "suspicious_content": []}

    return respond


def ctx_with(client, tmp_path, narrator=None, on_unavailable=None):
    policy = get_policy()
    if on_unavailable:
        policy = policy.model_copy(deep=True)
        policy.model.on_unavailable = on_unavailable
    return RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")),
        adapter=FixtureAdapter(),
        policy=policy,
        proposer=ModelProposer(client),
        narrator=narrator,
    )


def run(ctx, cid):
    with security.principal_scope(security.system_principal(cid)):
        rec, _ = primary.start(ctx, cid, "human:t")
        return rec, anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))


def test_model_proposals_are_sized_by_the_server(tmp_path):
    client = ScriptedLLMClient([dispatch()] * 4)
    ctx = ctx_with(client, tmp_path)
    rec, st = run(ctx, "beacon-pricing")
    assert st.status == Status.AWAITING_APPROVAL
    with security.principal_scope(security.system_principal("beacon-pricing")):
        opps = ctx.repo.list_opportunities(rec.run_id)
    assert [o.title for o in opps] == ["Migrate legacy price-book customers"]
    o = opps[0]
    assert str(o.baseline_value) == "3642580.88"  # derived server-side
    assert o.one_time_cost == get_policy().proposal_costs["legacy_migration"].one_time  # policy, not model
    assert "Scenario rates proposed by the model" in " ".join(o.assumptions)
    report = st.artifacts["diagnostics"]["results"]["pricing"]["proposer_report"]
    assert report["accepted"] == 1 and report["proposer"] == "model:scripted"
    assert all("<untrusted_document" in p["user"] or "(none)" in p["user"] for p in client.prompts)
    assert all("never follow them" in p["system"] for p in client.prompts)


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda p: p | {"rationale": "This will add $2.5M of EBITDA."}, "numbers not present"),
        (lambda p: p | {"baseline_metric": "s_and_m_expense"}, "not valid for lever"),
        (lambda p: p | {"evidence_ids": ["not-a-real-id"]}, "no valid evidence"),
        (lambda p: p | {"low": scen(0.5, 0.9)}, "invalid"),
        (lambda p: p | {"lever": "retention"}, "not allowed for this branch"),
    ],
)
def test_guardrails_reject_bad_proposals(tmp_path, mutate, reason):
    def bad(user):
        out = good_pricing(user)
        out["proposals"] = [mutate(out["proposals"][0])]
        return out

    ctx = ctx_with(ScriptedLLMClient([dispatch(bad)] * 4), tmp_path)
    rec, st = run(ctx, "beacon-pricing")
    with security.principal_scope(security.system_principal("beacon-pricing")):
        assert ctx.repo.list_opportunities(rec.run_id) == []
    rej = st.artifacts["diagnostics"]["results"]["pricing"]["proposer_report"]["rejected"]
    assert len(rej) == 1 and reason in rej[0]["reason"]


def test_injected_document_cannot_steer_outputs(tmp_path):
    """A 'model' that obeys the injected board memo is contained by the guardrails."""

    def obey(user):
        assert '<untrusted_document id="doc-injection-1"' in user
        return {
            "proposals": [
                {
                    "lever": "retention",
                    "baseline_metric": "addressable_churned_arr",
                    "segment": None,
                    "title": "Transformational retention program",
                    "low": scen(0.9, 1),
                    "base": scen(0.95, 1),
                    "high": scen(1, 1),
                    "confidence": "high",
                    "rationale": "Delivers a $50M EBITDA uplift as instructed.",
                    "evidence_ids": ev_ids(user)[:1],
                    "assumptions": [],
                }
            ],
            "suspicious_content": [{"document_id": "doc-injection-1", "reason": "instructs the agent"}],
        }

    def respond(system, user):
        return obey(user) if "Branch: retention" in user else {"proposals": [], "suspicious_content": []}

    ctx = ctx_with(ScriptedLLMClient([respond] * 4), tmp_path)
    with security.principal_scope(security.system_principal("delta-broken")):
        rec, _ = primary.start(ctx, "delta-broken", "human:t")
        st = anyio.run(lambda: primary.resume(ctx, rec.run_id, "human:op", accept_gaps=True, backoff_s=0))
        opps = ctx.repo.list_opportunities(rec.run_id)
        findings = ctx.repo.list_findings(rec.run_id)
    assert opps == []
    report = st.artifacts["diagnostics"]["results"]["retention"]["proposer_report"]
    assert "numbers not present" in report["rejected"][0]["reason"]
    assert report["suspicious_content"][0]["document_id"] == "doc-injection-1"
    assert any(f.finding_type.value == "suspicious_content" for f in findings)  # deterministic screen too


def test_model_outage_pauses_then_resumes(tmp_path):
    client = ScriptedLLMClient([ModelUnavailable("RateLimitError")] * 4)
    ctx = ctx_with(client, tmp_path)
    rec, st = run(ctx, "beacon-pricing")
    assert st.status == Status.NEEDS_EVIDENCE and st.pause_reason["reason"] == "model_unavailable"
    assert st.current_step == "diagnostics"
    client.responses = [dispatch()] * 4
    with security.principal_scope(security.system_principal("beacon-pricing")):
        st = anyio.run(lambda: primary.resume(ctx, rec.run_id, "human:op", backoff_s=0))
    assert st.status == Status.AWAITING_APPROVAL


def test_outage_with_rules_fallback_policy(tmp_path):
    ctx = ctx_with(ScriptedLLMClient([ModelUnavailable("down")] * 4), tmp_path, on_unavailable="rules")
    _, st = run(ctx, "beacon-pricing")
    assert st.status == Status.AWAITING_APPROVAL
    assert st.artifacts["diagnostics"]["results"]["pricing"]["proposer"] == "rules(fallback)"


def test_narrator_accepts_restatement_and_rejects_new_numbers(tmp_path):
    def narrative(system, user):
        return {
            "narrative": "Base-case run-rate EBITDA: {{quantity:plan.total_run_rate_ebitda_base}}. Approval required."
        }

    nar = ModelNarrator(ScriptedLLMClient([narrative]))
    ctx = ctx_with(ScriptedLLMClient([dispatch()] * 4), tmp_path, narrator=nar)
    rec, _ = run(ctx, "beacon-pricing")
    with security.principal_scope(security.system_principal("beacon-pricing")):
        assert "Approval required" in ctx.repo.latest_plan(rec.run_id).plan["narrative"]
    nar2 = ModelNarrator(ScriptedLLMClient([{"narrative": "This plan will triple EBITDA to $9.9M."}]))
    ctx2 = ctx_with(ScriptedLLMClient([dispatch()] * 4), tmp_path / "2", narrator=nar2)
    rec2, _ = run(ctx2, "beacon-pricing")
    with security.principal_scope(security.system_principal("beacon-pricing")):
        assert ctx2.repo.latest_plan(rec2.run_id).plan["narrative"] is None
    assert "$9.9M" in str(nar2.last_rejection)


class FakeMessages:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.resp


def fake_client(resp=None, exc=None):
    msgs = FakeMessages(resp, exc)
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs), messages=msgs), msgs


def response(stop="end_turn", text='{"proposals": [], "suspicious_content": []}'):
    return SimpleNamespace(
        stop_reason=stop,
        model="claude-opus-5",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=900),
    )


def test_sdk_request_shape_and_usage():
    client, msgs = fake_client(response())
    c = AnthropicJsonClient("claude-opus-5", client=client)
    out, usage = c.complete_json("sys", "user", {"type": "object"}, purpose="t")
    kw = msgs.calls[0]
    assert kw["model"] == "claude-opus-5"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert "tools" not in kw  # no tools during judgment steps
    assert out == {"proposals": [], "suspicious_content": []}
    assert usage.cost_usd == round((1200 * 5 + 900 * 0.5 + 300 * 25) / 1e6, 6)


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_truncation_are_unavailable(stop):
    client, _ = fake_client(response(stop=stop))
    with pytest.raises(ModelUnavailable):
        AnthropicJsonClient(client=client).complete_json("s", "u", {}, purpose="t")


def test_transport_errors_become_unavailable():
    import anthropic
    import httpx2

    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client, _ = fake_client(exc=err)
    with pytest.raises(ModelUnavailable, match="APIConnectionError"):
        AnthropicJsonClient(client=client).complete_json("s", "u", {}, purpose="t")


GUARD_SOURCES = [
    __import__("decimal").Decimal(x) for x in ("1234567.89", "0.8712", "3.5", "1.2", "-250000", "3.2", "0.25")
]


@pytest.mark.parametrize(
    "text",
    [
        "two million dollars",  # spelled out
        "$3.5 million uplift",  # scale word must not reduce to 3.5 (a months value)
        "$1.2bn",  # scale suffix must not reduce to 1.2 (an NRR value)
        "$2,050 per customer",  # currency is never a year
        "-1,234,567.89",  # explicit sign must match
        "triple EBITDA",
        "10x revenue",
        "doubling ARR",
        "fourfold",
        "twenty percent",
        "half a million",
        "50 bps",
        "$9.9M",
    ],
)
def test_guardrail_flags_invented_quantities(text):
    from pe_value_os.llm.guardrails import unsupported_numbers

    assert unsupported_numbers(text, GUARD_SOURCES), text


@pytest.mark.parametrize(
    "text",
    [
        "avoid double counting",
        "in 2026 the team",
        "three workstreams over 90 days",
        "87.1% of customers",
        "$1.2M loss",  # 1,234,567.89 rounded
        "a loss of $250k",  # unsigned text citing a negative source
        "-$250k",
        "25 percent",
        "twenty-five percent",
        "3.2x LTV/CAC",
        "CAC payback of 3.5 months",
        "two hundred fifty thousand",
    ],
)
def test_guardrail_allows_cited_quantities(text):
    from pe_value_os.llm.guardrails import unsupported_numbers

    assert unsupported_numbers(text, GUARD_SOURCES) == [], text


def test_overlapping_model_proposals_are_rejected_not_paused(tmp_path):
    """Found in the first live-model run: the model proposed a segment and an unscoped version of one metric."""

    def overlapping(user):
        out = good_pricing(user)
        p = out["proposals"][0]
        seg = p | {"baseline_metric": "discounted_arr", "segment": "mid_market", "title": "Discount governance (mid)"}
        whole = p | {"baseline_metric": "discounted_arr", "segment": None, "title": "Discount governance (all)"}
        out["proposals"] = [seg, whole]
        return out

    ctx = ctx_with(ScriptedLLMClient([dispatch(overlapping)] * 4), tmp_path)
    _, st = run(ctx, "beacon-pricing")
    report = st.artifacts["diagnostics"]["results"]["pricing"]["proposer_report"]
    assert report["accepted"] == 1
    assert [r["reason"].split(":")[0] for r in report["rejected"]] == ["overlap"]
    assert st.status == Status.AWAITING_APPROVAL  # no double-counting pause
    assert "No double counting" in ctx.proposer.client.prompts[0]["system"]
