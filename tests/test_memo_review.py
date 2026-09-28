"""A source correction must change the executive choice, not just an appendix."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.diligence.cases import digest
from pe_value_os.diligence.memo import assemble_memo
from pe_value_os.diligence.memo_render import build_decision_memo, incremental_waterfall, render_memo
from pe_value_os.diligence.memo_review import MemoReviewContext
from pe_value_os.diligence.scheduling import fingerprint

from .test_decision_memo import PATHS, inputs, scenario

SOURCE = Path("docs/portfolio/source-review.json")


def context():
    return MemoReviewContext.from_export(json.loads(SOURCE.read_text(encoding="utf-8")))


def test_latest_evidence_reopens_original_preference_and_preserves_public_facts():
    data, ctx = inputs(), context()
    before = [m.model_dump_json() for m in [*data, ctx]]
    original = assemble_memo(*data)
    report = assemble_memo(*data, ctx)
    assert report["memo_version"] == "executive-decision-packet/3"
    assert report["preference_status"] == "reopen_source_constrained_preference"
    review = report["source_review"]
    assert review["all_base_year_one_nonpositive"]
    assert review["review_state"] == "simulated_acceptance"
    assert review["context_sha256"] == fingerprint(ctx)
    assert report["input_hashes"]["case_review"] == fingerprint(ctx)
    for key in ("public_baseline", "historical_valuation", "constructed_options", "adjustment_review", "brief"):
        assert report[key] == original[key]
    assert report["actual_realized_value"] is None and report["execution_authorized"] is False
    for option in review["options"]:
        base = scenario(option)
        assert base["year_one"]["incremental_ebitda"] <= 0
        assert base["year_one"]["cost_removed"] == 0
        assert base["year_one"]["implementation_expense"] == Decimal("-85000")
        assert base["year_one"]["recurring_cost"] == Decimal("-102000")
        assert base["total"]["working_capital_cash"] == 0
        assert base["valuation"] == []
        assert next(a["value"] for a in base["assumptions"] if a["assumption_id"] == "capture") == "0.50"
        for field in ("resources", "tasks", "benefit_gates", "maximum_active_workstreams"):
            assert (
                option["plan"][field] == ctx.revisions[-1].draft.payload.operating_plan.model_dump(mode="json")[field]
            )
        y = base["year_one"]
        assert (
            y["incremental_ebitda"] + y["operating_accrual_to_cash"] + y["working_capital_cash"] + y["capex_cash"]
            == y["pre_tax_cash_proxy"]
        )
    assert [m.model_dump_json() for m in [*data, ctx]] == before
    html = render_memo(report)
    assert "Task order cannot substitute" in html
    assert html.index("id='evidence-update'") < html.index("id='thesis'")
    assert "Original preference — reopened" in html
    assert "Original conditional preference — now reopened" in html
    assert "not the current source-constrained forecast" in html
    assert "No operating intervention is authorized" in html


@pytest.mark.parametrize(
    "change",
    [
        "missing_original",
        "missing_middle",
        "duplicate",
        "wrong_hash",
        "wrong_case",
        "human",
        "wrong_parent",
        "withdraw_without_parent",
    ],
)
def test_incomplete_or_forged_context_is_rejected(change):
    raw = context().model_dump(mode="json")
    if change == "missing_original":
        raw["revisions"].pop(0)
    elif change == "missing_middle":
        raw["revisions"].pop(2)
    elif change == "duplicate":
        raw["revisions"].append(raw["revisions"][-1])
    elif change == "wrong_hash":
        raw["reviews"][-1]["revision_sha256"] = "a" * 64
    elif change == "wrong_case":
        raw["reviews"][-1]["company_id"] = "outsider"
    elif change == "human":
        raw["reviews"][-1]["mode"] = "human"
    elif change == "wrong_parent":
        raw["revisions"][-1]["parent_revision_id"] = raw["revisions"][0]["revision_id"]
    else:
        raw["reviews"][-1]["decision"] = "withdraw"
    with pytest.raises(ValueError):
        MemoReviewContext.model_validate(raw)


def test_withdrawal_and_missing_receipt_never_render_as_acceptance():
    raw = context().model_dump(mode="json")
    prior = raw["reviews"][-1]
    withdrawal = {
        **prior,
        "review_id": "fce5a659-260e-4a3d-884b-cec6d9429c95",
        "supersedes_review_id": prior["review_id"],
        "decision": "withdraw",
    }
    raw["reviews"].append(withdrawal)
    report = assemble_memo(*inputs(), MemoReviewContext.model_validate(raw))
    assert report["source_review"]["review_state"] == "withdrawn_or_rejected"
    assert report["source_review"]["active_receipts"] == [withdrawal]
    raw["reviews"] = []
    assert (
        assemble_memo(*inputs(), MemoReviewContext.model_validate(raw))["source_review"]["review_state"] == "unreviewed"
    )


def test_rehashed_financial_tampering_still_fails_reproduction():
    raw = context().model_dump(mode="json")
    last = raw["revisions"][-1]
    financial = json.loads(last["financial_result_json"])
    financial["scenarios"][1]["year_one"]["incremental_ebitda"] = "999999"
    last["financial_result_json"] = json.dumps(financial, sort_keys=True)
    unsigned = {k: v for k, v in last.items() if k != "content_sha256"}
    last["content_sha256"] = digest(json.dumps(unsigned, sort_keys=True))
    raw["reviews"][-1]["revision_sha256"] = last["content_sha256"]
    ctx = MemoReviewContext.model_validate(raw)
    with pytest.raises(ValueError, match="reproduced"):
        assemble_memo(*inputs(), ctx)


def test_source_context_must_bind_original_memo_inputs():
    data = inputs()
    raw = data[4].model_dump(mode="json")
    raw["multiple_rationale"] += " Changed original hypothesis."
    data[4] = type(data[4]).model_validate(raw)
    plan = data[5].model_dump(mode="json")
    plan["underwriting_sha256"] = fingerprint(data[4])
    data[5] = type(data[5]).model_validate(plan)
    brief = data[0].model_dump(mode="json")
    brief.update(underwriting_sha256=fingerprint(data[4]), plan_sha256=fingerprint(data[5]))
    data[0] = type(data[0]).model_validate(brief)
    with pytest.raises(ValueError, match="exact original"):
        assemble_memo(*data, context())


def test_waterfall_is_signed_and_refuses_an_unreconciled_headline():
    year = {
        "gross_price_benefit": "20",
        "revenue_leakage": "-5",
        "variable_cost": "-3",
        "cost_removed": "0",
        "recurring_cost": "-10",
        "implementation_expense": "-8",
        "incremental_ebitda": "-6",
    }
    html = incremental_waterfall(year)
    assert "-0.006" in html and "Vendor savings" in html and "aria-hidden='true'" in html
    year["incremental_ebitda"] = "7"
    with pytest.raises(ValueError, match="reconcile"):
        incremental_waterfall(year)


def test_export_binds_case_review_and_protects_source(tmp_path):
    out = tmp_path / "memo"
    build_decision_memo(*PATHS, out, SOURCE)
    result = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert result["source_review"]["current_revision_sha256"] == context().revisions[-1].content_sha256
    assert "href='memo.json' download" in out.with_suffix(".html").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        build_decision_memo(*PATHS, SOURCE, SOURCE)
    result["source_review"]["recommendation"] = "<script>injection</script>"
    assert "<script>injection</script>" not in render_memo(result)
