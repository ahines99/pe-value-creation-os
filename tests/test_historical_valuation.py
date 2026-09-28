"""Principal/carrying value, dated source binding and explicit EV-to-equity arithmetic."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from pe_value_os.cli import main
from pe_value_os.diligence.balances import BalanceBundle, BalanceMap, balance_values, extract_balances
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.scheduling import fingerprint
from pe_value_os.diligence.valuation import REQUIRED, ValuationSpec, analyze_valuation
from pe_value_os.diligence.valuation_render import build_valuation_report, render_valuation

ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    ROOT / p
    for p in (
        "data/public/progress/financial-facts.json",
        "data/public/progress/balance-facts.json",
        "data/constructed/progress/historical-valuation.json",
    )
]
MAP_PATH = ROOT / "data/public/progress/fy2025-balance-map.json"


def inputs():
    return [
        model.model_validate_json(path.read_bytes())
        for model, path in zip((FactBundle, BalanceBundle, ValuationSpec), PATHS, strict=True)
    ]


def rebind(data):
    raw = data[2].model_dump(mode="json")
    raw.update(financial_sha256=fingerprint(data[0]), balances_sha256=fingerprint(data[1]))
    data[2] = ValuationSpec.model_validate(raw)
    return data


def change_balance(data, metric, value):
    raw = data[1].model_dump(mode="json")
    next(f for f in raw["facts"] if f["metric"] == metric)["reported_amount"] = str(value)
    data[1] = BalanceBundle.model_validate(raw)
    return rebind(data)


def test_hand_worked_principal_bridge_and_negative_residual():
    data = inputs()
    before = [d.model_dump_json() for d in data]
    r = analyze_valuation(*data)
    assert r["earnings"]["value"] == Decimal("304202000")
    assert r["debt_principal"] == Decimal("1410000000")
    assert r["debt_carrying_value"] == Decimal("1400349000")
    assert r["debt_principal"] - r["debt_carrying_value"] == Decimal("9651000")
    assert r["lease_liabilities"] == Decimal("29567000")
    assert all(c["status"] == "matched" for c in r["reconciliations"])
    first = r["scenarios"][0]["rows"][0]
    assert first["enterprise_value"] == Decimal("1216808000")
    assert first["cash_added"] == Decimal("94807000")
    assert first["equity_sensitivity"] == Decimal("-98385000")
    assert r["scenarios"][0]["rows"][2]["equity_sensitivity"] == Decimal("1118423000")
    assert r["scenarios"][1]["rows"][2]["equity_sensitivity"] == Decimal("1071019500")
    assert r["scenarios"][2]["rows"][2]["equity_sensitivity"] == Decimal("954049000")
    for scenario in r["scenarios"]:
        for row in scenario["rows"]:
            assert row["equity_sensitivity"] == row["enterprise_value"] + row["cash_added"] + row[
                "nonoperating_assets_added"
            ] - sum(
                row[k]
                for k in (
                    "debt_principal_deducted",
                    "lease_claim_deducted",
                    "other_claims_deducted",
                    "transaction_costs_deducted",
                )
            )
    assert r["current_equity_value"] is None and r["per_share_value"] is None and r["transaction_proceeds"] is None
    assert r["subsequent_events"] and r["historical_date"].isoformat() == "2025-11-30"
    assert [d.model_dump_json() for d in data] == before
    assert analyze_valuation(*data) == r


@pytest.mark.parametrize("metric", sorted(REQUIRED))
def test_missing_required_balance_withholds_every_equity_and_ev_row(metric):
    data = inputs()
    raw = data[1].model_dump(mode="json")
    raw["facts"] = [f for f in raw["facts"] if f["metric"] != metric]
    data[1] = BalanceBundle.model_validate(raw)
    r = analyze_valuation(*rebind(data))
    assert f"Missing balance input: {metric}" in r["blocked_by"]
    assert all(
        row["enterprise_value"] is None and row["equity_sensitivity"] is None
        for s in r["scenarios"]
        for row in s["rows"]
    )


@pytest.mark.parametrize(
    "metric", ["current_notes_net", "noncurrent_notes_net", "long_term_face", "total_debt_net", "revolver_note"]
)
def test_debt_mismatch_is_not_a_warning_with_usable_valuation(metric):
    r = analyze_valuation(*change_balance(inputs(), metric, "123"))
    assert any(c["status"] == "mismatch" for c in r["reconciliations"])
    assert all(row["equity_sensitivity"] is None for s in r["scenarios"] for row in s["rows"])


@pytest.mark.parametrize("metric,value", [("cash", "-1"), ("lease_current", "-1"), ("current_discount", "837")])
def test_unexpected_signs_block_equity(metric, value):
    r = analyze_valuation(*change_balance(inputs(), metric, value))
    assert f"Unexpected source sign: {metric}" in r["blocked_by"]


def test_missing_earnings_component_blocks_even_with_rebound_revision():
    data = inputs()
    raw = data[0].model_dump(mode="json")
    raw["facts"] = [
        f
        for f in raw["facts"]
        if not (
            f["metric"] == "ppe_depreciation"
            and f["period"]["basis"] == "annual"
            and f["period"]["end"] == "2025-11-30"
        )
    ]
    data[0] = FactBundle.model_validate(raw)
    r = analyze_valuation(*rebind(data))
    assert r["earnings"]["value"] is None
    assert "Defined annual earnings bridge is unavailable" in r["blocked_by"]


def test_multiple_changes_only_ev_and_equity_not_the_source_claims():
    data = inputs()
    original = analyze_valuation(*data)
    raw = data[2].model_dump(mode="json")
    raw["multiples"] = ["5"]
    data[2] = ValuationSpec.model_validate(raw)
    changed = analyze_valuation(*data)
    assert changed["spec_sha256"] != original["spec_sha256"]
    for field in ("financial_sha256", "balances_sha256", "earnings", "reconciliations", "debt_principal"):
        assert changed[field] == original[field]
    a, b = original["scenarios"][0]["rows"][0], changed["scenarios"][0]["rows"][0]
    assert b["enterprise_value"] - a["enterprise_value"] == original["earnings"]["value"]
    assert b["equity_sensitivity"] - a["equity_sensitivity"] == original["earnings"]["value"]


@pytest.mark.parametrize(
    "field", ["nonoperating_assets", "other_claims", "transaction_costs", "cash_rationale", "lease_treatment"]
)
def test_no_missing_assumption_defaults_to_zero(field):
    raw = inputs()[2].model_dump(mode="json")
    del raw["scenarios"][0][field]
    with pytest.raises(ValueError):
        ValuationSpec.model_validate(raw)


@pytest.mark.parametrize("multiple", ["0", "-1", "NaN", "Infinity"])
def test_invalid_multiples_rejected(multiple):
    raw = inputs()[2].model_dump(mode="json")
    raw["multiples"] = [multiple]
    with pytest.raises(ValueError):
        ValuationSpec.model_validate(raw)


def test_assumption_cash_and_precision_bounds():
    raw = inputs()[2].model_dump(mode="json")
    raw["scenarios"][0]["available_cash_fraction"] = "1.01"
    with pytest.raises(ValueError):
        ValuationSpec.model_validate(raw)
    raw["scenarios"][0]["available_cash_fraction"] = "1"
    raw["scenarios"][0]["other_claims"]["amount"] = "1.001"
    with pytest.raises(ValueError, match="whole-cent"):
        ValuationSpec.model_validate(raw)


@pytest.mark.parametrize("mutation", ["classification", "date", "currency", "source", "cutoff", "hash"])
def test_rebound_sources_still_must_be_public_same_date_and_registered(mutation):
    data = inputs()
    raw = data[1].model_dump(mode="json")
    if mutation == "classification":
        raw["document"]["classification"] = "licensed_private"
    elif mutation == "date":
        raw["facts"][0]["as_of"] = "2025-11-29"
    elif mutation == "currency":
        raw["facts"][0]["currency"] = "EUR"
    elif mutation == "source":
        raw["document"]["sha256"] = "0" * 64
    elif mutation == "cutoff":
        raw["information_cutoff"] = "2026-09-27"
    else:
        raw["facts"][0]["reported_amount"] = "1"
    data[1] = BalanceBundle.model_validate(raw)
    with pytest.raises(ValueError):
        analyze_valuation(*(data if mutation == "hash" else rebind(data)))


def test_pdf_extraction_reproduces_dated_rows_and_never_converts_comparative_dashes_to_zero(tmp_path, monkeypatch):
    mapping = BalanceMap.model_validate_json(MAP_PATH.read_bytes())
    pages = [SimpleNamespace(extract_text=lambda: "") for _ in range(55)]
    expected = inputs()[1]
    for table in mapping.tables:
        text = (
            "PROGRESS SOFTWARE CORPORATION\n"
            + table.heading
            + "\n"
            + table.unit_heading
            + " November 30, 2025 November 30, 2024\n"
        )
        for row in table.rows:
            value = next(f for f in expected.facts if f.metric == row.metric)
            if row.occurrence:
                continue  # inserted with the first occurrence below
            text += value.source_row + "\n"
            same = [r for r in table.rows if r.label == row.label and r.occurrence > 0]
            for other in same:
                text += next(f.source_row for f in expected.facts if f.metric == other.metric) + "\n"
        text += table.printed_page
        pages[table.pdf_page - 1] = SimpleNamespace(extract_text=lambda text=text: text)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source fixture")
    raw = mapping.model_dump(mode="json")
    raw["registered_document"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    mapping = BalanceMap.model_validate(raw)
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=pages))
    extracted = extract_balances(source, mapping)
    assert [(f.metric, f.reported_amount) for f in extracted.facts] == [
        (f.metric, f.reported_amount) for f in expected.facts
    ]
    assert all(f.as_of.isoformat() == "2025-11-30" for f in extracted.facts)
    source.write_bytes(b"changed bytes")
    with pytest.raises(ValueError, match="hash"):
        extract_balances(source, mapping)


@pytest.mark.parametrize("mutation", ["dash", "columns", "header", "heading", "number"])
def test_pdf_ambiguities_fail_closed(mutation):
    raw = BalanceMap.model_validate_json(MAP_PATH.read_bytes()).tables[0].model_dump(mode="json")
    raw["rows"] = [raw["rows"][0]]
    table = type(BalanceMap.model_validate_json(MAP_PATH.read_bytes()).tables[0]).model_validate(raw)
    text = "Consolidated Balance Sheets\n(in thousands, except share data) November 30, 2025 November 30, 2024\nCash and cash equivalents 94,807 118,077\n37"
    if mutation == "dash":
        text = text.replace("94,807", "—")
    elif mutation == "columns":
        text = text.replace("118,077", "118,077 1")
    elif mutation == "header":
        text = text.replace("November 30, 2025 November 30, 2024", "November 30, 2024 November 30, 2025")
    elif mutation == "heading":
        text = text.replace("Consolidated Balance Sheets", "Different company statement")
    else:
        text = text.replace("94,807", "94,80X")
    with pytest.raises(ValueError):
        balance_values(text, table)


@pytest.mark.parametrize("index", range(3))
def test_export_protects_all_input_files(index):
    before = PATHS[index].read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_valuation_report(*PATHS, PATHS[index])
    assert PATHS[index].read_bytes() == before


def test_cli_render_and_escaping(tmp_path):
    output = tmp_path / "valuation"
    assert (
        main(
            [
                "historical-valuation",
                "--facts",
                str(PATHS[0]),
                "--balances",
                str(PATHS[1]),
                "--spec",
                str(PATHS[2]),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    r = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    html = output.with_suffix(".html").read_text(encoding="utf-8")
    assert "-98.385" in html and "1,410.000" in html and "1,400.349" in html
    assert "href='valuation.json' download" in html
    r["spec"]["multiple_rationale"] = "<script>bad()</script>"
    assert "<script>" not in render_valuation(r) and "&lt;script&gt;" in render_valuation(r)
    raw = inputs()[2].model_dump(mode="json")
    raw["balances_sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    assert (
        main(
            [
                "historical-valuation",
                "--facts",
                str(PATHS[0]),
                "--balances",
                str(PATHS[1]),
                "--spec",
                str(bad),
                "--output",
                str(tmp_path / "failed" / "valuation"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "failed").exists()
