"""Check the linked Progress review bundle against its allowed inputs, without network access.

This is a release consistency check, not independent finance or practitioner review.
Run from the repository root: uv run python scripts/check_progress_review.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pe_value_os.diligence.balances import BalanceBundle
from pe_value_os.diligence.exit_demo import render_exit
from pe_value_os.diligence.exit_review import ExitAssumptions, ExitReviewPayload
from pe_value_os.diligence.growth import GrowthContext
from pe_value_os.diligence.memo import DecisionBrief, assemble_memo
from pe_value_os.diligence.memo_render import render_memo
from pe_value_os.diligence.memo_review import MemoReviewContext
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.operating_sources import OperatingSourceBook, source_forecast
from pe_value_os.diligence.peers import PeerContext
from pe_value_os.diligence.quarterly import derive_quarters
from pe_value_os.diligence.scheduling import OperatingPlan, evaluate_plan, fingerprint
from pe_value_os.diligence.underwriting import UnderwritingCase, evaluate
from pe_value_os.diligence.valuation import ValuationSpec


def normalized(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def check_bundle(portfolio: Path, data: Path) -> dict[str, Any]:
    """Fail on a stale/mixed bundle, altered headline, promoted result or stale rendered page."""
    files: dict[str, str] = {}
    checks: list[dict[str, str]] = []

    def read(path: Path) -> str:
        raw = path.read_bytes()
        files[path.as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw.decode("utf-8").replace("\r\n", "\n")

    def artifact(name: str) -> Any:
        return json.loads(read(portfolio / (name + ".json")))

    def require(condition: bool, check_id: str, description: str) -> None:
        if not condition:
            raise ValueError(f"{check_id}: {description}")
        checks.append({"id": check_id, "status": "pass", "description": description})

    public, constructed = data / "public/progress", data / "constructed/progress"
    brief = DecisionBrief.model_validate_json(read(constructed / "decision-brief.json"))
    facts = FactBundle.model_validate_json(read(public / "financial-facts.json"))
    growth = GrowthContext.model_validate_json(read(public / "growth-context.json"))
    peers = PeerContext.model_validate_json(read(public / "peer-context.json"))
    underwriting = UnderwritingCase.model_validate_json(read(constructed / "underwriting.json"))
    plan = OperatingPlan.model_validate_json(read(constructed / "operating-plan.json"))
    balances = BalanceBundle.model_validate_json(read(public / "balance-facts.json"))
    valuation = ValuationSpec.model_validate_json(read(constructed / "historical-valuation.json"))
    exit_report, memo = artifact("exit-review"), artifact("decision-memo")
    context = MemoReviewContext.from_export(exit_report)
    payload = context.revisions[-1].draft.payload
    assumptions = ExitAssumptions.model_validate_json(read(constructed / "exit-assumptions.json"))
    require(
        isinstance(payload, ExitReviewPayload)
        and payload.public_facts == facts
        and payload.public_balances == balances
        and payload.historical_valuation == valuation
        and payload.exit_assumptions == assumptions,
        "exit-inputs",
        "Exit revision retains the current declared public anchors and authored sensitivity inputs.",
    )
    book = OperatingSourceBook.model_validate_json(read(constructed / "operating-sources.json"))
    require(
        exit_report["source_review"]["supplied_source_book_sha256"] == fingerprint(book)
        and artifact("operating-sources") == normalized(source_forecast(book, underwriting, plan)),
        "operating-source-inputs",
        "The original source challenge reproduces; later evidence corrections remain separate revisions.",
    )
    reproduced = normalized(
        assemble_memo(brief, facts, growth, peers, underwriting, plan, balances, valuation, context)
    )
    require(
        memo == reproduced,
        "memo-reproduction",
        "Memo reproduces from allowed inputs and the exact exported exit history.",
    )

    appendix = artifact("progress-baseline")
    expected_appendix = {
        **memo["public_financials"],
        "quarterly_derivations": normalized(derive_quarters(facts)),
        "growth_analysis": memo["public_growth"],
        "peer_analysis": memo["public_peers"],
    }
    require(
        appendix == expected_appendix, "public-appendix", "Public financial, growth and peer exhibits match the memo."
    )
    require(
        artifact("historical-valuation") == memo["historical_valuation"],
        "historical-valuation",
        "Historical valuation exhibit matches the memo's separate company-level model.",
    )
    require(
        artifact("underwriting") == normalized(evaluate(underwriting)),
        "original-underwriting",
        "Original monthly underwriting reproduces without using the later source corrections.",
    )
    require(
        artifact("operating-plan") == normalized(evaluate_plan(plan, underwriting)),
        "capacity-plan",
        "Original capacity schedule and its financial timing reproduce from the bound plan.",
    )

    baseline = exit_report["baseline"]["frozen_forecast"]
    require(
        artifact("case-history")["close_baseline"]["frozen_forecast"] == baseline,
        "frozen-close",
        "Standalone close and latest lifecycle retain the same frozen financial baseline.",
    )
    source = artifact("source-review")
    accounting_keys = ("measured_difference", "attributed_difference", "unassigned_residual")
    require(
        all(
            source["aggregate_recorded_periods"][k] == exit_report["aggregate_recorded_periods"][k]
            for k in accounting_keys
        ),
        "accounting-continuity",
        "Exit sensitivity does not change the recorded accounting difference, claims or residual.",
    )
    aggregate = exit_report["aggregate_recorded_periods"]
    require(
        all(
            Decimal(aggregate["measured_difference"][k])
            == Decimal(aggregate["attributed_difference"][k]) + Decimal(aggregate["unassigned_residual"][k])
            for k in ("incremental_ebitda", "pre_tax_cash_proxy")
        ),
        "attribution-reconciliation",
        "Recorded difference equals attributed claims plus the unassigned residual in each financial measure.",
    )
    latest = memo["source_review"]["latest_financials"]
    exit_values = latest["exit_review"]
    require(
        memo["execution_authorized"] is False
        and memo["actual_realized_value"] is None
        and exit_report["actual_company_realized_value"] is None
        and exit_report["human_review_count"] == 0
        and all(
            exit_values[k] is None
            for k in (
                "transaction_proceeds",
                "shareholder_distributions",
                "actual_exit_date",
                "current_company_valuation",
                "investment_return",
            )
        ),
        "authority-boundary",
        "Constructed records confer no company approval, realized company result or exit proceeds.",
    )
    require(
        read(portfolio / "decision-memo.html") == render_memo(memo),
        "memo-render",
        "Rendered executive memo is exactly the output of its verified JSON packet.",
    )
    require(
        read(portfolio / "exit-review.html") == render_exit(exit_report, "exit-review.json"),
        "exit-render",
        "Rendered exit exhibit is exactly the output of its verified lifecycle export.",
    )
    return {
        "version": "progress-review-consistency/1",
        "classification": "automated_internal_engineering_check",
        "checks": checks,
        "files_sha256": files,
        "case_revision_sha256": context.revisions[-1].content_sha256,
        "public_fact_count": len(facts.facts),
        "case_revision_count": len(context.revisions),
        "independent_practitioner_review": "not_performed",
        "pilot_started": False,
        "limits": "Reproduction uses the application calculators. It checks this linked bundle, not source-document accuracy, independent commercial judgment, human comprehension, all runtime security, or a real pilot. See the acceptance matrix and separate CI evidence.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", type=Path, default=Path("docs/portfolio"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("var/progress-review/checks.json"))
    args = parser.parse_args()
    # The checker may write a receipt, never an input or a published exhibit.
    if any(args.output.resolve().is_relative_to(p.resolve()) for p in (args.portfolio, args.data)):
        parser.error("receipt must be outside the portfolio and data directories")
    try:
        report = check_bundle(args.portfolio, args.data)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Progress review check failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(report['checks'])} Progress review consistency checks; receipt {args.output}")


if __name__ == "__main__":
    main()
