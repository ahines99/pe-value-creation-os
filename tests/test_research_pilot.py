"""Synthetic fixtures only: these tests contain no vendor records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pe_value_os.cli import main
from pe_value_os.research.models import PilotBundle
from pe_value_os.research.pilot import analyze, build_report, private_destination


def bundle_data() -> dict:
    rows = []
    for index, ticker in enumerate(["TEST", "AAA", "BBB", "CCC"]):
        for year in [2023, 2024]:
            rows.append(
                {
                    "entity_id": ticker,
                    "ticker": ticker,
                    "company": f"Fictional {ticker}",
                    "period": "annual",
                    "period_end": f"{year}-12-31",
                    "fiscal_year": year,
                    "currency": "USD",
                    "revenue": str(100 if year == 2023 else 120),
                    "cogs": "30",
                    "sga": str(30 + index * 12),
                    "operating_income": "24",
                    "source": "comp.funda",
                    "source_file": "synthetic.parquet",
                    "source_sha256": "a" * 64,
                    "source_row": len(rows),
                    "vintage": "2025-03-01T00:00:00Z",
                    "available_at": "2025-02-01T00:00:00Z",
                }
            )
    return {
        "classification": "synthetic",
        "focal_ticker": "TEST",
        "anchor_period_end": "2024-12-31",
        "first_year": 2023,
        "as_of": "2025-06-01T00:00:00Z",
        "peers": [
            {"ticker": t, "rationale": "Synthetic comparable for tests", "limitation": "Fictional data, not a business"}
            for t in ["AAA", "BBB", "CCC"]
        ],
        "statements": rows,
    }


def test_financial_math_and_peer_exclusion():
    report = analyze(PilotBundle.model_validate(bundle_data()))
    assert report["focal_metrics"]["revenue_growth"] == Decimal("0.2")
    assert report["focal_metrics"]["gross_margin"] == Decimal("0.75")
    assert report["benchmarks"]["sga_intensity"] == {"median": Decimal("0.45"), "n": 3}
    assert report["sensitivity"][1]["gross_annual_effect_millions"] == Decimal("1.2")
    assert report["human_acceptance"] == "pending"
    assert report["operating_plan"] == "not_created"


def test_revisions_are_coherent_rows_and_future_vintages_excluded():
    data = bundle_data()
    original = data["statements"][1]
    revised = {**original, "vintage": "2025-04-01T00:00:00Z", "sga": None, "revenue": "125"}
    future = {**original, "vintage": "2025-07-01T00:00:00Z", "revenue": "999"}
    data["statements"] += [revised, future]
    report = analyze(PilotBundle.model_validate(data))
    assert report["focal"]["revenue"] == "125"
    assert report["focal_metrics"]["sga_intensity"] is None  # No field splicing from old row.
    assert report["exclusions"]["future_vintage"] == 1
    assert report["exclusions"]["superseded"] == 1


@pytest.mark.parametrize(
    "change", [{"currency": "EUR"}, {"period_end": "2024-01-01"}, {"available_at": "2025-07-01T00:00:00Z"}]
)
def test_ineligible_peers_do_not_enter_median(change):
    data = bundle_data()
    data["statements"][3].update(change)
    report = analyze(PilotBundle.model_validate(data))
    assert report["benchmarks"]["sga_intensity"]["median"] is None
    assert len(report["peers"]) == 2


def test_missing_values_are_not_zero_and_growth_does_not_span_missing_years():
    data = bundle_data()
    data["statements"][1]["cogs"] = None
    data["statements"][0]["fiscal_year"] = 2022
    data["statements"][0]["period_end"] = "2022-12-31"
    report = analyze(PilotBundle.model_validate(data))
    assert report["focal_metrics"]["gross_margin"] is None
    assert report["focal_metrics"]["revenue_growth"] is None


@pytest.mark.parametrize("revenue", ["0", "-1", "NaN", "Infinity"])
def test_invalid_revenue_rejected(revenue):
    data = bundle_data()
    data["statements"][0]["revenue"] = revenue
    with pytest.raises(ValidationError):
        PilotBundle.model_validate(data)


def test_identity_collision_rejected():
    data = bundle_data()
    data["statements"][0]["entity_id"] = "DIFFERENT"
    with pytest.raises(ValidationError, match="multiple entities"):
        PilotBundle.model_validate(data)


def test_quarterly_growth_uses_same_quarter_and_does_not_replace_annual():
    data = bundle_data()
    for year, value in [(2023, "20"), (2024, "30")]:
        data["statements"].append(
            {
                **data["statements"][0],
                "period": "quarterly",
                "source": "comp.fundq",
                "fiscal_year": year,
                "fiscal_quarter": 4,
                "period_end": f"{year}-12-31",
                "revenue": value,
            }
        )
    report = analyze(PilotBundle.model_validate(data))
    assert report["focal"]["revenue"] == "120"
    assert report["history"][-1]["metrics"]["revenue_growth"] == Decimal("0.5")


def test_source_bridge_reconciliation_and_mismatch():
    data = bundle_data()
    data["reconciliations"] = [
        {
            "ticker": "TEST",
            "period_end": "2024-12-31",
            "metric": "sga",
            "reported_millions": "20",
            "bridge_millions": "10",
            "explanation": "Synthetic bridge for validation",
            "source_url": "https://example.com/filing",
            "source_locator": "page 1",
        }
    ]
    report = analyze(PilotBundle.model_validate(data))
    assert report["reconciliations"][0]["status"] == "matched"
    data["reconciliations"][0]["bridge_millions"] = "11"
    assert analyze(PilotBundle.model_validate(data))["reconciliations"][0]["status"] == "unresolved"


def test_private_report_end_to_end_and_html_escaping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = bundle_data()
    data["statements"][1]["company"] = "<script>alert('x')</script>"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    assert main(["research-pilot", "--input", str(source), "--name", "sample"]) == 0
    html = (tmp_path / "var/research-pilot/sample.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Human acceptance pending" in html
    assert "Synthetic test research" in html
    first = (tmp_path / "var/research-pilot/sample.json").read_bytes()
    build_report(source, "sample")
    assert (tmp_path / "var/research-pilot/sample.json").read_bytes() == first


@pytest.mark.parametrize("name", ["../../docs/leak", "../leak"])
def test_output_cannot_escape_private_directory(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        private_destination(name)
    assert not (tmp_path / "docs").exists()


def test_output_refuses_input_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = private_destination("same.json")
    source.write_text(json.dumps(bundle_data()), encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        build_report(source, "same")


def test_no_focal_at_cutoff_fails_closed():
    data = bundle_data()
    data["as_of"] = datetime(2025, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="no eligible focal"):
        analyze(PilotBundle.model_validate(data))


def test_conflicting_same_vintage_fails_closed():
    data = bundle_data()
    data["statements"].append({**data["statements"][1], "sga": "90"})
    with pytest.raises(ValueError, match="conflicting"):
        analyze(PilotBundle.model_validate(data))


def test_local_parquet_extraction_filters_formats_and_preserves_lineage(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from scripts.extract_research_cache import extract

    config = bundle_data()
    for table_name, suffix in [("funda", ""), ("fundq", "q")]:
        folder = tmp_path / table_name
        folder.mkdir()
        row = {
            "tic": "TEST",
            "gvkey": "TEST",
            "conm": "Fictional company",
            "datadate": datetime(2024, 12, 31).date(),
            f"fyear{suffix}": 2024,
            f"curcd{suffix}": "USD",
            f"sale{suffix}": Decimal("120.000"),
            f"xsga{suffix}": Decimal("30.000"),
            "fqtr": 4,
            "indfmt": "INDL",
            "datafmt": "STD",
            "popsrc": "D",
            "consol": "C",
            "ingest_ts_utc": datetime(2025, 3, 1, tzinfo=UTC),
        }
        pq.write_table(
            pa.Table.from_pylist([row, {**row, "datafmt": "SUMM_STD"}, {**row, f"sale{suffix}": Decimal("0")}]),
            folder / "rows.parquet",
        )
        pq.write_table(pa.table({"tic": []}), folder / "empty.parquet")
    rows, counts = extract(tmp_path, config, datetime(2025, 6, 1, tzinfo=UTC))
    assert len(rows) == 2
    assert counts["empty_files"] == 2
    assert counts["invalid_revenue"] == 2
    assert all(r["source_row"] == 0 and len(r["source_sha256"]) == 64 for r in rows)
    assert {r["period"] for r in rows} == {"annual", "quarterly"}
    config["statements"] = rows
    assert analyze(PilotBundle.model_validate(config))["focal"]["sga"] == "30.000"
