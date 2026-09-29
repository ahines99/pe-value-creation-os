"""The executive exercise must expose capacity limits and preserve its frozen claims."""

import json
import shutil
from pathlib import Path

import pytest
from scripts.build_allocation_example import examples
from scripts.check_allocation_review import check_allocation

from pe_value_os.cli import main
from pe_value_os.diligence.allocation_demo import build_allocation_demo, render_allocation_demo
from pe_value_os.diligence.cases import CaseRevision, digest
from pe_value_os.diligence.memo import assemble_memo
from pe_value_os.diligence.memo_render import render_memo
from pe_value_os.diligence.memo_review import MemoReviewContext
from pe_value_os.diligence.scheduling import fingerprint

from .test_decision_memo import inputs

ROOT = Path("data/constructed/progress")


def test_authored_inputs_reproduce_exactly_and_preserve_resource_budgets():
    authored = examples()
    for name, model in authored.items():
        assert model.model_dump(mode="json") == json.loads((ROOT / (name + ".json")).read_text(encoding="utf-8"))
    old = json.loads((ROOT / "operating-plan.json").read_text(encoding="utf-8"))
    assert authored["allocation-plan"].model_dump(mode="json")["resources"] == old["resources"]
    assert authored["allocation-plan"].maximum_active_workstreams == old["maximum_active_workstreams"]


def test_installed_command_replays_choices_and_memo_without_reassigning_history(tmp_path):
    output = tmp_path / "allocation-review"
    args = ["allocation-demo", "--output", str(output)]
    for flag, name in (
        ("underwriting", "allocation-underwriting"),
        ("operating-plan", "allocation-plan"),
        ("exercise", "allocation-realization"),
        ("sources", "allocation-sources"),
    ):
        args.extend(["--" + flag, str(ROOT / (name + ".json"))])
    assert main(args) == 0
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    revisions = [CaseRevision.model_validate(r) for r in report["revisions"]]
    assert len(revisions) == 6
    assert all(report["source_review"]["continuity"].values())
    assert report["initial_capacity_challenge"]["blocked_tasks"] == ["pricing-review-targeted", "pricing-gate-targeted"]
    assert report["actual_company_realized_value"] is None and report["human_review_count"] == 0
    original = json.loads(revisions[0].financial_result_json)
    latest = json.loads(revisions[-1].financial_result_json)
    assert (
        "pricing-renewals" in original["selected_initiatives"]
        and "pricing-targeted" not in original["selected_initiatives"]
    )
    assert (
        "pricing-targeted" in latest["selected_initiatives"]
        and "pricing-renewals" not in latest["selected_initiatives"]
    )
    assert (
        next(s for s in latest["scenarios"] if s["scenario_id"] == "base")["year_one"]["incremental_ebitda"]
        == "-163165.00"
    )
    assert report["allocation_comparability"]["financial_attribution"] is None
    claims = [a for claim in report["attributions"] for a in claim["request"]["allocations"]]
    assert any(a["initiative_id"] == "pricing-renewals" for a in claims)
    assert not any(a["initiative_id"] == "pricing-targeted" for a in claims)
    html = output.with_suffix(".html").read_text(encoding="utf-8")
    assert html == render_allocation_demo(report, output.with_suffix(".json").name)
    assert "Rework the proposed first wave" in html
    data = inputs()
    authored = examples()
    data[0], data[4], data[5] = (
        authored["allocation-brief"],
        authored["allocation-underwriting"],
        authored["allocation-plan"],
    )
    context = MemoReviewContext.from_export(report)
    memo = assemble_memo(*data, context)
    assert memo["memo_version"] == "executive-decision-packet/6"
    assert memo["source_review"]["all_base_year_one_nonpositive"]
    assert memo["source_review"]["current_revision_sha256"] == revisions[-1].content_sha256
    assert memo["actual_realized_value"] is None and not memo["execution_authorized"]
    rendered = render_memo(memo)
    assert "One economic pool, explicit choices" in rendered
    assert "href='allocation-underwriting.html'" in rendered
    # Even a resigned envelope cannot pass reproduction with altered economics.
    altered = context.model_dump(mode="json")
    current = altered["revisions"][-1]
    financial = json.loads(current["financial_result_json"])
    financial["scenarios"][0]["year_one"]["incremental_ebitda"] = "1000000000"
    current["financial_result_json"] = json.dumps(financial, sort_keys=True)
    current["content_sha256"] = digest(
        json.dumps({k: v for k, v in current.items() if k != "content_sha256"}, sort_keys=True)
    )
    for receipt in altered["reviews"]:
        if receipt["revision_id"] == current["revision_id"]:
            receipt["revision_sha256"] = current["content_sha256"]
    with pytest.raises(ValueError, match="reproduced"):
        assemble_memo(*data, MemoReviewContext.model_validate(altered))
    assert fingerprint(context) != fingerprint(MemoReviewContext.model_validate(altered))


def test_allocation_demo_does_not_overwrite_input_or_its_companion(tmp_path):
    paths = [
        ROOT / (name + ".json")
        for name in ("allocation-underwriting", "allocation-plan", "allocation-realization", "allocation-sources")
    ]
    for output, message in ((paths[0], "overwrite"), (tmp_path / "allocation-sources", "distinct")):
        with pytest.raises(ValueError, match=message):
            build_allocation_demo(*paths, output)


def test_published_allocation_bundle_reproduces():
    result = check_allocation()
    assert len(result["checks"]) == 8
    assert all(c["status"] == "pass" for c in result["checks"])
    assert result["pilot_started"] is False


@pytest.mark.parametrize(
    "name,field,expected",
    [
        ("allocation-sources", "financial", "allocation-source-reproduction"),
        ("allocation-review", "accounting", "allocation-accounting-reproduction"),
    ],
)
def test_allocation_bundle_rejects_changed_exhibit_without_promoting_a_result(tmp_path, name, field, expected):
    for source in Path("docs/portfolio").glob("allocation-*"):
        if source.is_file():
            shutil.copyfile(source, tmp_path / source.name)
    path = tmp_path / (name + ".json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if field == "financial":
        raw["scenarios"][0]["year_one"]["incremental_ebitda"] = "1000000000"
    else:
        raw["aggregate_recorded_periods"]["attributed_difference"]["incremental_ebitda"] = "1000000000"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        check_allocation(tmp_path)
