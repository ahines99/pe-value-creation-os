"""Reproduce the separate allocation exhibits and frozen accounting without network access."""

import argparse
import hashlib
import json
from pathlib import Path

from pe_value_os.diligence.allocation_demo import render_allocation_demo
from pe_value_os.diligence.balances import BalanceBundle
from pe_value_os.diligence.cases import InvestmentCase
from pe_value_os.diligence.close_baseline import CloseBaseline
from pe_value_os.diligence.growth import GrowthContext
from pe_value_os.diligence.interactions import InteractionCase
from pe_value_os.diligence.memo import DecisionBrief, assemble_memo
from pe_value_os.diligence.memo_render import render_memo
from pe_value_os.diligence.memo_review import MemoReviewContext
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.operating_sources import source_forecast
from pe_value_os.diligence.operating_sources_render import render_sources
from pe_value_os.diligence.peers import PeerContext
from pe_value_os.diligence.realization import Attribution, Observation, realization_report
from pe_value_os.diligence.scheduling import OperatingPlan, evaluate_plan
from pe_value_os.diligence.scheduling_render import render_plan
from pe_value_os.diligence.source_revisions import financial_snapshot, source_payload
from pe_value_os.diligence.underwriting import evaluate
from pe_value_os.diligence.underwriting_render import render_underwriting
from pe_value_os.diligence.valuation import ValuationSpec


def normalized(value):
    return json.loads(json.dumps(value, default=str))


def check_allocation(portfolio=Path("docs/portfolio"), data=Path("data")):
    files, checks = {}, []

    def read(path):
        raw = path.read_bytes()
        files[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw.decode("utf-8").replace("\r\n", "\n")

    def check(value, label):
        if not value:
            raise ValueError(label)
        checks.append({"id": label, "status": "pass"})

    def artifact(name):
        return json.loads(read(portfolio / (name + ".json")))

    constructed, public = data / "constructed/progress", data / "public/progress"
    report = artifact("allocation-review")
    context = MemoReviewContext.from_export(report)
    case = InteractionCase.model_validate_json(read(constructed / "allocation-underwriting.json"))
    plan = OperatingPlan.model_validate_json(read(constructed / "allocation-plan.json"))
    check(
        context.revisions[0].draft.payload.underwriting == case
        and context.revisions[1].draft.payload.operating_plan == plan,
        "allocation-original-inputs",
    )
    underwriting = artifact("allocation-underwriting")
    operating = artifact("allocation-operating-plan")
    underwriting_calculated, operating_calculated = evaluate(case), evaluate_plan(plan, case)
    check(
        underwriting == normalized(underwriting_calculated) and operating == normalized(operating_calculated),
        "allocation-original-forecasts",
    )
    for index, revision in enumerate(context.revisions):
        basis = source_payload(revision.draft.payload)
        if basis:
            projected = financial_snapshot(
                basis,
                context.revisions[index - 1],
                source_forecast(basis.operating_sources, basis.underwriting, basis.operating_plan),
            )
        elif revision.draft.payload.operating_plan:
            projected = evaluate_plan(revision.draft.payload.operating_plan, revision.draft.payload.underwriting)[
                "scheduled_financials"
            ]
        else:
            projected = evaluate(revision.draft.payload.underwriting)
        if normalized(projected) != json.loads(revision.financial_result_json):
            raise ValueError("allocation-revision-reproduction")
    check(True, "allocation-revision-reproduction")
    latest = source_payload(context.revisions[-1].draft.payload)
    assert latest is not None
    sources = artifact("allocation-sources")
    source_calculated = source_forecast(latest.operating_sources, latest.underwriting, latest.operating_plan)
    check(
        sources == normalized(source_calculated),
        "allocation-source-reproduction",
    )
    baseline = CloseBaseline.model_validate(report["baseline"]["baseline"])
    accounting = normalized(
        realization_report(
            InvestmentCase.model_validate(report["source_review"]["case_snapshot"]),
            baseline,
            list(context.revisions),
            list(context.reviews),
            [baseline],
            [Observation.model_validate(r) for r in report["observations"]],
            [Attribution.model_validate(r) for r in report["attributions"]],
        )
    )
    check(all(report[k] == value for k, value in accounting.items()), "allocation-accounting-reproduction")
    memo = artifact("allocation-memo")
    calculated = assemble_memo(
        DecisionBrief.model_validate_json(read(constructed / "allocation-brief.json")),
        FactBundle.model_validate_json(read(public / "financial-facts.json")),
        GrowthContext.model_validate_json(read(public / "growth-context.json")),
        PeerContext.model_validate_json(read(public / "peer-context.json")),
        case,
        plan,
        BalanceBundle.model_validate_json(read(public / "balance-facts.json")),
        ValuationSpec.model_validate_json(read(constructed / "historical-valuation.json")),
        context,
    )
    check(memo == normalized(calculated), "allocation-memo-reproduction")
    check(
        report["actual_company_realized_value"] is None
        and report["human_review_count"] == 0
        and memo["actual_realized_value"] is None
        and memo["execution_authorized"] is False
        and report["allocation_comparability"]["financial_attribution"] is None
        and all(r.mode == "simulation" for r in context.reviews),
        "allocation-authority",
    )
    rendered = {
        "allocation-review": render_allocation_demo(report, "allocation-review.json"),
        "allocation-sources": render_sources(source_calculated, "allocation-sources.json"),
        "allocation-memo": render_memo(memo, "allocation-memo.json"),
        "allocation-underwriting": render_underwriting(case, underwriting_calculated),
        "allocation-operating-plan": render_plan(plan, operating_calculated),
    }
    check(
        all(read(portfolio / (name + ".html")) == html for name, html in rendered.items()),
        "allocation-rendered-exhibits",
    )
    return {
        "classification": "automated_internal_engineering_check",
        "checks": checks,
        "files_sha256": files,
        "current_revision_sha256": context.revisions[-1].content_sha256,
        "independent_practitioner_review": "not_performed",
        "pilot_started": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("var/allocation-review/checks.json"))
    args = parser.parse_args()
    if any(args.output.resolve().is_relative_to(Path(p).resolve()) for p in ("docs", "data")):
        parser.error("receipt must be outside the published documents and input data")
    result = check_allocation()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(result['checks'])} allocation review consistency checks")
