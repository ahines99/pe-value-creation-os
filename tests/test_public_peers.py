"""Peer selection, independently worked ratios and fail-closed publication boundaries."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from pe_value_os.cli import main
from pe_value_os.diligence.filing_pdf import FilingMap, extract_filing
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.peer_render import render_peers
from pe_value_os.diligence.peers import PeerContext, analyze_peers
from pe_value_os.diligence.render import build_public_report

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data/public/progress/financial-facts.json"
PEERS = ROOT / "data/public/progress/peer-context.json"


def inputs():
    return FactBundle.model_validate_json(FACTS.read_bytes()), PeerContext.model_validate_json(PEERS.read_bytes())


def raw():
    return inputs()[1].model_dump(mode="json")


def result(data):
    return analyze_peers(inputs()[0], PeerContext.model_validate(data))


def change_fact(data, metric, value):
    for fact in data["candidates"][0]["facts"]["facts"]:
        if fact["metric"] == metric:
            fact["reported_amount"] = value


def test_independently_worked_ratios_and_cohort_sensitivity():
    bundle, context = inputs()
    before = context.model_dump_json()
    report = analyze_peers(bundle, context)
    oi = report["metrics"]["operating_margin"]
    cash = report["metrics"]["cash_margin"]
    assert oi["focal"]["value"] == Decimal(153290) / Decimal(977831)
    assert cash["focal"]["value"] == Decimal(229485) / Decimal(977831)
    observations = report["observations"]
    assert observations[0]["metrics"]["operating_margin"]["value"] == Decimal(982385) / Decimal(2739226)
    assert observations[0]["metrics"]["cash_margin"]["value"] == Decimal(856688) / Decimal(2739226)
    assert observations[1]["metrics"]["cash_margin"]["value"] == Decimal(687396) / Decimal(5168405)
    assert observations[2]["metrics"]["operating_margin"]["value"] == Decimal(209978) / Decimal(728992)
    assert observations[2]["metrics"]["cash_margin"]["value"] == Decimal(260516) / Decimal(728992)
    assert observations[3]["metrics"]["operating_margin"]["value"] == Decimal("1436.7") / Decimal("6272.2")
    assert observations[3]["metrics"]["cash_margin"]["value"] == Decimal("1664.0") / Decimal("6272.2")
    assert (
        oi["cohorts"]["all_eligible"]["median"]
        == (Decimal("1436.7") / Decimal("6272.2") + Decimal(209978) / Decimal(728992)) / 2
    )
    assert (
        cash["cohorts"]["all_eligible"]["median"]
        == (Decimal("1664.0") / Decimal("6272.2") + Decimal(856688) / Decimal(2739226)) / 2
    )
    assert oi["cohorts"]["strict"]["count"] == 1 and oi["cohorts"]["strict"]["median"] is None
    assert cash["cohorts"]["strict"]["count"] == 0 and cash["cohorts"]["strict"]["median"] is None
    assert observations[2]["period"]["end"] == "2026-01-31"
    assert observations[3]["period"]["end"] == "2025-12-31"
    assert report["operating_target"] is None
    assert context.model_dump_json() == before and analyze_peers(bundle, context) == report


def test_growth_and_arr_are_not_inferred_from_consolidated_revenue():
    report = result(raw())
    for key in ("organic_growth", "arr_growth"):
        assert report["metrics"][key]["focal"]["value"] is None
        assert report["metrics"][key]["cohorts"]["all_eligible"]["count"] == 0


@pytest.mark.parametrize("mutation", ["source_hash", "entity", "private", "metric", "currency", "amount"])
def test_focal_cash_supplement_cannot_bypass_same_source_and_reconciliation(mutation):
    data = raw()
    supplement = data["focal_cash_reconciliation"]
    if mutation == "source_hash":
        supplement["documents"][0]["sha256"] = "0" * 64
    elif mutation == "entity":
        supplement["entity_id"] = "other"
    elif mutation == "private":
        supplement["documents"][0]["classification"] = "licensed_private"
    elif mutation == "metric":
        supplement["facts"][0]["metric"] = "revenue"
    elif mutation == "currency":
        supplement["facts"][0]["currency"] = "EUR"
    else:
        supplement["facts"][0]["reported_amount"] = "1"
    if mutation == "amount":
        report = result(data)
        assert report["metrics"]["cash_margin"]["focal"]["value"] is None
        assert report["metrics"]["operating_margin"]["focal"]["value"] is not None
    else:
        with pytest.raises(ValueError):
            result(data)


def test_removing_peer_withholds_median_and_keeps_exclusion_reason():
    data = raw()
    data["candidates"][0]["eligibility"][0]["status"] = "exclude"
    # One exclusion leaves three contextual values; two drop below the display floor.
    first = result(data)
    assert first["metrics"]["operating_margin"]["cohorts"]["all_eligible"]["count"] == 3
    assert first["metrics"]["operating_margin"]["cohorts"]["all_eligible"]["median"] is not None
    data["candidates"][3]["eligibility"][0]["status"] = "exclude"
    report = result(data)
    assert report["metrics"]["operating_margin"]["cohorts"]["all_eligible"]["count"] == 2
    assert report["metrics"]["operating_margin"]["cohorts"]["all_eligible"]["median"] is None
    assert report["metrics"]["cash_margin"]["cohorts"]["all_eligible"]["count"] == 4
    assert report["observations"][0]["metrics"]["operating_margin"]["rationale"]


@pytest.mark.parametrize(
    "metric,value,blocked,retained",
    [
        ("gross_profit", "1", "operating_margin", "cash_margin"),
        ("operating_expense", "1", "operating_margin", "cash_margin"),
        ("cash_flow_net_income", "1", "cash_margin", "operating_margin"),
        ("ppe_purchases", "1", "cash_margin", "operating_margin"),
    ],
)
def test_reconciliation_and_sign_failures_block_only_dependent_metric(metric, value, blocked, retained):
    data = raw()
    change_fact(data, metric, value)
    metrics = result(data)["observations"][0]["metrics"]
    assert metrics[blocked]["value"] is None and metrics[blocked]["blocked_by"]
    assert metrics[retained]["value"] is not None


@pytest.mark.parametrize(
    "metric",
    [
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_income",
        "operating_expense",
        "net_income",
        "cash_flow_net_income",
        "operating_cash_flow",
        "ppe_purchases",
    ],
)
def test_missing_fact_is_not_zero(metric):
    data = raw()
    data["candidates"][0]["facts"]["facts"] = [
        f for f in data["candidates"][0]["facts"]["facts"] if f["metric"] != metric
    ]
    report = result(data)
    key = (
        "cash_margin"
        if metric in ("net_income", "cash_flow_net_income", "operating_cash_flow", "ppe_purchases")
        else "operating_margin"
    )
    assert report["observations"][0]["metrics"][key]["value"] is None


@pytest.mark.parametrize("value", ["0", "-1"])
def test_nonpositive_revenue_withholds_both_ratios(value):
    data = raw()
    change_fact(data, "revenue", value)
    assert all(m["value"] is None for m in result(data)["observations"][0]["metrics"].values())


@pytest.mark.parametrize("mutation", ["currency", "end_window", "duration"])
def test_temporal_and_currency_gates(mutation):
    data = raw()
    for fact in data["candidates"][0]["facts"]["facts"]:
        if mutation == "currency":
            fact["currency"] = "EUR"
        elif mutation == "end_window":
            fact["period"]["start"] = f"{int(fact['period']['end'][:4]) - 1}-01-01"
            fact["period"]["end"] = f"{int(fact['period']['end'][:4]) - 1}-12-31"
        else:
            fact["period"]["start"] = fact["period"]["start"][:8] + "15"
    report = result(data)
    assert report["metrics"]["cash_margin"]["cohorts"]["all_eligible"]["count"] == 3
    assert report["observations"][0]["metrics"]["operating_margin"]["value"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "cutoff",
        "peer_cutoff",
        "duplicate",
        "unsupported_growth",
        "missing_decision",
        "unknown_evidence",
        "unverified_included",
        "wrong_company",
        "duplicate_component",
        "lower_floor",
        "wrong_anchor",
    ],
)
def test_invalid_context_is_rejected(mutation):
    data = raw()
    if mutation == "hash":
        data["financial_input_sha256"] = "0" * 64
    elif mutation == "cutoff":
        data["selection_as_of"] = "2026-09-27"
    elif mutation == "peer_cutoff":
        data["candidates"][0]["facts"]["information_cutoff"] = "2026-09-27"
    elif mutation == "duplicate":
        data["candidates"].append(data["candidates"][0])
    elif mutation == "unsupported_growth":
        data["candidates"][0]["eligibility"][2]["status"] = "strict"
    elif mutation == "missing_decision":
        data["candidates"][0]["eligibility"].pop()
    elif mutation == "unknown_evidence":
        data["candidates"][0]["eligibility"][0]["evidence_ids"] = ["unknown"]
    elif mutation == "unverified_included":
        data["candidates"][3]["facts"] = None
        data["candidates"][3]["eligibility"][0]["status"] = "strict"
    elif mutation == "wrong_company":
        data["candidates"][0]["company"] = "Other"
    elif mutation == "duplicate_component":
        data["candidates"][2]["operating_expense_components"] *= 2
    elif mutation == "lower_floor":
        data["minimum_median_count"] = 2
    else:
        data["anchor"]["end"] = "2025-11-29"
    with pytest.raises(ValueError):
        result(data)


@pytest.mark.parametrize("source_class", ["licensed_private", "permissioned_private", "constructed"])
def test_nonpublic_peer_blocks_export_before_writing(tmp_path, source_class):
    data = raw()
    data["candidates"][0]["facts"]["documents"][0]["classification"] = source_class
    source = tmp_path / "peers.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="rejects"):
        build_public_report(FACTS, tmp_path / "output" / "memo", peer_source=source)
    assert not (tmp_path / "output").exists()


def test_public_renderer_escapes_judgments_and_cli_preserves_context(tmp_path):
    data = raw()
    data["candidates"][0]["eligibility"][0]["rationale"] = "<script>alert(1)</script>"
    html = render_peers(result(data))
    assert "<script>" not in html and "&lt;script&gt;" in html
    before = PEERS.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_public_report(FACTS, PEERS, peer_source=PEERS)
    assert PEERS.read_bytes() == before
    output = tmp_path / "case"
    assert main(["public-diligence", "--input", str(FACTS), "--peers", str(PEERS), "--output", str(output)]) == 0
    assert "id='peers'" in output.with_suffix(".html").read_text(encoding="utf-8")
    assert json.loads(output.with_suffix(".json").read_text())["peer_analysis"]["operating_target"] is None


def test_mapping_and_embedded_facts_match_separate_source_artifacts():
    for candidate in inputs()[1].candidates:
        if candidate.facts is None:
            continue
        mapping = FilingMap.model_validate_json(
            (ROOT / f"data/public/peers/{candidate.candidate_id}-map.json").read_bytes()
        )
        bundle = FactBundle.model_validate_json(
            (ROOT / f"data/public/peers/{candidate.candidate_id}-facts.json").read_bytes()
        )
        assert candidate.facts == bundle
        assert bundle.documents[0].mapping_sha256 == hashlib.sha256(mapping.model_dump_json().encode()).hexdigest()
    assert sum(len(c.facts.facts) for c in inputs()[1].candidates if c.facts) == 123


def test_ssc_software_investment_is_preserved_without_relabeling_cash_proxy():
    bundle, context = inputs()
    candidate = context.candidates[3]
    assert candidate.facts is not None
    facts = {f.metric: f.amount for f in candidate.facts.facts if f.period.end == date(2025, 12, 31)}
    assert facts["capitalized_software_purchases"] == Decimal(-221900000)
    assert facts["operating_cash_flow"] + facts["ppe_purchases"] == Decimal(1664000000)
    after_software = facts["operating_cash_flow"] + facts["ppe_purchases"] + facts["capitalized_software_purchases"]
    assert after_software == Decimal(1442100000)
    report = analyze_peers(bundle, context)
    metric = report["observations"][3]["metrics"]["cash_margin"]
    assert metric["value"] != after_software / facts["revenue"]
    assert metric["status"] == "context_only"
    assert "ssc-capitalization" in metric["evidence_ids"]
    assert "ssc-client-funds" in metric["evidence_ids"]
    assert report["operating_target"] is None


def test_header_page_number_and_40f_are_explicit_and_fail_closed(tmp_path, monkeypatch):
    from tests.test_public_diligence import tiny_mapping

    payload = b"test-pdf"
    raw_map = tiny_mapping(payload).model_dump(mode="json")
    raw_map["form"] = "40-F"
    raw_map["tables"][0]["printed_page_location"] = "header"
    mapping = FilingMap.model_validate(raw_map)
    table = mapping.tables[0]
    text = "\n".join(
        [
            table.printed_page,
            mapping.entity_heading,
            table.heading,
            table.unit_heading,
            " ".join(c.label for c in table.columns),
            *[r.label + " " + " ".join("100" for _ in table.columns) for r in table.rows],
            "Notes follow.",
        ]
    )
    monkeypatch.setattr(
        "pypdf.PdfReader", lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    )
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(payload)
    extracted = extract_filing(pdf, mapping, datetime(2026, 9, 28, tzinfo=UTC), date(2026, 9, 28))
    assert extracted.documents[0].form == "40-F"
    assert extracted.documents[0].extraction_version == "filing-pdf/3"
    text = text.replace(table.printed_page + "\n", "WRONG\n", 1)
    with pytest.raises(ValueError, match="printed page"):
        extract_filing(pdf, mapping, datetime(2026, 9, 28, tzinfo=UTC), date(2026, 9, 28))
