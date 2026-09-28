"""Acquisition perimeter, rounded disclosures, public export and research judgment boundaries."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pe_value_os.cli import main
from pe_value_os.diligence.filing_pdf import FilingMap
from pe_value_os.diligence.growth import GrowthContext, analyze_growth, fingerprint, verify_disclosure_source
from pe_value_os.diligence.growth_render import render_growth
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.render import build_public_report

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data/public/progress/financial-facts.json"
CONTEXT = ROOT / "data/public/progress/growth-context.json"


def inputs():
    return FactBundle.model_validate_json(FACTS.read_bytes()), GrowthContext.model_validate_json(CONTEXT.read_bytes())


def raw_context():
    return inputs()[1].model_dump(mode="json")


def test_independently_worked_acquisition_bridge_is_not_organic_growth():
    facts, context = inputs()
    result = analyze_growth(facts, context)
    assert result["reported_change"] == Decimal("224422000")
    assert result["acquired_change"] == Decimal("240500000")
    assert result["residual_change"] == Decimal("-16078000")
    assert result["residual_prior"] == Decimal("732309000")
    assert result["residual_current"] == Decimal("716231000")
    assert result["acquired_change"] + result["residual_change"] == result["reported_change"]
    assert result["residual_growth"] == Decimal("-16078000") / Decimal("732309000")
    assert result["organic_growth"] is None and result["acquired_earnings"] is None
    assert result["display_resolution"] == 100000
    assert result == analyze_growth(facts, context)
    assert {d.disposition for d in context.assessments} == {"investigate", "defer", "reject"}
    assert all(d.decision_scope == "research_assessment_only" for d in context.assessments)


def test_mix_reconciles_three_annual_periods_without_overwriting_original_facts():
    facts, context = inputs()
    before = facts.model_dump_json()
    result = analyze_growth(facts, context)
    assert len(context.revenue_mix.facts) == 15
    assert len(result["revenue_mix"]) == 3
    for period in result["revenue_mix"]:
        assert sum(c["amount"] for c in period["components"].values()) == period["total"]
    current = result["revenue_mix"][-1]
    assert current["components"]["saas_revenue"]["amount"] == Decimal("287928000")
    assert current["components"]["maintenance_revenue"]["amount"] == Decimal("410174000")
    assert current["components"]["professional_services_revenue"]["amount"] == Decimal("41842000")
    assert facts.model_dump_json() == before
    assert len(facts.facts) == 241
    mapping = FilingMap.model_validate_json((ROOT / "data/public/progress/revenue-mix-map.json").read_bytes())
    assert (
        hashlib.sha256(mapping.model_dump_json().encode()).hexdigest()
        == context.revenue_mix.documents[0].mapping_sha256
    )


@pytest.mark.parametrize(
    "field,value", [("financial_input_sha256", "0" * 64), ("source_sha256", "0" * 64), ("document_id", "unknown")]
)
def test_changed_bundle_or_source_revision_requires_explicit_remapping(field, value):
    facts, _ = inputs()
    raw = raw_context()
    raw[field] = value
    with pytest.raises(ValueError, match=r"revision|registered"):
        analyze_growth(facts, GrowthContext.model_validate(raw))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "mismatch",
        "foreign_currency",
        "negative",
        "unknown_component",
        "changed_source",
        "changed_entity",
        "changed_cutoff",
        "missing_year",
    ],
)
def test_revenue_disaggregation_cannot_manufacture_a_comparable_total(mutation):
    facts, _ = inputs()
    raw = raw_context()
    mix = raw["revenue_mix"]
    if mutation == "missing":
        mix["facts"] = [f for f in mix["facts"] if f["metric"] != "saas_revenue"]
    elif mutation == "mismatch":
        mix["facts"][0]["reported_amount"] = "1"
    elif mutation == "foreign_currency":
        mix["facts"][0]["currency"] = "EUR"
    elif mutation == "negative":
        mix["facts"][0]["reported_amount"] = "-1"
    elif mutation == "unknown_component":
        mix["facts"][0]["metric"] = "invented_revenue"
    elif mutation == "changed_source":
        mix["documents"][0]["sha256"] = "0" * 64
    elif mutation == "changed_entity":
        mix["ticker"] = "OTHER"
    elif mutation == "changed_cutoff":
        mix["information_cutoff"] = "2026-09-29"
    else:
        mix["facts"] = [f for f in mix["facts"] if f["period"]["end"] != "2024-11-30"]
    with pytest.raises(ValueError):
        analyze_growth(facts, GrowthContext.model_validate(raw))


@pytest.mark.parametrize(
    "mutation",
    [
        "reversed_periods",
        "quarter",
        "wrong_metric",
        "over_total",
        "currency",
        "before_acquisition",
        "pro_forma",
        "precision",
    ],
)
def test_contribution_period_basis_and_precision_gates(mutation):
    facts, _ = inputs()
    raw = raw_context()
    if mutation == "reversed_periods":
        raw["current"], raw["prior"] = raw["prior"], raw["current"]
    elif mutation == "quarter":
        raw["current"]["revenue_fact_id"] = next(
            f.fact_id for f in facts.facts if f.metric == "revenue" and f.period.basis == "discrete_quarter"
        )
    elif mutation == "wrong_metric":
        raw["current"]["revenue_fact_id"] = next(f.fact_id for f in facts.facts if f.metric == "net_income")
    elif mutation == "over_total":
        raw["current"]["reported_amount"] = "1000.0"
    elif mutation == "currency":
        raw["prior"]["currency"] = "EUR"
    elif mutation == "before_acquisition":
        raw["acquired_on"] = "2025-12-01"
    elif mutation == "pro_forma":
        raw["current"]["evidence_id"] = "pro-forma-basis"
    else:
        raw["current"]["reported_amount"] = "261.61"
    with pytest.raises(ValueError):
        analyze_growth(facts, GrowthContext.model_validate(raw))


def test_zero_residual_denominator_is_unavailable_not_division_error():
    facts, _ = inputs()
    raw = raw_context()
    raw["prior"].update(reported_amount="753.409", reported_resolution="0.001")
    result = analyze_growth(facts, GrowthContext.model_validate(raw))
    assert result["residual_prior"] == 0 and result["residual_growth"] is None


def test_offsetting_component_changes_cannot_hide_a_conflict_with_existing_license_facts():
    facts, context = inputs()
    raw = raw_context()
    # The current annual baseline has only total revenue. Supply an independently
    # selected overlapping component to exercise the conflict gate explicitly.
    original = facts.model_dump(mode="json")
    original["facts"].append(
        next(
            f.model_dump(mode="json")
            for f in context.revenue_mix.facts
            if f.metric == "software_license_revenue" and f.period.end.year == 2025
        )
    )
    facts = FactBundle.model_validate(original)
    raw["financial_input_sha256"] = fingerprint(facts)
    for fact in raw["revenue_mix"]["facts"]:
        if fact["period"]["end"] == "2025-11-30":
            if fact["metric"] == "software_license_revenue":
                fact["reported_amount"] = "237888"
            elif fact["metric"] == "maintenance_revenue":
                fact["reported_amount"] = "410173"
    with pytest.raises(ValueError, match="existing source fact"):
        analyze_growth(facts, GrowthContext.model_validate(raw))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_counter",
        "unknown_evidence",
        "duplicate_evidence",
        "duplicate_assessment",
        "expired_review",
        "operating_approval",
    ],
)
def test_research_decisions_need_traceable_contradiction_and_cannot_be_approvals(mutation):
    raw = raw_context()
    if mutation == "missing_counter":
        raw["assessments"][0]["counterevidence_ids"] = []
    elif mutation == "unknown_evidence":
        raw["assessments"][0]["supporting_evidence_ids"] = ["invented"]
    elif mutation == "duplicate_evidence":
        raw["disclosures"].append(raw["disclosures"][0])
    elif mutation == "duplicate_assessment":
        raw["assessments"].append(raw["assessments"][0])
    elif mutation == "expired_review":
        raw["assessments"][0]["review_by"] = "2026-09-27"
    else:
        raw["assessments"][0]["decision_scope"] = "operating_approval"
    with pytest.raises(ValidationError):
        GrowthContext.model_validate(raw)


@pytest.mark.parametrize("classification", ["licensed_private", "permissioned_private", "constructed"])
def test_nested_source_policy_rejects_private_context_before_any_export(tmp_path, classification):
    raw = raw_context()
    raw["revenue_mix"]["documents"][0]["classification"] = classification
    source = tmp_path / "context.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="export rejects"):
        build_public_report(FACTS, tmp_path / "public" / "report", source)
    assert not (tmp_path / "public").exists()


def test_fingerprint_covers_research_edits_and_html_escapes_all_authored_prose():
    facts, context = inputs()
    original = analyze_growth(facts, context)
    raw = raw_context()
    raw["assessments"][0]["rationale"] = "<script>alert('assessment')</script>"
    raw["disclosures"][0]["reported_summary"] = "<script>alert('disclosure')</script>"
    changed = analyze_growth(facts, GrowthContext.model_validate(raw))
    assert changed["context_sha256"] != original["context_sha256"]
    assert changed["financial_input_sha256"] == fingerprint(facts)
    html = render_growth(facts, changed)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "-16.1" in html and "-2.2%" in html
    assert "-16.078" not in html
    assert "Organic growth remains unavailable" in html and "not ARR" in html


def test_cli_replay_and_input_overwrite_protection(tmp_path):
    output = tmp_path / "baseline"
    assert main(["public-diligence", "--input", str(FACTS), "--growth", str(CONTEXT), "--output", str(output)]) == 0
    report = json.loads(output.with_suffix(".json").read_text())
    assert report["growth_analysis"]["organic_growth"] is None
    annual = next(p for p in report["periods"] if p["basis"] == "annual" and p["end"] == "2025-11-30")
    assert Decimal(annual["derived"]["ebitda"]["value"]) == Decimal("304202000")
    assert "research-decisions" in output.with_suffix(".html").read_text(encoding="utf-8")
    before = CONTEXT.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_public_report(FACTS, CONTEXT, CONTEXT)
    assert CONTEXT.read_bytes() == before


def test_optional_source_verifier_rejects_changed_bytes(tmp_path):
    _, context = inputs()
    path = tmp_path / "changed.pdf"
    path.write_bytes(b"not the registered filing")
    with pytest.raises(ValueError, match="hash"):
        verify_disclosure_source(path, context)
