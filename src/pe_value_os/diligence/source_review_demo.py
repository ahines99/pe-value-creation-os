"""Persist a constructed source challenge, review and correction in the existing case ledger."""

from __future__ import annotations

import json
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any

from ..adapters.repositories import Repository
from .cases import CaseRevision, InvestmentCase, ReviewRequest, RevisionDraft
from .close_baseline import CloseBaseline
from .execution_demo import ExecutionExercise, replay_execution
from .exhibit_style import exhibit_page
from .operating_sources import OperatingSourceBook
from .operating_sources_render import money, table
from .realization_render import RealizationExercise, demonstrate_realization
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import OperatingRecordRef, SourceCasePayload, SourceLesson, source_rows
from .underwriting import UnderwritingCase


def source_draft(
    parent: CaseRevision, book: OperatingSourceBook, effective_on: date, *, correction: bool = False
) -> RevisionDraft:
    """Author a disclosed exercise challenge; retain the latest forecast assumptions."""
    prior = parent.draft.payload
    if prior.operating_plan is None:
        raise ValueError("source exercise requires a capacity-tested parent")
    if correction:
        if not isinstance(prior, SourceCasePayload):
            raise ValueError("source correction requires a prior source-backed revision")
        if not isinstance(prior.operating_sources, OperatingSourceBook):
            raise ValueError("the legacy source-correction demo requires an unpartitioned source book")
        book = prior.operating_sources
    bound = OperatingSourceBook.model_validate(
        {
            **book.model_dump(mode="json"),
            "underwriting_sha256": fingerprint(prior.underwriting),
            "plan_sha256": fingerprint(prior.operating_plan),
        }
    )
    if correction:
        raw = bound.model_dump(mode="json")
        for month in raw["service_months"]:
            month.update(release_on=None, release_evidence=None)
        bound = OperatingSourceBook.model_validate(raw)
    rows = source_rows(bound)

    def refs(kind: str) -> tuple[OperatingRecordRef, ...]:
        return tuple(
            OperatingRecordRef(kind=k, record_id=i, record_sha256=fingerprint(row))
            for (k, i), row in rows.items()
            if k == kind
        )

    lessons = [
        SourceLesson(
            lesson_id="vendor-release-correction" if correction else "vendor-constraints",
            initiative_id="service-automation",
            scenario_id="base",
            assumption_ids=("cost-action", "addressable-spend"),
            source_records=refs("service_month"),
            finding="Vendor release evidence has been removed from the authored source schedule."
            if correction
            else "Quality exclusions, QA effort, vendor minimums and release timing constrain savings.",
            response="Retain capacity calculations and all original costs; remove vendor expense savings."
            if correction
            else "Use the explicit monthly vendor and evaluation constraints in the shared ledger.",
            follow_up_evidence="An authorized vendor amendment and finance reconciliation are required for a real pilot.",
        )
    ]
    if not correction:
        lessons.extend(
            [
                SourceLesson(
                    lesson_id="contract-eligibility",
                    initiative_id="pricing-renewals",
                    scenario_id="base",
                    assumption_ids=("eligible-revenue", "uplift", "capture"),
                    source_records=refs("renewal"),
                    finding="Notice deadlines, prohibited or unknown rights, caps and bounded terms constrain the cohort.",
                    response="Apply row-level rights and dates while preserving the latest capture assumption.",
                    follow_up_evidence="Contract-owner review and reconciled renewal outcomes remain absent.",
                ),
                SourceLesson(
                    lesson_id="collectible-timing",
                    initiative_id="collections-timing",
                    scenario_id="base",
                    assumption_ids=("receivables", "accelerated"),
                    source_records=refs("invoice"),
                    finding="Credits, payments, disputes and missed acceleration windows reduce eligible balances.",
                    response="Model only eligible timing cash and retain its counterfactual reversal; no EBITDA benefit.",
                    follow_up_evidence="Tie a permissioned invoice export to the subledger and actual receipts.",
                ),
            ]
        )
    return RevisionDraft(
        stage="ownership_review",
        effective_on=effective_on,
        reason="Correct unsupported vendor release evidence; retain the adverse model for review."
        if correction
        else "Challenge the current forecast using authored contract, service and invoice records.",
        payload=SourceCasePayload(
            schema_version=2,
            underwriting=prior.underwriting,
            operating_plan=prior.operating_plan,
            decision_question="Does the evidence still justify the proposed first wave?",
            counterevidence=("All source records and lessons are constructed; no independent company validation.",),
            unresolved_items=(
                "Sponsor, authorized private records, independent challenge and historical information cutoffs remain absent.",
            ),
            operating_sources=bound,
            challenged_revision_id=parent.revision_id,
            challenged_revision_sha256=parent.content_sha256,
            lessons=tuple(lessons),
        ),
    )


def replay_source_review(
    repo: Repository,
    case: InvestmentCase,
    baseline: CloseBaseline,
    book: OperatingSourceBook,
    effective_on: date,
) -> dict[str, Any]:
    assert case.current_revision_id is not None
    parent = repo.get_case_revision(case.current_revision_id)
    before = repo.case_realization(case.case_id, baseline.baseline_id)
    checkpoints = []
    for correction, decision in ((False, "request_changes"), (True, "accept")):
        draft = source_draft(parent, book, effective_on, correction=correction)
        revision = repo.append_case_revision(case.case_id, parent.revision_id, draft)
        review = repo.review_case_revision(
            revision.revision_id,
            ReviewRequest(
                expected_revision_sha256=revision.content_sha256,
                mode="simulation",
                decision=decision,
                rationale="Simulated acceptance of a corrected adverse research model; no operating action authorized."
                if correction
                else "Simulated challenge: require removal of unsupported vendor release evidence.",
            ),
        )
        checkpoints.append(
            {
                "revision_id": revision.revision_id,
                "revision_sha256": revision.content_sha256,
                "review": review.model_dump(mode="json"),
                "aggregate_recorded_periods": repo.case_realization(case.case_id, baseline.baseline_id)[
                    "aggregate_recorded_periods"
                ],
            }
        )
        parent = revision
        effective_on += timedelta(days=1)
    return {
        "classification": "constructed_source_review_exercise",
        "supplied_source_book_sha256": fingerprint(book),
        "rebinding": "Source rows are retained for the first challenge; only case/plan bindings change to preserve the latest capture assumption. The next revision explicitly removes vendor release evidence.",
        "forecast_basis": "Retrospective whole-horizon re-estimate, not actuals plus remaining forecast or a point-in-time backtest. Exercise effective dates are authored; recorded_at is the actual persistence timestamp.",
        "baseline_id": baseline.baseline_id,
        "baseline_sha256": baseline.content_sha256,
        "before_aggregate_recorded_periods": before["aggregate_recorded_periods"],
        "checkpoints": checkpoints,
        "reviews": [r.model_dump(mode="json") for r in repo.list_case_reviews(case.case_id)],
        "human_review_count": 0,
        "actual_company_realized_value": None,
    }


def render_source_review(report: dict[str, Any], download: str) -> str:
    revisions = report["revisions"]
    review = report["source_review"]
    current = json.loads(revisions[-1]["financial_result_json"])
    base = next(s for s in current["scenarios"] if s["scenario_id"] == "base")
    close_base = next(
        s for s in json.loads(revisions[1]["financial_result_json"])["scenarios"] if s["scenario_id"] == "base"
    )
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed operating exercise / Investment committee rehearsal</p>"
        "<h1>Change the forecast. Preserve the record.</h1>"
        "<p class='page-subtitle'>An evidence challenge, a requested correction and an accepted adverse model.</p>"
        "<p>Fictional contracts, vendor schedules and invoices test the original investment logic. Every revision keeps its inputs, calculation and exact-version review receipt.</p>"
        "</div><aside class='hero-aside'><span class='metric-label'>Research decision</span>"
        "<p>Rework the first wave. Accepting this model means acknowledging its adverse economics; it does not authorize spending or certify value delivery.</p>"
        "<p>Simulation only · 0 human reviews · no company pilot</p></aside></section><div class='metrics-grid'>"
    )
    for label, value, note in (
        ("Current year-one EBITDA", base["year_one"]["incremental_ebitda"], "Base · source correction included"),
        ("Current year-one cash", base["year_one"]["pre_tax_cash_proxy"], "Pre-tax proxy · original costs retained"),
        (
            "Frozen close EBITDA",
            close_base["year_one"]["incremental_ebitda"],
            "Year one · comparison anchor unchanged",
        ),
        ("Current peak funding", base["maximum_dated_funding_need"], "Base · dated cash deficit"),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{money(value)} <span class='x-unit'>{escape(report['currency'])}</span></strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div><section class='panel' id='revisions'><h2>One case, five immutable revisions</h2>"
    receipts = {r["revision_id"]: r for r in review["reviews"]}
    rows = []
    for revision in revisions:
        financial = json.loads(revision["financial_result_json"])
        scenario = next(s for s in financial["scenarios"] if s["scenario_id"] == "base")
        receipt = receipts.get(revision["revision_id"])
        rows.append(
            [
                f"{revision['sequence']} · {escape(revision['draft']['stage'].replace('_', ' '))}",
                escape(revision["draft"]["reason"]),
                money(scenario["year_one"]["incremental_ebitda"]),
                money(scenario["year_one"]["pre_tax_cash_proxy"]),
                "Simulated " + escape(receipt["decision"].replace("_", " ")) if receipt else "No receipt",
            ]
        )
    body += table(
        ["Revision", "Why it changed", "Year-one EBITDA", "Year-one cash", "Research review"],
        rows,
        "USD · base scenarios over the same model calendar. The frozen close is revision 2. Reviews bind exact revision hashes.",
    )
    body += f"<p>{escape(review['forecast_basis'])}</p><p>{escape(review['rebinding'])}</p></section>"
    body += "<section class='panel' id='learning'><h2>What changed, and what evidence would resolve it?</h2>"
    for revision in revisions:
        financial = json.loads(revision["financial_result_json"])
        for lesson in financial.get("learning_context", []):
            assumptions = ", ".join(
                f"{a['assumption_id']} = {a['value']} {a['unit']}" for a in lesson["prior_assumptions"]
            )
            body += f"<article><h3>Revision {revision['sequence']} · {escape(lesson['initiative_id'])}</h3><p><strong>{escape(lesson['finding'])}</strong></p><p>{escape(lesson['response'])}</p><p class='muted'>Prior assumptions: {escape(assumptions)}</p><p><strong>Next evidence:</strong> {escape(lesson['follow_up_evidence'])}</p>"
            body += f"<details><summary>Inspect {len(lesson['source_comparison'])} bound records and prior assumptions</summary><div class='detail-body'><p>{escape(lesson['authority'])}</p><pre>{escape(json.dumps(lesson, default=str, indent=2))}</pre></div></details></article>"
    body += (
        "</section><section class='panel' id='preserved'><h2>Reforecasting does not rewrite accounting or claims</h2>"
    )
    aggregate = report["aggregate_recorded_periods"]
    body += table(
        ["Five recorded months", "EBITDA difference", "Pre-tax cash difference"],
        [
            [label, money(aggregate[key]["incremental_ebitda"]), money(aggregate[key]["pre_tax_cash_proxy"])]
            for label, key in (
                ("Constructed accounting comparison", "measured_difference"),
                ("Explicit authored claims", "attributed_difference"),
                ("Unassigned residual", "unassigned_residual"),
            )
        ],
        "These are constructed accounting differences and claims, not actual company savings or causal estimates. The source correction changes none of these figures.",
    )
    body += "<p>The vendor delivery acceptance remains withdrawn. Removing release evidence from the forecast is an explicit authored correction, not an automatic causal inference from that withdrawal. Original receipts remain inspectable.</p>"
    body += f"<p><a href='{escape(download, quote=True)}' download>Download the complete case, source lessons, reviews and accounting comparison</a></p><p><a href='execution.html'>Delivery and claim support</a> · <a href='operating-sources.html'>Original source challenge</a> · <a href='https://github.com/ahines99/pe-value-creation-os/blob/main/docs/pilot/permissioned/README.md'>Pilot sponsor package</a></p></section>"
    return exhibit_page(
        title="Source-backed case review — Value Creation OS",
        kind="Case review",
        provenance="Constructed exercise",
        nav=[("#revisions", "Revisions"), ("#learning", "Learning"), ("#preserved", "Accounting")],
        body=body,
    )


def build_source_review_demo(
    underwriting: Path, operating_plan: Path, realization: Path, execution: Path, sources: Path, output: Path
) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in (underwriting, operating_plan, realization, execution, sources)} & {
        html_path.resolve(),
        json_path.resolve(),
    }:
        raise ValueError("source review must not overwrite its inputs")
    case = UnderwritingCase.model_validate_json(underwriting.read_bytes())
    plan = OperatingPlan.model_validate_json(operating_plan.read_bytes())
    financial = RealizationExercise.model_validate_json(realization.read_bytes())
    exercise = ExecutionExercise.model_validate_json(execution.read_bytes())
    book = OperatingSourceBook.model_validate_json(sources.read_bytes())
    book.bind(case, plan)
    if exercise.realization_sha256 != fingerprint(financial):
        raise ValueError("execution rehearsal must bind the exact realization exercise")
    report = demonstrate_realization(
        case,
        plan,
        financial,
        lambda repo, case, baseline: replay_execution(repo, case, baseline, exercise),
        lambda repo, case, baseline: replay_source_review(
            repo, case, baseline, book, exercise.exercise_as_of + timedelta(days=1)
        ),
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_source_review(report, json_path.name), encoding="utf-8")
    return html_path
