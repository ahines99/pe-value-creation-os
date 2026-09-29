"""A separate constructed allocation decision, preserving the published lineage exercise."""

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
from .cases import InvestmentCase, ReviewRequest, RevisionDraft
from .close_baseline import CloseBaseline
from .interactions import InteractionCase
from .operating_sources import AllocatedSourceBook, OperatingSourceBook, operating_records, source_forecast
from .operating_sources_render import render_sources
from .realization_render import RealizationExercise, demonstrate_realization
from .scheduling import OperatingPlan, evaluate_plan, fingerprint
from .source_revisions import SourceCasePayload
from .underwriting_render import amount, render_allocation


def validate_demo_selection(case: InteractionCase) -> tuple[str, str]:
    """This authored narrative is intentionally narrower than the general engine."""
    partitions = [p for p in case.interaction_policy.pools if p.mode == "partition"]
    if len(partitions) != 1 or len(partitions[0].initiative_ids) != 2:
        raise ValueError("allocation walkthrough requires its authored two-member pricing partition")
    rule = partitions[0]
    primary, alternative = rule.initiative_ids
    shares = {s.initiative_id: s.share for s in rule.shares}
    selected = set(case.interaction_policy.selected_initiatives)
    if (
        shares != {primary: Decimal(".6"), alternative: Decimal(".4")}
        or primary not in selected
        or alternative in selected
        or any(d.kind != "pricing" for d in case.scenarios[0].drivers if d.benefit_pool == rule.pool_id)
        or any(len(p.initiative_ids) != 1 for p in case.interaction_policy.pools if p != rule)
    ):
        raise ValueError("allocation walkthrough requires the authored 60% selected / 40% deferred pricing scope")
    return primary, alternative


def bind_sources(records: OperatingSourceBook, case: InteractionCase, plan: OperatingPlan) -> AllocatedSourceBook:
    """Author one exact record-to-pool assignment for this three-mechanism exercise."""
    by_kind: dict[str, set[str]] = {}
    for driver in case.scenarios[0].drivers:
        by_kind.setdefault(driver.kind, set()).add(driver.benefit_pool)
    if set(by_kind) != {"pricing", "service", "collections"} or any(len(pools) != 1 for pools in by_kind.values()):
        raise ValueError("allocation demonstration requires one declared pool per source mechanism")
    kinds = {"renewal": "pricing", "service_month": "service", "invoice": "collections"}
    raw = records.model_dump(mode="json")
    raw.update(case_id=case.case_id, underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    records = OperatingSourceBook.model_validate(raw)
    return AllocatedSourceBook.model_validate(
        {
            "schema_version": 3,
            "records": records.model_dump(mode="json"),
            "pool_ids": [p.pool_id for p in case.interaction_policy.pools],
            "assignments": [
                {
                    "kind": kind,
                    "record_id": key,
                    "record_sha256": fingerprint(row),
                    "pool_id": next(iter(by_kind[kinds[kind]])),
                }
                for (kind, key), row in operating_records(records).items()
            ],
            "allocation_rationale": "Authored complete records assigned once to their economic pool. Within-pool shares are scenario assumptions, not observed customer segmentation.",
        }
    )


def replay_allocation(
    repo: Repository, case: InvestmentCase, baseline: CloseBaseline, initial_book: AllocatedSourceBook
) -> dict[str, Any]:
    assert case.current_revision_id is not None
    parent = repo.get_case_revision(case.current_revision_id)
    before = repo.case_realization(case.case_id, baseline.baseline_id)
    checkpoints = []
    records = initial_book.records
    for step in ("source_challenge", "exclusive_choice", "vendor_correction"):
        raw = parent.draft.payload.underwriting.model_dump(mode="json")
        if step == "exclusive_choice":
            rule = next(p for p in raw["interaction_policy"]["pools"] if p["mode"] == "partition")
            primary, alternative = rule["initiative_ids"]
            rule.update(
                mode="exclusive",
                shares=[],
                rationale="Authored redesign: two competing pricing policies on the same full cohort; implement at most one.",
            )
            raw["interaction_policy"]["selected_initiatives"].remove(primary)
            if alternative not in raw["interaction_policy"]["selected_initiatives"]:
                raw["interaction_policy"]["selected_initiatives"].append(alternative)
            raw["interaction_policy"]["selection_rationale"] = (
                f"Research scenario selects {alternative} across the eligible cohort instead of two population partitions. This changes proposed scope; it does not move earlier claims or authorize customer actions."
            )
        current = InteractionCase.model_validate(raw)
        assert parent.draft.payload.operating_plan is not None
        plan_raw = parent.draft.payload.operating_plan.model_dump(mode="json")
        plan_raw["underwriting_sha256"] = fingerprint(current)
        plan = OperatingPlan.model_validate(plan_raw)
        if step == "vendor_correction":
            record_raw = records.model_dump(mode="json")
            for month in record_raw["service_months"]:
                month.update(release_on=None, release_evidence=None)
            records = OperatingSourceBook.model_validate(record_raw)
        book = bind_sources(records, current, plan)
        mechanism = "service" if step == "vendor_correction" else "pricing"
        driver = next(
            d
            for d in current.scenarios[0].drivers
            if d.kind == mechanism and d.initiative_id in current.interaction_policy.selected_initiatives
        )
        kind = "service_month" if mechanism == "service" else "renewal"
        refs = [
            {"kind": k, "record_id": key, "record_sha256": fingerprint(row)}
            for (k, key), row in operating_records(book.records).items()
            if k == kind
        ]
        payload = SourceCasePayload.model_validate(
            {
                "schema_version": 2,
                "underwriting": current.model_dump(mode="json"),
                "operating_plan": plan.model_dump(mode="json"),
                "operating_sources": book.model_dump(mode="json"),
                "challenged_revision_id": parent.revision_id,
                "challenged_revision_sha256": parent.content_sha256,
                "decision_question": "Does the explicitly allocated first wave survive contract, capacity and vendor-evidence constraints?",
                "counterevidence": [
                    "All record assignments and population shares are authored; no company intervention is represented."
                ],
                "unresolved_items": [
                    "Sponsor, source reconciliation, independent finance/commercial review and real outcome evidence remain absent."
                ],
                "lessons": [
                    {
                        "lesson_id": step,
                        "initiative_id": driver.initiative_id,
                        "scenario_id": "base",
                        "assumption_ids": [
                            getattr(
                                driver, "monthly_cost_action" if mechanism == "service" else "monthly_eligible_revenue"
                            )
                        ],
                        "source_records": refs,
                        "finding": step.replace("_", " "),
                        "response": "Recompute selected scope using each record once; retain commitments and earlier claims.",
                        "follow_up_evidence": "Authorized operating evidence and an independent challenge of this constructed interpretation.",
                    }
                ],
            }
        )
        reason = {
            "source_challenge": "Apply source rights, bounded terms and vendor commitments to each allocated population.",
            "exclusive_choice": "Replace the authored pricing partition with one mutually exclusive alternative; do not reassign historical claims.",
            "vendor_correction": "Remove unsupported vendor release evidence and retain the adverse forecast for review.",
        }[step]
        saved = repo.append_case_revision(
            case.case_id,
            parent.revision_id,
            RevisionDraft(
                stage="ownership_review",
                effective_on=parent.draft.effective_on + timedelta(days=1),
                reason=reason,
                payload=payload,
            ),
        )
        repo.review_case_revision(
            saved.revision_id,
            ReviewRequest(
                expected_revision_sha256=saved.content_sha256,
                mode="simulation",
                decision="accept" if step == "vendor_correction" else "request_changes",
                rationale="Simulated review of a research model only; no intervention or financial claim authorized.",
            ),
        )
        checkpoints.append({"step": step, "revision_id": saved.revision_id, "revision_sha256": saved.content_sha256})
        parent = saved
    after = repo.case_realization(case.case_id, baseline.baseline_id)
    continuity = {key: before[key] == after[key] for key in ("baseline", "observations", "attributions")}
    if not all(continuity.values()):
        raise ValueError("allocation replay must preserve frozen accounting and claim history")
    return {
        "classification": "constructed_source_review_exercise",
        "case_snapshot": repo.get_investment_case(case.case_id).model_dump(mode="json"),
        "checkpoints": checkpoints,
        "reviews": [r.model_dump(mode="json") for r in repo.list_case_reviews(case.case_id)],
        "continuity": continuity,
    }


def render_allocation_demo(report: dict[str, Any], download: str) -> str:
    latest = json.loads(report["revisions"][-1]["financial_result_json"])
    base = next(s for s in latest["scenarios"] if s["scenario_id"] == "base")
    decision = (
        "Rework the proposed first wave."
        if Decimal(base["year_one"]["incremental_ebitda"]) <= 0
        else "Challenge the evidence before selecting the proposed first wave."
    )
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed operating decision / Allocation review</p>"
        f"<h1>One pool. An explicit choice.</h1><p class='page-subtitle'>{escape(report['currency'])} · Population shares, competing initiatives and retained commitments</p>"
        "<p>Two pricing approaches have authored 60% and 40% shares. The 40% alternative is initially deferred because both do not fit the original capacity budgets. A later research revision chooses one competing policy for the full eligible cohort.</p>"
        f"</div><aside class='hero-aside'><span class='metric-label'>Current research decision</span><p>{decision} "
        "No company operation or independent review is represented.</p></aside></section><div class='metrics-grid'>"
    )
    for label, value, note in (
        (
            "Current year-one EBITDA",
            amount(base["year_one"]["incremental_ebitda"]),
            "After source constraints and vendor correction",
        ),
        (
            "Current year-one cash",
            amount(base["year_one"]["pre_tax_cash_proxy"]),
            "Pre-tax proxy; temporary acceleration reverses",
        ),
        ("Frozen accounting history", "Preserved", "Earlier records and claims do not move with the choice"),
        ("Realized company value", "Unavailable", "Every operating record here is constructed"),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{escape(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div><section class='panel'><h2>Capacity forces a bounded first wave</h2>"
    body += (
        "<p>Trying both pricing packages blocks: "
        + escape(", ".join(report["initial_capacity_challenge"]["blocked_tasks"]))
        + ". The modeled close therefore defers the alternative and leaves its 40% share unused. Resource budgets are unchanged.</p></section>"
    )
    body += "<section class='panel' id='history'><h2>Trace the decision</h2>"
    rows = []
    for revision in report["revisions"]:
        financial = json.loads(revision["financial_result_json"])
        scenario = next(s for s in financial["scenarios"] if s["scenario_id"] == "base")
        rows.append(
            [
                str(revision["sequence"]),
                escape(revision["draft"]["reason"]),
                escape(", ".join(financial["selected_initiatives"])),
                amount(scenario["year_one"]["incremental_ebitda"]),
                amount(scenario["year_one"]["pre_tax_cash_proxy"]),
            ]
        )
    body += (
        table(
            ["Revision", "Reason", "Selected work", "Year-one EBITDA", "Year-one cash"],
            rows,
            "Original forecasts are immutable. Effective dates are authored exercise dates, not actual ownership events.",
        )
        + "</section>"
    )
    body += render_allocation(latest)
    body += "<section class='panel' id='evidence'><h2>Review the decision and its limits</h2><p>Population shares do not allocate historical financial claims. A blocked or excluded share is not reassigned automatically. Shared commitments are posted once, with a separate explanation of ownership.</p>"
    body += table(
        ["Continuity check", "Result"],
        [[escape(k), "Preserved" if v else "Failed"] for k, v in report["source_review"]["continuity"].items()],
        "Compared before and after the saved source and selection revisions.",
    )
    body += (
        f"<p><a href='{escape(download, quote=True)}'>Complete case history and accounting comparison</a> · "
        "<a href='allocation-sources.html'>Current source constraints</a> · <a href='allocation-memo.html'>Executive memo</a></p>"
        "<p><a href='allocation-underwriting.html'>Original allocation assumptions</a> · <a href='allocation-operating-plan.html'>Original capacity plan</a> · "
        "<a href='lineage-review.html'>Separate initiative split/merge exercise</a></p>"
        "<p>This is a separate authored decision exercise. Its simulated reviews do not establish a company sponsor, independent finance validation, operating approval or real pilot outcomes.</p></section>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Benefit allocation review</title><style>{CSS}</style></head><body><a class='skip-link' href='#main'>Skip to content</a>"
        "<header class='topbar'><div class='topbar-inner'><a class='brand' href='../index.html'>Value Creation OS</a><nav class='primary-nav' aria-label='Sections'><a class='nav-link' href='#history'>Decision history</a><a class='nav-link' href='#allocation'>Allocation</a><a class='nav-link' href='#evidence'>Evidence</a></nav></div></header>"
        f"<main class='app-shell' id='main' tabindex='-1'>{body}</main></body></html>"
    )


def build_allocation_demo(
    underwriting: Path, plan_path: Path, exercise_path: Path, sources: Path, output: Path
) -> Path:
    case = InteractionCase.model_validate_json(underwriting.read_bytes())
    plan = OperatingPlan.model_validate_json(plan_path.read_bytes())
    exercise = RealizationExercise.model_validate_json(exercise_path.read_bytes())
    book = AllocatedSourceBook.model_validate_json(sources.read_bytes())
    book.bind(case, plan)
    _, alternative = validate_demo_selection(case)
    challenge = evaluate_plan(plan, case, selected=frozenset(d.initiative_id for d in case.scenarios[0].drivers))
    if not any(t["initiative_id"] == alternative and t["status"] == "blocked" for t in challenge["tasks"]):
        raise ValueError(
            "allocation walkthrough requires a demonstrated capacity constraint on the deferred alternative"
        )
    paths = (
        output.with_suffix(".html"),
        output.with_suffix(".json"),
        output.parent / "allocation-sources.html",
        output.parent / "allocation-sources.json",
    )
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("allocation review and companion source outputs must be distinct")
    if {p.resolve() for p in (underwriting, plan_path, exercise_path, sources)} & {p.resolve() for p in paths}:
        raise ValueError("allocation demo must not overwrite an input")
    report = demonstrate_realization(
        case, plan, exercise, revision_replay=lambda r, c, b: replay_allocation(r, c, b, book)
    )
    report["initial_capacity_challenge"] = {
        "blocked_tasks": [t["task_id"] for t in challenge["tasks"] if t["status"] == "blocked"],
        "report_sha256": challenge["report_sha256"],
        "authority": "Hypothetical simultaneous selection; a blocked proposal cannot become the frozen close baseline.",
    }
    latest = SourceCasePayload.model_validate(report["revisions"][-1]["draft"]["payload"])
    source = source_forecast(latest.operating_sources, latest.underwriting, latest.operating_plan)
    html = render_allocation_demo(report, paths[1].name)
    source_html = render_sources(source, paths[3].name)
    output.parent.mkdir(parents=True, exist_ok=True)
    for path, value in zip(
        paths,
        (
            html,
            json.dumps(report, indent=2, default=str) + "\n",
            source_html,
            json.dumps(source, indent=2, default=str) + "\n",
        ),
        strict=True,
    ):
        path.write_text(value, encoding="utf-8")
    return paths[0]
