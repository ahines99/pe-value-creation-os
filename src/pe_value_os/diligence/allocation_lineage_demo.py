"""Compose saved allocation decisions, scoped KPI history and financial realization."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from typing import Any

from ..adapters.repositories import Repository
from ..research.render import table
from .allocation_demo import render_allocation_demo, replay_allocation
from .allocation_lineage_example import (
    measure_allocated_lineage,
    merge_allocated_lineage,
    partition_allocated_lineage,
    seed_allocated_lineage,
    split_allocated_lineage,
)
from .cases import InvestmentCase, ReviewRequest
from .close_baseline import CloseBaseline
from .operating_sources import AllocatedSourceBook


def replay_allocated_lineage(
    repo: Repository, case: InvestmentCase, baseline: CloseBaseline, initial_book: AllocatedSourceBook
) -> dict[str, Any]:
    result = replay_allocation(repo, case, baseline, initial_book)
    before = repo.case_realization(case.case_id, baseline.baseline_id)
    checkpoints = []
    for builder in (
        seed_allocated_lineage,
        partition_allocated_lineage,
        split_allocated_lineage,
        measure_allocated_lineage,
        lambda p: measure_allocated_lineage(p, complete=True),
        merge_allocated_lineage,
    ):
        current = repo.get_investment_case(case.case_id)
        assert current.current_revision_id is not None
        parent = repo.get_case_revision(current.current_revision_id)
        saved = repo.append_case_revision(case.case_id, parent.revision_id, builder(parent))
        receipt = repo.review_case_revision(
            saved.revision_id,
            ReviewRequest(
                expected_revision_sha256=saved.content_sha256,
                mode="simulation",
                decision="accept",
                rationale="Simulated research review of conserved pool scope, KPI history and adverse economics; no company action, independent validation or financial claim authorized.",
            ),
        )
        after = repo.case_realization(case.case_id, baseline.baseline_id)
        if any(before[k] != after[k] for k in ("baseline", "observations", "attributions")) or any(
            before["aggregate_recorded_periods"][k] != after["aggregate_recorded_periods"][k]
            for k in ("measured_difference", "attributed_difference", "unassigned_residual")
        ):
            raise ValueError("allocated lineage cannot move frozen accounting or financial claims")
        checkpoints.append(
            {
                "revision_id": saved.revision_id,
                "revision_sha256": saved.content_sha256,
                "review": receipt.model_dump(mode="json"),
                "preserved_accounting_and_claims": True,
            }
        )
    return {
        **result,
        "case_snapshot": repo.get_investment_case(case.case_id).model_dump(mode="json"),
        "reviews": [r.model_dump(mode="json") for r in repo.list_case_reviews(case.case_id)],
        "allocated_lineage_checkpoints": checkpoints,
    }


def render_allocated_lineage(report: dict[str, Any], download: str) -> str:
    latest = json.loads(report["revisions"][-1]["financial_result_json"])
    lineage, payload = latest["lineage_review"], report["revisions"][-1]["draft"]["payload"]
    extra = "<section class='panel' id='kpi-history'><h2>Change the plan. Preserve its measurement history.</h2><p>The full-pool choice is subsequently narrowed to a 60% selected / 40% deferred partition. The selected 60% splits into 24% and 36% scopes, then recombines. Complete records stay in one economic pool. These are authored population fractions, not observed customer cohorts.</p>"
    extra += table(
        ["Current KPI", "Pool", "Scope", "Target", "Current measurement"],
        [
            [
                escape(d["initiative_id"]),
                escape(d["allocation_scope"]["pool_id"]),
                f"{Decimal(d['allocation_scope']['population_share']) * 100:g}%",
                f"{Decimal(d['target']) * 100:g}%",
                "Unavailable; needs a new scoped reading"
                if d["definition_id"] in lineage["kpis"]["unmeasured_current_definition_ids"]
                else "Constructed reading retained",
            ]
            for d in lineage["kpis"]["definitions"]
            if d["definition_id"] in lineage["kpis"]["active_definition_ids"]
        ],
        "Only selected current populations appear. A target is an authored proposal, not an operating result.",
    )
    rows = []
    for revision in report["revisions"]:
        result = json.loads(revision["financial_result_json"])
        if "lineage_review" not in result:
            continue
        for group in result["lineage_review"]["kpis"]["current_population_observations"]:
            if group["metric"] == "net_price_uplift":
                rows.append(
                    [
                        str(revision["sequence"]),
                        escape(group["start"]),
                        escape(", ".join(group["definition_ids"])),
                        "Withheld: missing current population"
                        if group["value"] is None
                        else f"{Decimal(group['value']) * 100:.2f}%",
                    ]
                )
    extra += table(
        ["Revision", "Measurement period", "Exact definitions", "Scoped pricing result"],
        rows,
        "Ratios use the sum of authored numerators divided by the sum of denominators. Shares never multiply an observation a second time.",
    )
    extra += "<details><summary>Inspect identity and task ancestry</summary>"
    extra += table(
        ["Predecessor", "Successor", "Share of predecessor"],
        [
            [
                escape(edge["predecessor_id"]),
                escape(edge["successor_id"]),
                f"{Decimal(edge['reference_allocation']) * 100:g}%",
            ]
            for event in payload["lineage_events"]
            for edge in event["edges"]
        ],
        "Lineage preserves selection, source assignments, unit economics, commitments and cost explanations. Task effort is explicitly apportioned; resource budgets are unchanged.",
    )
    extra += "</details><p>Monthly pool amounts follow the existing cent-rounding convention. Splits can change partial-period rounding and scheduled gate dates; financial comparisons retain those differences rather than claiming every daily amount is identical. Historical accounting and attribution remain on their frozen identities.</p></section>"
    html = render_allocation_demo(report, download)
    html = html.replace("One pool. An explicit choice.", "One pool. A traceable operating history.")
    html = html.replace("<section class='panel' id='evidence'>", extra + "<section class='panel' id='evidence'>")
    html = html.replace("allocation-sources.html", "allocation-lineage-sources.html").replace(
        "allocation-memo.html", "allocation-lineage-memo.html"
    )
    return html.replace("<title>Benefit allocation review</title>", "<title>Allocation and KPI lifecycle</title>")
