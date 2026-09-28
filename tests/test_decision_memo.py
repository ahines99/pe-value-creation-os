"""Decision-packet source binding, financial traceability and conditional authority."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.cli import main
from pe_value_os.diligence.growth import GrowthContext
from pe_value_os.diligence.memo import DecisionBrief, assemble_memo
from pe_value_os.diligence.memo_render import build_decision_memo, render_memo
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.peers import PeerContext
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.underwriting import UnderwritingCase

ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    ROOT / s
    for s in (
        "data/constructed/progress/decision-brief.json",
        "data/public/progress/financial-facts.json",
        "data/public/progress/growth-context.json",
        "data/public/progress/peer-context.json",
        "data/constructed/progress/underwriting.json",
        "data/constructed/progress/operating-plan.json",
    )
]
MODELS = (DecisionBrief, FactBundle, GrowthContext, PeerContext, UnderwritingCase, OperatingPlan)


def inputs():
    return [model.model_validate_json(path.read_bytes()) for model, path in zip(MODELS, PATHS, strict=True)]


def option(report, key):
    return next(o for o in report["constructed_options"] if o["option_id"] == key)


def scenario(op, key="base"):
    return next(s for s in op["analysis"]["scheduled_financials"]["scenarios"] if s["scenario_id"] == key)


def test_reported_company_economics_never_become_constructed_company_forecast():
    data = inputs()
    before = [x.model_dump_json() for x in data]
    r = assemble_memo(*data)
    assert r["public_baseline"]["reported"]["revenue"]["value"] == Decimal("977831000")
    assert r["public_baseline"]["derived"]["ebitda"]["value"] == Decimal("304202000")
    assert r["normalized_ebitda"] is None and r["company_equity_value"] is None
    assert r["actual_realized_value"] is None and not r["execution_authorized"]
    assert r["public_growth"]["organic_growth"] is None
    assert r["preference_status"] == "conditional_research_preference"
    assert all(o["feasible"] for o in r["constructed_options"])
    assert [x.model_dump_json() for x in data] == before
    assert assemble_memo(*data) == r


def test_hand_worked_sequencing_difference_preserves_costs_and_source_dates():
    r = assemble_memo(*inputs())
    current = scenario(option(r, "collections-first"))
    preferred = scenario(option(r, "service-first"))
    assert current["year_one"]["incremental_ebitda"] == Decimal("218976.65")
    assert preferred["year_one"]["incremental_ebitda"] == Decimal("228266.97")
    # Sixteen days of the assumed 18,000 monthly vendor cost action are recovered.
    assert preferred["year_one"]["incremental_ebitda"] - current["year_one"]["incremental_ebitda"] == (
        Decimal(18000) * 16 / 31
    ).quantize(Decimal("0.01"))
    assert preferred["year_one"]["pre_tax_cash_proxy"] == Decimal("179461.97")
    assert preferred["maximum_dated_funding_need"] == Decimal("125500.00")
    assert preferred["costs"] == current["costs"]
    assert preferred["day_100"]["working_capital_cash"] == Decimal("180000")
    assert preferred["year_one"]["working_capital_cash"] == 0
    assert preferred["day_100"]["pre_tax_cash_proxy"] == Decimal("55870.97")
    # A favorable base-case preference must not erase its adverse outcome.
    downside = scenario(option(r, "service-first"), "downside")
    assert downside["year_one"]["incremental_ebitda"] == Decimal("-327840")
    assert downside["maximum_dated_funding_need"] == Decimal("583630")
    for op in r["constructed_options"]:
        for s in op["analysis"]["scheduled_financials"]["scenarios"]:
            y = s["year_one"]
            assert (
                y["incremental_ebitda"] + y["operating_accrual_to_cash"] + y["working_capital_cash"] + y["capex_cash"]
                == y["pre_tax_cash_proxy"]
            )


def test_all_alternatives_preserve_scope_resources_and_assumptions():
    data = inputs()
    r = assemble_memo(*data)
    original = data[-1].model_dump(mode="json")
    for op in r["constructed_options"]:
        for field in ("resources", "tasks", "benefit_gates", "maximum_active_workstreams", "start", "days"):
            assert op["plan"][field] == original[field]
        assert op["analysis"]["original_underwriting_sha256"] == fingerprint(data[-2])
        for s in op["analysis"]["scheduled_financials"]["scenarios"]:
            original_s = next(x for x in data[-2].scenarios if x.scenario_id == s["scenario_id"])
            assert s["assumptions"] == [a.model_dump(mode="json") for a in original_s.assumptions]


@pytest.mark.parametrize("field", ["financial", "growth", "peers", "underwriting", "plan"])
def test_stale_brief_rejected_before_export(tmp_path, field):
    raw = json.loads(PATHS[0].read_text(encoding="utf-8"))
    raw[field + "_sha256"] = "0" * 64
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="exact"):
        build_decision_memo(brief, *PATHS[1:], tmp_path / "output" / "memo")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "thesis_reference",
        "adjustment_reference",
        "duplicate_option",
        "unknown_preference",
        "invalid_order",
        "duplicate_thesis",
        "unsupported_addback",
        "false_scope_exception",
        "cutoff",
    ],
)
def test_invalid_decision_contracts_are_rejected(mutation):
    data = inputs()
    raw = data[0].model_dump(mode="json")
    if mutation == "thesis_reference":
        raw["thesis"][0]["evidence_ids"] = ["unknown"]
    elif mutation == "adjustment_reference":
        raw["adjustment_review"][0]["fact_id"] = "unknown"
    elif mutation == "duplicate_option":
        raw["options"].append(raw["options"][0])
    elif mutation == "unknown_preference":
        raw["preferred_constructed_option"] = "unknown"
    elif mutation == "invalid_order":
        raw["options"][0]["priority_order"].pop()
    elif mutation == "duplicate_thesis":
        raw["thesis"].append(raw["thesis"][0])
    elif mutation == "unsupported_addback":
        raw["adjustment_review"][0]["disposition"] = "already_in_bridge"
    elif mutation == "false_scope_exception":
        raw["adjustment_review"][0]["disposition"] = "scope_unresolved"
    else:
        raw["as_of"] = "2026-09-27"
    with pytest.raises(ValueError):
        data[0] = DecisionBrief.model_validate(raw)
        assemble_memo(*data)


def test_unknown_capacity_reopens_preference_and_suppresses_benefits():
    data = inputs()
    raw = data[-1].model_dump(mode="json")
    raw["resources"][0]["weekly_hours"] = [None] * 15
    data[-1] = OperatingPlan.model_validate(raw)
    brief = data[0].model_dump(mode="json")
    brief["plan_sha256"] = fingerprint(data[-1])
    data[0] = DecisionBrief.model_validate(brief)
    r = assemble_memo(*data)
    assert r["preference_status"] == "reopen_blocked_preference"
    assert all(not o["feasible"] for o in r["constructed_options"])
    s = scenario(option(r, "service-first"))
    assert set(s["suppressed_benefits"]) == {"pricing-renewals", "service-automation", "collections-timing"}
    assert s["year_one"]["incremental_ebitda"] == Decimal("-187000")
    assert not r["execution_authorized"]


@pytest.mark.parametrize("classification", ["licensed_private", "permissioned_private", "constructed"])
def test_nonpublic_focal_fact_is_rejected_even_with_rebound_brief(classification):
    data = inputs()
    raw = data[1].model_dump(mode="json")
    raw["documents"][0]["classification"] = classification
    data[1] = FactBundle.model_validate(raw)
    brief = data[0].model_dump(mode="json")
    brief["financial_sha256"] = fingerprint(data[1])
    data[0] = DecisionBrief.model_validate(brief)
    with pytest.raises(ValueError, match="rejects"):
        assemble_memo(*data)


def test_adjustment_register_retains_expenses_and_known_scope_exceptions():
    r = assemble_memo(*inputs())
    assert len(r["adjustment_review"]) == 8
    assert all(a["accepted_addback"] is None for a in r["adjustment_review"])
    unresolved = [a for a in r["adjustment_review"] if a["disposition"] == "scope_unresolved"]
    assert {a["period"]["end"] for a in unresolved} == {"2023-11-30", "2024-11-30"}
    assert len([a for a in r["adjustment_review"] if a["disposition"] == "retain_expense"]) == 4


@pytest.mark.parametrize("index", range(6))
def test_export_never_overwrites_any_input(index):
    before = PATHS[index].read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_decision_memo(*PATHS, PATHS[index])
    assert PATHS[index].read_bytes() == before


def test_public_text_escaped_and_cli_replays_bound_memo(tmp_path):
    data = inputs()
    raw = data[0].model_dump(mode="json")
    raw["recommendation"] = "<script>alert('x')</script>"
    data[0] = DecisionBrief.model_validate(raw)
    html = render_memo(assemble_memo(*data))
    assert "<script>" not in html and "&lt;script&gt;" in html
    args = ["decision-memo"]
    for flag, path in zip(("brief", "facts", "growth", "peers", "underwriting", "operating-plan"), PATHS, strict=True):
        args.extend(["--" + flag, str(path)])
    output = tmp_path / "memo"
    args.extend(["--output", str(output)])
    assert main(args) == 0
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["execution_authorized"] is False and report["actual_realized_value"] is None
    assert "Service first" in output.with_suffix(".html").read_text(encoding="utf-8")
    html = output.with_suffix(".html").read_text(encoding="utf-8")
    assert "2026-03-01 to 2026-05-31" in html and "253.465" in html
    assert "2025-12-01 to 2026-05-31" in html and "501.264" in html
    assert "304.202" in html and "73.133" in html
    assert "href='memo.json' download" in html
