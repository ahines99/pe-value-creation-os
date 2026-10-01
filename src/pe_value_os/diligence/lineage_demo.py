"""Rehearse initiative changes without creating retrospective financial claims."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from html import escape
from typing import Any

from ..adapters.repositories import Repository
from ..research.render import table
from .balances import BalanceBundle
from .cases import CaseRevision, InvestmentCase, ReviewRequest, RevisionDraft
from .close_baseline import CloseBaseline
from .execution_demo import ExecutionExercise
from .exhibit_style import exhibit_page
from .exit_demo import exit_draft
from .exit_review import ExitAssumptions, ExitReviewPayload
from .lineage import LineageCasePayload
from .lineage_example import merge_lineage, partition_book, revise_kpi_target, seed_lineage, source_basis, split_lineage
from .models import FactBundle
from .operating_sources import OperatingSourceBook
from .source_review_demo import replay_source_review
from .valuation import ValuationSpec


def lineage_exit_draft(
    parent: CaseRevision,
    facts: FactBundle,
    balances: BalanceBundle,
    valuation: ValuationSpec,
    assumptions: ExitAssumptions,
) -> RevisionDraft:
    prior = parent.draft.payload
    if not isinstance(prior, LineageCasePayload):
        raise ValueError("lineage exit requires retained initiative and KPI history")
    draft = exit_draft(parent, facts, balances, valuation, assumptions)
    assert isinstance(draft.payload, ExitReviewPayload)
    raw = draft.payload.model_dump(mode="json")
    raw["source_basis"] = source_basis(
        parent, prior.underwriting, prior.operating_plan, partition_book(prior.source_basis)
    ).model_dump(mode="json")
    raw["source_basis"]["decision_question"] = draft.payload.source_basis.decision_question
    raw["source_basis"]["unresolved_items"] = list(draft.payload.source_basis.unresolved_items)
    return RevisionDraft(
        stage=draft.stage,
        effective_on=draft.effective_on,
        reason=draft.reason,
        payload=LineageCasePayload(
            schema_version=4,
            basis=ExitReviewPayload.model_validate(raw),
            lineage_events=prior.lineage_events,
            kpis=prior.kpis,
        ),
    )


def replay_lineage(
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
    before = repo.case_realization(case.case_id, baseline.baseline_id)
    checkpoints = []
    for builder in (
        seed_lineage,
        split_lineage,
        revise_kpi_target,
        merge_lineage,
        lambda parent: lineage_exit_draft(parent, facts, balances, valuation, assumptions),
    ):
        current = repo.get_investment_case(case.case_id)
        assert current.current_revision_id is not None
        parent = repo.get_case_revision(current.current_revision_id)
        revision = repo.append_case_revision(case.case_id, parent.revision_id, builder(parent))
        receipt = repo.review_case_revision(
            revision.revision_id,
            ReviewRequest(
                expected_revision_sha256=revision.content_sha256,
                mode="simulation",
                decision="accept",
                rationale="Simulated review of explicit identity mapping, preserved costs and evidence boundaries. No company result, financial attribution, intervention or sale is approved.",
            ),
        )
        after = repo.case_realization(case.case_id, baseline.baseline_id)
        if any(before[k] != after[k] for k in ("baseline", "observations", "attributions")) or any(
            before["aggregate_recorded_periods"][k] != after["aggregate_recorded_periods"][k]
            for k in ("measured_difference", "attributed_difference", "unassigned_residual")
        ):
            raise ValueError("lineage must preserve the frozen baseline, accounting and financial claims")
        checkpoints.append(
            {
                "revision_id": revision.revision_id,
                "revision_sha256": revision.content_sha256,
                "review": receipt.model_dump(mode="json"),
                "preserved_accounting_and_claims": True,
            }
        )
    return {
        **source,
        "reviews": [r.model_dump(mode="json") for r in repo.list_case_reviews(case.case_id)],
        "lineage_checkpoints": checkpoints,
        "exit_checkpoint": checkpoints[-1],
    }


def render_lineage(report: dict[str, Any], download: str) -> str:
    revisions = report["revisions"]
    latest = json.loads(revisions[-1]["financial_result_json"])
    lineage = latest["lineage_review"]
    kpis = lineage["kpis"]

    def money(value: Any) -> str:
        return f"{Decimal(str(value)):,.2f}"

    def percent(value: Any) -> str:
        return "Withheld" if value is None else f"{Decimal(str(value)) * 100:,.2f}%"

    body = (
        "<section class='hero'><div><p class='eyebrow'>Operating review / Constructed lifecycle</p>"
        "<h1>Change the plan. Keep the history.</h1>"
        "<p class='page-subtitle'>Split a pricing initiative, challenge its target, then consolidate the work.</p>"
        "<p>Every contract keeps one owner. Costs stay in the ledger once. Prior KPI readings keep the target and population used when they were authored.</p></div>"
        "<aside class='hero-aside'><span class='metric-label'>Decision boundary</span><p>Accept the traceable rehearsal. Rework the adverse operating case before a pilot.</p>"
        "<p>Constructed records · simulated reviews · no company intervention or realized value</p></aside></section>"
    )
    latest_base = next(s for s in latest["scenarios"] if s["scenario_id"] == "base")
    body += "<div class='metrics-grid'>"
    for label, value, note in (
        ("Case revisions", str(len(revisions)), "One preserved accounting record"),
        ("KPI definitions", str(len(kpis["definitions"])), "All authored definitions remain inspectable"),
        ("KPI readings", str(len(kpis["observations"])), "Constructed readings; corrections are explicit"),
        (
            "Current year-one EBITDA",
            money(latest_base["year_one"]["incremental_ebitda"])
            + f" <span class='x-unit'>{escape(latest['currency'])}</span>",
            "Base scenario · latest revision",
        ),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{value}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div><section class='panel' id='history'><h2>Ten revisions; one preserved accounting record</h2>"
    rows = []
    for revision in revisions:
        result = json.loads(revision["financial_result_json"])
        base = next(s for s in result["scenarios"] if s["scenario_id"] == "base")
        rows.append(
            [
                str(revision["sequence"]),
                escape(revision["draft"]["effective_on"]),
                escape(revision["draft"]["reason"]),
                money(base["year_one"]["incremental_ebitda"]),
                money(base["year_one"]["pre_tax_cash_proxy"]),
            ]
        )
    body += table(
        ["Revision", "Exercise date", "Decision / change", "Year-one EBITDA", "Year-one cash"],
        rows,
        "USD · base scenario. Splitting work creates no management capacity: the same concurrency and resource limits still govern dates.",
    )
    body += "</section><section class='panel' id='lineage'><h2>Trace every predecessor and successor</h2>"
    events = revisions[-1]["draft"]["payload"]["lineage_events"]
    body += table(
        ["Effective date", "Predecessor", "Successor", "Reference share"],
        [
            [
                escape(event["effective_on"]),
                escape(edge["predecessor_id"]),
                escape(edge["successor_id"]),
                percent(edge["reference_allocation"]),
            ]
            for event in events
            for edge in event["edges"]
        ],
        "Reference shares conserve authored revenue or spend populations. They do not allocate historical accounting or attribution claims.",
    )
    for event in events:
        body += f"<p>{escape(event['rationale'])}</p><p class='muted'>{escape(event['allocation_basis'])}</p>"
    body += "<h3>One owner per operating record</h3>"
    sources = revisions[-1]["draft"]["payload"]["basis"]["source_basis"]["operating_sources"]
    body += table(
        ["Record type", "Record", "Current initiative"],
        [
            [escape(a["kind"].replace("_", " ")), escape(a["record_id"]), escape(a["initiative_id"])]
            for a in sources["assignments"]
        ],
        "Contracts, indivisible vendor months and invoices cannot be copied into two current benefit populations.",
    )
    body += "</section><section class='panel' id='kpis'><h2>Keep targets and observations in context</h2>"
    body += table(
        ["Definition", "Initiative", "Baseline", "Target", "Target date", "Replaces / descends from"],
        [
            [
                escape(d["definition_id"]),
                escape(d["initiative_id"]),
                percent(Decimal(d["baseline_numerator"]) / Decimal(d["baseline_denominator"])),
                percent(d["target"]),
                escape(d["target_on"]),
                escape(
                    d["supersedes_definition_id"] or ", ".join(d["predecessor_definition_ids"]) or "Initial definition"
                ),
            ]
            for d in kpis["definitions"]
        ],
        "All seven authored definitions remain inspectable. The spring target changes from 2.5% to 4%; earlier readings keep their earlier target.",
    )
    body += table(
        ["Reading", "Exact definition", "Month", "Numerator", "Denominator", "Ratio", "Corrects"],
        [
            [
                escape(o["observation_id"]),
                escape(o["definition_id"]),
                escape(o["start"][:7]),
                money(o["numerator"]),
                money(o["denominator"]),
                percent(Decimal(o["numerator"]) / Decimal(o["denominator"])),
                escape(o["supersedes_observation_id"] or "—"),
            ]
            for o in kpis["observations"]
        ],
        "Fifteen constructed readings include the original April spring reading and its explicit correction. No past parent reading becomes an invented child result.",
    )
    body += "<h3>Aggregate comparable populations using their denominators</h3>"
    body += table(
        ["Metric", "Month", "Status", "Weighted ratio"],
        [
            [
                escape(g["metric"].replace("_", " ")),
                escape(g["start"][:7]),
                escape(g["status"].replace("_", " ")),
                percent(g["value"]),
            ]
            for g in kpis["current_population_observations"]
        ],
        "Current definitions only. A missing child observation withholds the combined ratio. Prior definitions remain in history; target changes do not rebind earlier readings.",
    )
    body += "</section><section class='panel' id='comparison'><h2>Compare the full economic family</h2>"
    comparisons = next(s for s in lineage["scenarios"] if s["scenario_id"] == "base")["families"]
    body += table(
        [
            "Original family",
            "Current identities",
            "Prior year-one EBITDA",
            "Current year-one EBITDA",
            "Current year-one cash",
        ],
        [
            [
                escape(", ".join(f["original_ids"]) or "Cross-family shared costs"),
                escape(", ".join(f["current_ids"]) or "Shared"),
                money(f["prior"]["year_one"]["incremental_ebitda"]),
                money(f["current"]["year_one"]["incremental_ebitda"]),
                money(f["current"]["year_one"]["pre_tax_cash_proxy"]),
            ]
            for f in comparisons
        ],
        "Latest exit review versus its immediate predecessor, both over the same calendar. Each prior split/merge comparison remains in its revision's download.",
    )
    body += f"<p>{escape(lineage['cost_treatment'])}</p></section>"
    aggregate = report["aggregate_recorded_periods"]
    body += "<section class='panel' id='authority'><h2>Preserve the financial measurement perimeter</h2>"
    body += table(
        ["Recorded-period comparison", "EBITDA", "Cash"],
        [
            [label, money(aggregate[key]["incremental_ebitda"]), money(aggregate[key]["pre_tax_cash_proxy"])]
            for label, key in (
                ("Constructed difference", "measured_difference"),
                ("Authored claims", "attributed_difference"),
                ("Unassigned residual", "unassigned_residual"),
            )
        ],
        "USD · unchanged accounting and claims on frozen initiative IDs. These figures are not actual Progress results.",
    )
    body += "<p>The exit sensitivity remains separate from these operating populations. Actual transaction proceeds, shareholder distributions and maintainable annual operating uplift remain unavailable.</p>"
    body += (
        "<details><summary>Inspect frozen-to-current identity mappings and review receipts</summary><pre>"
        + escape(
            json.dumps(
                {
                    "comparability": report["initiative_comparability"],
                    "reviews": report["source_review"]["lineage_checkpoints"],
                },
                indent=2,
            )
        )
        + "</pre></details>"
    )
    body += f"<p><a href='{escape(download, quote=True)}' download>Download the complete ten-revision lifecycle</a> · <a href='decision-memo.html'>Executive decision memo</a> · <a href='exit-review.html'>Earlier exit sensitivity exhibit</a></p></section>"
    return exhibit_page(
        title="Initiative and KPI history — Value Creation OS",
        kind="Initiative lifecycle",
        provenance="Constructed exercise",
        nav=[
            ("#history", "Decisions"),
            ("#lineage", "Ownership"),
            ("#kpis", "KPI history"),
            ("#authority", "Accounting"),
        ],
        nav_label="Lineage review sections",
        body=body,
    )
