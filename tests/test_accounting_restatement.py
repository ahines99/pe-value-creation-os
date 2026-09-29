"""Original-source preservation, non-reliance, financial reconciliation and timing."""

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pytest

from pe_value_os.diligence.restatements import (
    RestatementHistory,
    analyze_restatement,
    select_by_disclosed_date,
    select_by_publication,
)
from pe_value_os.diligence.restatements_render import build_restatement_report, render_restatement

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/public/progress/accounting-restatement-history.json"


def raw():
    return json.loads(SOURCE.read_bytes())


def test_worked_correction_distinguishes_earnings_cash_and_reclassification():
    report = analyze_restatement(RestatementHistory.model_validate(raw()))
    rows = {r["metric"]: r for r in report["comparison"]}
    assert rows["net_income"] == {
        "metric": "net_income",
        "label": "Net income",
        "original": "48933000",
        "adjustment": "-2676000",
        "restated": "46257000",
    }
    assert rows["operating_income"]["adjustment"] == "-3815000"
    assert rows["operating_cash_flow"]["adjustment"] == "0"
    assert rows["cash"]["adjustment"] == "-17001000"
    assert rows["short_term_investments"]["adjustment"] == "17001000"
    assert rows["cash_and_investments"]["adjustment"] == "0"
    assert rows["change_in_cash"]["adjustment"] == "-5501000"
    # The 5.501m movement plus the 11.500m opening reclassification explains
    # the 17.001m closing cash change; no EBITDA or operating-saving inference.
    assert report["public_availability"]["selected"] is None


def test_notice_suspends_numbers_without_leaking_correction_or_rewriting_original():
    history = RestatementHistory.model_validate(raw())
    before = history.model_dump_json()
    original = select_by_disclosed_date(history, date(2006, 8, 28))
    assert original["selected"]["snapshot_id"] == history.original.snapshot_id
    assert "46257" not in json.dumps(original)
    for day, state in [(date(2006, 8, 29), "non_reliance"), (date(2006, 12, 18), "restatement_announcement")]:
        result = select_by_disclosed_date(history, day)
        assert result["status"] == state and result["selected"] is None
        assert "46257" not in json.dumps(result)
    assert (
        select_by_disclosed_date(history, date(2006, 12, 19))["selected"]["snapshot_id"] == history.amended.snapshot_id
    )
    assert select_by_disclosed_date(history, date(2006, 2, 9))["selected"] is None
    assert history.model_dump_json() == before


def timestamp(when):
    return {
        "timestamp": when,
        "source_url": "https://example.com/fictional-publication-log",
        "locator": "Synthetic timestamp for selector tests, not historical evidence",
    }


def test_exact_selector_uses_publication_time_and_notice_not_filing_metadata():
    data = raw()
    times = [
        "2006-02-10T17:00:00-05:00",
        "2006-08-29T17:00:00-04:00",
        "2006-12-18T18:00:00-05:00",
        "2006-12-19T18:00:00-05:00",
    ]
    for event, when in zip(data["events"], times, strict=True):
        event["public_available"] = timestamp(when)
    history = RestatementHistory.model_validate(data)
    before = select_by_publication(history, datetime.fromisoformat("2006-02-10T16:30:00-05:00"))
    assert before["selected"] is None  # Accepted, but synthetic availability is later.
    assert select_by_publication(history, datetime.fromisoformat(times[0]))["status"] == "original_filing"
    assert select_by_publication(history, datetime.fromisoformat(times[1]))["selected"] is None
    assert select_by_publication(history, datetime.fromisoformat(times[2]))["selected"] is None
    assert select_by_publication(history, datetime.fromisoformat(times[3]))["status"] == "amended_filing"
    data["events"][1]["public_available"] = None
    missing_notice = select_by_publication(RestatementHistory.model_validate(data), datetime.fromisoformat(times[3]))
    assert missing_notice["selected"] is None
    assert missing_notice["unknown"] == ["non-reliance-announcement"]


@pytest.mark.parametrize(
    "mutation",
    [
        "original_replaced",
        "entity",
        "period",
        "private",
        "same_source",
        "wrong_form",
        "missing_notice",
        "event_date",
        "date_basis",
        "duplicate_metric",
        "statement_total",
        "correction_total",
        "correction_original",
        "income_bridge",
        "future_timestamp",
        "naive_timestamp",
    ],
)
def test_invalid_histories_rejected(mutation):
    data = raw()
    if mutation == "original_replaced":
        data["original"]["rows"] = deepcopy(data["amended"]["rows"])
    elif mutation == "entity":
        data["amended"]["entity_id"] = "different-company"
    elif mutation == "period":
        data["amended"]["period_start"] = "2004-12-02"
    elif mutation == "private":
        data["original"]["classification"] = "permissioned_private"
    elif mutation == "same_source":
        data["amended"]["sha256"] = data["original"]["sha256"]
    elif mutation == "wrong_form":
        data["amended"]["form"] = "10-K"
    elif mutation == "missing_notice":
        data["events"].pop(1)
    elif mutation == "event_date":
        data["events"][1]["reported_on"] = "2007-01-01"
    elif mutation == "date_basis":
        data["events"][1]["date_basis"] = "filing_metadata"
    elif mutation == "duplicate_metric":
        data["original"]["rows"][1] = deepcopy(data["original"]["rows"][0])
    elif mutation == "statement_total":
        data["original"]["rows"][0]["amount"] = "1"
    elif mutation == "correction_total":
        data["corrections"][0]["adjustment"] = "1"
    elif mutation == "correction_original":
        data["corrections"][0]["originally_reported"] = "1"
    elif mutation == "income_bridge":
        data["net_income_bridge"]["additional_stock_compensation"] = "1"
    elif mutation == "future_timestamp":
        data["events"][0]["public_available"] = timestamp("2099-01-01T00:00:00+00:00")
    else:
        data["events"][0]["public_available"] = timestamp("2006-02-10T17:00:00")
    with pytest.raises(ValueError):
        RestatementHistory.model_validate(data)


def test_time_precision_and_export_safety(tmp_path):
    history = RestatementHistory.model_validate(raw())
    with pytest.raises(ValueError, match="timezone"):
        select_by_publication(history, datetime(2006, 3, 1))
    with pytest.raises(ValueError, match="intraday"):
        select_by_disclosed_date(history, datetime(2006, 3, 1))
    with pytest.raises(ValueError, match="overwrite"):
        build_restatement_report(SOURCE, SOURCE)
    output = build_restatement_report(SOURCE, tmp_path / "restatement")
    report = analyze_restatement(history)
    assert json.loads(output.with_suffix(".json").read_bytes()) == report
    html = output.read_text(encoding="utf-8")
    assert "Withheld" in html and "48.933" in html and "46.257" in html
    assert "not an operating cash-saving initiative" in html
    report["history"]["events"][0]["locator"] = "<script>bad()</script>"
    assert "<script>bad" not in render_restatement(report, "data.json")


def test_committed_report_and_cli_are_reproducible(tmp_path):
    from pe_value_os.cli import main

    assert main(["restatement-history", "--input", str(SOURCE), "--output", str(tmp_path / "report")]) == 0
    assert (tmp_path / "report.json").read_bytes() == (ROOT / "docs/portfolio/accounting-restatement.json").read_bytes()
    assert (tmp_path / "report.html").read_text(encoding="utf-8").replace(
        "report.json", "accounting-restatement.json"
    ) == (ROOT / "docs/portfolio/accounting-restatement.html").read_text(encoding="utf-8")
