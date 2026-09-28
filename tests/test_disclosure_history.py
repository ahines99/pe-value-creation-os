"""No future source leakage, silent vintage replacement or invented publication time."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from pe_value_os.diligence.vintages import AllocationHistory, analyze_vintages, select_vintage
from pe_value_os.diligence.vintages_render import build_vintage_report, render_vintages

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/public/progress/sharefile-allocation-history.json"


def raw():
    import json

    return json.loads(SOURCE.read_bytes())


def test_real_allocation_changes_and_reconciliation():
    history = AllocationHistory.model_validate(raw())
    report = analyze_vintages(history)
    changes = {r["metric"]: r["change"] for r in report["comparison"]}
    assert changes == {
        "working_capital": "1156000",
        "ppe": "0",
        "technology": "0",
        "trade_name": "0",
        "customer_relationships": "-1000000",
        "deferred_taxes": "-378000",
        "deferred_revenue": "-96000",
        "goodwill": "1513000",
        "net_assets": "1195000",
    }
    assert report["point_in_time_claim"] == "withheld"
    assert len(report["reconciliations"]) == 2
    assert report["history"]["revision_kind"] == "measurement_period_adjustment"


def test_earlier_cutoff_never_gets_revised_allocation():
    history = AllocationHistory.model_validate(raw())
    before = history.model_dump_json()
    results = analyze_vintages(history)["cutoffs"]
    assert results[0]["acceptance_selection"]["selected"] is None
    assert [r["acceptance_selection"]["selected"]["status"] for r in results[1:]] == [
        "preliminary",
        "preliminary",
        "final",
    ]
    assert "460972" not in str(results[2]["acceptance_selection"])
    assert history.model_dump_json() == before
    assert all(r["publication_selection"]["selected"] is None for r in results)


def test_missing_timestamp_blocks_even_when_an_older_filing_has_availability():
    data = raw()
    older = data["vintages"][0]
    older["public_available"] = {
        "timestamp": "2025-01-21T16:25:00-05:00",
        "source_url": "https://example.com/fictional-test-publication-log",
        "locator": "Synthetic timestamp for this test only",
    }
    history = AllocationHistory.model_validate(data)
    result = select_vintage(history, datetime.fromisoformat("2026-02-01T00:00:00+00:00"), basis="public_availability")
    assert result["selected"] is None
    assert result["unknown"] == [history.vintages[1].vintage_id]


def test_availability_cutoff_uses_evidence_time_not_acceptance():
    data = raw()
    first = data["vintages"][0]
    first["public_available"] = {
        "timestamp": "2025-01-21T16:25:00-05:00",
        "source_url": "https://example.com/fictional-test-publication-log",
        "locator": "Synthetic timestamp for this test only",
    }
    history = AllocationHistory.model_validate(data)
    assert (
        select_vintage(history, datetime.fromisoformat("2025-01-21T21:24:00+00:00"), basis="public_availability")[
            "selected"
        ]
        is None
    )
    at = select_vintage(history, datetime.fromisoformat("2025-01-21T21:25:00+00:00"), basis="public_availability")
    assert at["selected"]["status"] == "preliminary"


@pytest.mark.parametrize(
    "mutation",
    [
        "private",
        "wrong_entity",
        "duplicate",
        "reverse",
        "unreconciled",
        "missing_row",
        "wrong_units",
        "future_availability",
        "naive",
        "restatement",
    ],
)
def test_invalid_or_misrepresented_history_rejected(mutation):
    data = raw()
    old, new = data["vintages"]
    if mutation == "private":
        old["document"]["classification"] = "licensed_private"
    elif mutation == "wrong_entity":
        new["document"]["entity_id"] = "different-company"
    elif mutation == "duplicate":
        new["document"]["accession"] = old["document"]["accession"]
    elif mutation == "reverse":
        data["vintages"].reverse()
    elif mutation == "unreconciled":
        new["rows"][0]["reported_amount"] = "0"
    elif mutation == "missing_row":
        new["rows"].pop()
    elif mutation == "wrong_units":
        new["unit_scale"] = 1
    elif mutation == "future_availability":
        new["public_available"] = deepcopy(new["accepted"])
        new["public_available"]["timestamp"] = "2099-01-01T00:00:00+00:00"
    elif mutation == "naive":
        new["accepted"]["timestamp"] = "2026-01-20T16:12:13"
    else:
        data["revision_kind"] = "accounting_error_restatement"
    with pytest.raises(ValueError):
        AllocationHistory.model_validate(data)


def test_delayed_older_availability_does_not_replace_newer_revision():
    data = raw()
    for vintage, timestamp in zip(
        data["vintages"], ["2026-01-22T00:00:00+00:00", "2026-01-21T00:00:00+00:00"], strict=True
    ):
        vintage["public_available"] = {
            "timestamp": timestamp,
            "source_url": "https://example.com/fictional-test-publication-log",
            "locator": "Synthetic delayed publication for this test only",
        }
    history = AllocationHistory.model_validate(data)
    result = select_vintage(history, datetime.fromisoformat("2026-02-01T00:00:00+00:00"), basis="public_availability")
    assert result["selected"]["status"] == "final"


def test_naive_cutoff_and_invalid_basis_rejected():
    history = AllocationHistory.model_validate(raw())
    with pytest.raises(ValueError, match="timezone"):
        select_vintage(history, datetime(2025, 2, 1), basis="acceptance")
    with pytest.raises(ValueError, match="basis"):
        select_vintage(history, datetime.fromisoformat("2025-02-01T00:00:00+00:00"), basis="invented")


def test_public_export_and_output_collision(tmp_path):
    path = build_vintage_report(SOURCE, tmp_path / "history")
    html = path.read_text(encoding="utf-8")
    assert "Withheld" in html and "1.195" in html
    assert "not a realized investment return" in html
    assert (tmp_path / "history.json").is_file()
    with pytest.raises(ValueError, match="overwrite"):
        build_vintage_report(SOURCE, SOURCE)
    report = analyze_vintages(AllocationHistory.model_validate(raw()))
    report["history"]["revision_explanation"] = "<script>bad()</script>"
    assert "<script>bad" not in render_vintages(report, "download.json")


def test_committed_report_matches_current_inputs():
    import json

    expected = analyze_vintages(AllocationHistory.model_validate(raw()))
    assert json.loads((ROOT / "docs/portfolio/disclosure-history.json").read_bytes()) == expected
