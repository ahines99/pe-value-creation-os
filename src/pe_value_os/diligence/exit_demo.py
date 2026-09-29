"""Extend the saved source challenge through a constructed, reviewed exit sensitivity."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..adapters.repositories import Repository
from ..api.presentation import CSS
from ..research.render import table
from .balances import BalanceBundle
from .cases import CaseRevision, InvestmentCase, ReviewRequest, RevisionDraft
from .close_baseline import CloseBaseline
from .execution_demo import ExecutionExercise, replay_execution
from .exit_review import ExitAssumptions, ExitReviewPayload
from .models import FactBundle
from .operating_sources import OperatingSourceBook
from .realization_render import RealizationExercise, demonstrate_realization
from .scheduling import OperatingPlan, fingerprint
from .source_review_demo import replay_source_review
from .source_revisions import SourceCasePayload, source_payload
from .underwriting import UnderwritingCase
from .valuation import ValuationSpec


def exit_draft(
    parent: CaseRevision,
    facts: FactBundle,
    balances: BalanceBundle,
    valuation: ValuationSpec,
    assumptions: ExitAssumptions,
) -> RevisionDraft:
    prior = source_payload(parent.draft.payload)
    if prior is None:
        raise ValueError("exit review requires a prior source-backed ownership review")
    source = SourceCasePayload.model_validate(
        {
            **prior.model_dump(mode="json"),
            "challenged_revision_id": parent.revision_id,
            "challenged_revision_sha256": parent.content_sha256,
            "decision_question": "What does the exit sensitivity show, and what evidence prevents a proceeds claim?",
            "unresolved_items": [
                *prior.unresolved_items,
                "No maintainable consolidated forecast, actual transaction, settlement or distribution evidence.",
            ],
        }
    )
    return RevisionDraft(
        stage="exit_review",
        effective_on=assumptions.exit_on,
        reason="Review a constructed exit sensitivity; preserve the adverse source forecast and frozen close.",
        payload=ExitReviewPayload(
            schema_version=3,
            source_basis=source,
            public_facts=facts,
            public_balances=balances,
            historical_valuation=valuation,
            exit_assumptions=assumptions,
        ),
    )


def replay_exit(
    repo: Repository,
    case: InvestmentCase,
    baseline: CloseBaseline,
    book: OperatingSourceBook,
    exercise: ExecutionExercise,
    facts: FactBundle,
    balances: BalanceBundle,
    valuation: ValuationSpec,
    assumptions: ExitAssumptions,
) -> dict[str, Any]:
    source = replay_source_review(repo, case, baseline, book, exercise.exercise_as_of + timedelta(days=1))
    current = repo.get_investment_case(case.case_id)
    assert current.current_revision_id is not None
    parent = repo.get_case_revision(current.current_revision_id)
    before = repo.case_realization(case.case_id, baseline.baseline_id)
    revision = repo.append_case_revision(
        case.case_id, parent.revision_id, exit_draft(parent, facts, balances, valuation, assumptions)
    )
    receipt = repo.review_case_revision(
        revision.revision_id,
        ReviewRequest(
            expected_revision_sha256=revision.content_sha256,
            mode="simulation",
            decision="accept",
            rationale="Simulated acceptance of scenario arithmetic and evidence limits. No sale, transaction valuation, realized return or operating action is approved.",
        ),
    )
    after = repo.case_realization(case.case_id, baseline.baseline_id)
    for key in ("baseline", "observations", "attributions", "aggregate_recorded_periods"):
        if before[key] != after[key]:
            raise ValueError("exit review must preserve the frozen baseline, accounting, claims and operating forecast")
    return {
        **source,
        "reviews": [r.model_dump(mode="json") for r in repo.list_case_reviews(case.case_id)],
        "exit_checkpoint": {
            "revision_id": revision.revision_id,
            "revision_sha256": revision.content_sha256,
            "review": receipt.model_dump(mode="json"),
            "preserved_accounting_and_claims": True,
        },
    }


def millions(value: Any) -> str:
    return "Withheld" if value is None else f"{Decimal(str(value)) / 1000000:,.3f}"


def render_exit(report: dict[str, Any], download: str) -> str:
    latest = report["revisions"][-1]
    result = json.loads(latest["financial_result_json"])["exit_review"]
    spec = result["assumptions"]
    body = (
        "<section class='hero'><div><p class='eyebrow'>Progress reference case / Constructed exit review</p>"
        "<h1>Review the exit case</h1>"
        "<p class='page-subtitle'>Separate earnings assumptions, multiple effects and the equity claim.</p>"
        f"<p>Authored review date {escape(spec['exit_on'])}. Historical public earnings and capital claims anchor "
        "this hypothetical sensitivity. No ownership, sale or company forecast is established.</p></div>"
        "<aside class='hero-aside'><span class='metric-label'>Actual transaction proceeds</span>"
        "<strong class='metric-value'>Unavailable</strong><span class='metric-note'>A simulated research review cannot create a disposal or distribution.</span></aside></section>"
        "<section class='panel' id='decision'><h2>Retain the exercise; withhold a sale conclusion</h2>"
        "<p>The original underwriting, reviewed hypothetical close, constructed accounting and corrected source forecast remain intact. "
        "The sixth revision adds a sensitivity and simulated review. It does not close an investment or release capital.</p>"
        "<p><strong>Next evidence:</strong> a reconciled maintainable consolidated earnings bridge, updated post-acquisition debt and cash, "
        "transaction terms, ownership and settlement evidence. Initiative splits and exact historical information availability remain separate open work.</p></section>"
        "<section class='panel' id='matrix'><h2>Investment-level sensitivity / USD millions</h2>"
        f"<p>Historical calculated EBITDA: {millions(result['historical_reference']['earnings']['value'])}; "
        f"assumed starting multiple: {escape(spec['entry_multiple'])}x. "
        f"Selected claim convention: {escape(result['claim_scenario']['label'])}.</p>"
    )
    body += table(
        ["Assumed earnings factor", "Exit multiple", "EBITDA", "Enterprise value", "Equity sensitivity"],
        [
            [escape(r["earnings_factor"]) + "x", escape(r["multiple"]) + "x"]
            + [
                millions(r[k])
                for k in ("terminal_ebitda_sensitivity", "enterprise_value_sensitivity", "equity_sensitivity")
            ]
            for r in result["rows"]
        ],
        "Author-selected scenarios, not forecasts or probabilities. Negative equity residuals remain visible as arithmetic funding shortfalls.",
    )
    body += f"<p>{escape(spec['earnings_rationale'])}</p><p>{escape(spec['multiple_rationale'])}</p></section>"
    body += "<section class='panel' id='bridge'><h2>Explain the change in enterprise value</h2>"
    body += table(
        [
            "Earnings factor / exit multiple",
            "Earnings effect",
            "Multiple effect",
            "Interaction",
            "Rounding",
            "Total EV change",
        ],
        [
            [escape(r["earnings_factor"]) + "x / " + escape(r["multiple"]) + "x"]
            + [
                millions(r["decomposition"][k]) if r["decomposition"] else "Withheld"
                for k in (
                    "earnings_change_at_entry_multiple",
                    "multiple_change_on_starting_earnings",
                    "earnings_multiple_interaction",
                    "rounding_residual",
                )
            ]
            + [millions(r["ev_change"])]
            for r in result["rows"]
        ],
        "Starting multiple × earnings change + starting earnings × multiple change + interaction + rounding = total EV change.",
    )
    body += "<p>Multiple effects and interaction stay at the investment level; they are not operating-initiative attribution.</p></section>"
    body += "<section class='panel' id='claims'><h2>From enterprise value to the equity residual</h2>"
    anchor = result["entry_anchor"]
    labels = [
        ("cash_added", "Available cash added"),
        ("nonoperating_assets_added", "Other assets added"),
        ("debt_principal_deducted", "Debt principal deducted"),
        ("lease_claim_deducted", "Lease claims deducted"),
        ("other_claims_deducted", "Other claims deducted"),
        ("transaction_costs_deducted", "Transaction costs deducted"),
    ]
    body += table(
        ["Historical / assumed claim", "USD millions"],
        [[label, millions(anchor.get(k))] for k, label in labels],
        "EV + available cash + other assets − debt principal − selected lease claims − other claims − costs. All inherited claim assumptions remain explicit.",
    )
    body += f"<p>{escape(spec['capital_structure_rationale'])}</p><p>Equity sensitivity is not consideration received by shareholders. Ownership, dilution, tax and settlement are unresolved.</p>"
    body += (
        "<details><summary>Inspect inherited claim and settlement assumptions</summary><pre>"
        + escape(json.dumps(result["claim_scenario"], indent=2))
        + "</pre></details></section>"
    )
    body += "<section class='panel' id='operating'><h2>What the operating evidence can support</h2>"
    body += table(
        [
            "Operating scenario",
            "Terminal month",
            "Incremental EBITDA / USD",
            "Vendor cost removed / USD",
            "Maintainable annual uplift",
        ],
        [
            [
                escape(r["scenario_id"]),
                escape(r["terminal_month"]["start"]),
                f"{Decimal(r['terminal_month']['incremental_ebitda']):,.2f}",
                f"{Decimal(r['terminal_month']['cost_removed']):,.2f}",
                "Unavailable",
            ]
            for r in result["operating_scope_review"]
        ],
        "Scoped constructed operating records remain outside consolidated exit earnings. Expired price terms and unsupported vendor release do not become a perpetual uplift.",
    )
    body += f"<p>{escape(spec['operating_scope_rationale'])}</p></section>"
    body += "<section class='panel' id='history'><h2>Six revisions; original accounting retained</h2>"
    body += table(
        ["Revision", "Stage", "Authored effective date", "Exact content hash"],
        [
            [
                str(r["sequence"]),
                escape(r["draft"]["stage"].replace("_", " ")),
                escape(r["draft"]["effective_on"]),
                "<code>" + escape(r["content_sha256"]) + "</code>",
            ]
            for r in report["revisions"]
        ],
        "Effective dates are authored exercise dates; recorded timestamps remain in the export. All review receipts are simulated.",
    )
    aggregate = report["aggregate_recorded_periods"]
    measured = Decimal(aggregate["measured_difference"]["incremental_ebitda"])
    attributed = Decimal(aggregate["attributed_difference"]["incremental_ebitda"])
    body += f"<p>The source review's ${measured:,.0f} constructed accounting difference and ${attributed:,.0f} attributed EBITDA claim are unchanged. Neither figure is actual company realization or exit proceeds.</p>"
    body += (
        "<details><summary>Inspect exit assumptions, review receipt and limits</summary><pre>"
        + escape(
            json.dumps(
                {
                    "assumptions": spec,
                    "receipt": report["source_review"]["exit_checkpoint"],
                    "limits": result["limitations"],
                },
                indent=2,
            )
        )
        + "</pre></details>"
    )
    body += f"<p><a href='{escape(download, quote=True)}' download>Download the full lifecycle review</a> · <a href='source-review.html'>Operating evidence challenge</a> · <a href='historical-valuation.html'>Historical equity bridge</a> · <a href='decision-memo.html'>Executive memo</a></p></section>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Value Creation OS — constructed exit review</title><style>{CSS}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.primary-nav{{flex-wrap:wrap}}</style></head><body>"
        "<a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'>"
        "<a class='brand' href='../index.html'>Value Creation OS · Lifecycle</a><nav class='primary-nav' aria-label='Exit review sections'>"
        "<a class='nav-link' href='#matrix'>Sensitivity</a><a class='nav-link' href='#bridge'>EV bridge</a>"
        "<a class='nav-link' href='#operating'>Operating evidence</a><a class='nav-link' href='#history'>History</a></nav></div></header>"
        "<main id='main' tabindex='-1' class='app-shell'>" + body + "</main></body></html>"
    )


def build_exit_demo(
    underwriting: Path,
    operating_plan: Path,
    realization: Path,
    execution: Path,
    sources: Path,
    facts: Path,
    balances: Path,
    valuation: Path,
    assumptions: Path,
    output: Path,
    *,
    include_lineage: bool = False,
) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {
        p.resolve()
        for p in (
            underwriting,
            operating_plan,
            realization,
            execution,
            sources,
            facts,
            balances,
            valuation,
            assumptions,
        )
    } & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("exit review must not overwrite its inputs")
    case = UnderwritingCase.model_validate_json(underwriting.read_bytes())
    plan = OperatingPlan.model_validate_json(operating_plan.read_bytes())
    financial = RealizationExercise.model_validate_json(realization.read_bytes())
    exercise = ExecutionExercise.model_validate_json(execution.read_bytes())
    book = OperatingSourceBook.model_validate_json(sources.read_bytes())
    book.bind(case, plan)
    public = FactBundle.model_validate_json(facts.read_bytes())
    balance = BalanceBundle.model_validate_json(balances.read_bytes())
    value = ValuationSpec.model_validate_json(valuation.read_bytes())
    spec = ExitAssumptions.model_validate_json(assumptions.read_bytes())
    if exercise.realization_sha256 != fingerprint(financial):
        raise ValueError("execution must bind the exact realization exercise")
    replay, render = replay_exit, render_exit
    if include_lineage:
        from .lineage_demo import render_lineage, replay_lineage

        replay, render = replay_lineage, render_lineage
    report = demonstrate_realization(
        case,
        plan,
        financial,
        lambda repo, case, baseline: replay_execution(repo, case, baseline, exercise),
        lambda repo, case, baseline: replay(repo, case, baseline, book, exercise, public, balance, value, spec),
    )
    html = render(report, json_path.name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
