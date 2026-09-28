"""The reviewer must not receive individually plausible but inconsistent exhibits."""

import json
import shutil
from pathlib import Path

import pytest
from scripts.check_progress_review import check_bundle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundle(tmp_path):
    target = tmp_path / "portfolio"
    target.mkdir()
    for path in (ROOT / "docs/portfolio").glob("*"):
        if path.suffix in {".json", ".html"}:
            shutil.copyfile(path, target / path.name)
    return target


def test_checked_in_bundle_reproduces_and_records_exact_files():
    result = check_bundle(ROOT / "docs/portfolio", ROOT / "data")
    assert len(result["checks"]) == 15
    assert all(c["status"] == "pass" for c in result["checks"])
    assert result["public_fact_count"] == 241
    assert result["case_revision_count"] == 10
    assert result["pilot_started"] is False
    assert result["independent_practitioner_review"] == "not_performed"
    assert all(len(v) == 64 for v in result["files_sha256"].values())


@pytest.mark.parametrize(
    ("name", "change", "expected"),
    [
        ("decision-memo", "headline", "memo-reproduction"),
        ("decision-memo", "old_context", "memo-reproduction"),
        ("progress-baseline", "public", "public-appendix"),
        ("historical-valuation", "proceeds", "historical-valuation"),
        ("case-history", "baseline", "frozen-close"),
        ("source-review", "accounting", "accounting-continuity"),
        ("lineage-review", "human", "authority-boundary"),
        ("lineage-review", "mapping", "lineage-boundary"),
    ],
)
def test_mixed_or_promoted_export_fails(bundle, name, change, expected):
    path = bundle / (name + ".json")
    data = json.loads(path.read_bytes())
    if change == "headline":
        data["public_baseline"]["derived"]["ebitda"]["value"] = "999999999"
    elif change == "old_context":
        data["source_review"]["current_revision_sha256"] = data["source_review"]["context"]["revisions"][-2][
            "content_sha256"
        ]
    elif change == "public":
        data["quarterly_derivations"]["quarters"][0]["status"] = "mismatch"
    elif change == "proceeds":
        data["transaction_proceeds"] = "1000000000"
    elif change == "baseline":
        data["close_baseline"]["frozen_forecast"]["year_one"]["incremental_ebitda"] = "0"
    elif change == "accounting":
        data["aggregate_recorded_periods"]["measured_difference"]["incremental_ebitda"] = "90000"
    elif change == "mapping":
        data["initiative_comparability"]["frozen_to_current"][0]["current_ids"] = ["unrelated"]
    else:
        data["human_review_count"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        check_bundle(bundle, ROOT / "data")


@pytest.mark.parametrize("name", ["decision-memo", "exit-review", "lineage-review"])
def test_stale_html_fails_even_when_all_json_is_valid(bundle, name):
    path = bundle / (name + ".html")
    path.write_text(path.read_text(encoding="utf-8") + "<p>Unverified claim</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="render"):
        check_bundle(bundle, ROOT / "data")
