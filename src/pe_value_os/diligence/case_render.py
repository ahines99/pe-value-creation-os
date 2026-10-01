"""Public constructed revision walkthrough using the same repository operations."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .. import security
from ..adapters.evidence_store import FileSystemEvidenceStore
from ..adapters.repositories import InMemoryRepository
from ..domain.source_models import CompanyProfile
from ..research.render import table
from .cases import CasePayload, ReviewRequest, RevisionDraft, compare_revisions
from .close_baseline import CloseBaselineRequest, close_baseline_view
from .exhibit_style import exhibit_page
from .scheduling import OperatingPlan
from .underwriting import UnderwritingCase
from .underwriting_render import amount


def demonstrate_revisions(case: UnderwritingCase, plan: OperatingPlan) -> dict[str, Any]:
    plan.bind(case)
    company_id = "progress-constructed-exercise"
    with TemporaryDirectory(prefix="pvc-case-demo-") as temporary:
        repo = InMemoryRepository(FileSystemEvidenceStore(temporary))
        with security.principal_scope(security.system_principal(company_id, subject="service:constructed-case-demo")):
            repo.upsert_company(
                CompanyProfile(
                    company_id=company_id,
                    name="Constructed operating exercise — not Progress company records",
                    business_model="Constructed method demonstration",
                    vertical="Software reference case",
                    currency=case.currency,
                    fiscal_year_start_month=10,
                )
            )
            registered = repo.create_investment_case(
                company_id, case.case_id, "Original underwriting to capacity revision", case.currency
            )
            payload = CasePayload(
                underwriting=case,
                decision_question="Does the proposed first wave still work when finite change capacity is enforced?",
                counterevidence=(
                    "Original benefit dates do not demonstrate available capacity or accepted work.",
                    "No actual Progress contracts, staffing assignments, service records or collectible cohort are available.",
                ),
                unresolved_items=(
                    "Company sponsor, confirmed capacity and actual human review absent.",
                    "Commercial thesis, maintainability review and financial actuals remain incomplete.",
                ),
            )
            first = repo.append_case_revision(
                registered.case_id,
                None,
                RevisionDraft(
                    stage="underwriting",
                    effective_on=case.start,
                    reason="Freeze the original constructed underwriting before resource challenge.",
                    payload=payload,
                ),
            )
            repo.review_case_revision(
                first.revision_id,
                ReviewRequest(
                    expected_revision_sha256=first.content_sha256,
                    mode="simulation",
                    decision="request_changes",
                    rationale="Constructed challenge: assumed start dates need prerequisite and shared-resource checks.",
                ),
            )
            updated_payload = CasePayload.model_validate(
                {**payload.model_dump(mode="json"), "operating_plan": plan.model_dump(mode="json")}
            )
            second = repo.append_case_revision(
                registered.case_id,
                first.revision_id,
                RevisionDraft(
                    stage="close_validation",
                    effective_on=case.start,
                    reason="Hypothetical close review adds explicit resource feasibility before freezing the comparison baseline; retain original assumptions, commitments and calendar.",
                    payload=updated_payload,
                ),
            )
            accepted = repo.review_case_revision(
                second.revision_id,
                ReviewRequest(
                    expected_revision_sha256=second.content_sha256,
                    mode="simulation",
                    decision="accept",
                    rationale="Constructed method review accepts the recalculated schedule for demonstration only. Actual assignments, acceptance and outcomes are still unavailable.",
                ),
            )
            baseline = repo.designate_close_baseline(
                registered.case_id,
                CloseBaselineRequest(
                    revision_id=second.revision_id,
                    revision_sha256=second.content_sha256,
                    review_id=accepted.review_id,
                    mode="simulation",
                    scenario_id="base",
                    rationale="Freeze the capacity-tested hypothetical-close base scenario for later constructed result comparisons.",
                ),
            )
            revisions = repo.list_case_revisions(registered.case_id)
            reviews = repo.list_case_reviews(registered.case_id)
            return {
                "classification": "constructed_operating_exercise",
                "case": repo.get_investment_case(registered.case_id).model_dump(mode="json"),
                "revisions": [r.model_dump(mode="json") for r in revisions],
                "reviews": [r.model_dump(mode="json") for r in reviews],
                "comparison": compare_revisions(first, second),
                "audit": [a.model_dump(mode="json") for a in repo.list_audit(company_id=company_id)],
                "close_baseline": close_baseline_view(baseline, second, reviews, [baseline]),
                "human_review_count": 0,
                "note": "Two explicitly simulated research reviews, generated by a service identity. Hypothetical effective dates do not represent actual ownership events. This replay uses isolated memory storage; the same contracts are verified against PostgreSQL. Receipt IDs and recording timestamps are newly generated on each replay; numeric results are reproducible.",
            }


def render_case_history(report: dict[str, Any], json_name: str = "case-history.json") -> str:
    case = report["case"]
    revisions = report["revisions"]
    original = report["comparison"]["original_financials"]
    current = report["comparison"]["current_financials"]
    before = next(s for s in original["scenarios"] if s["scenario_id"] == "base")
    after = next(s for s in current["scenarios"] if s["scenario_id"] == "base")
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed case / Versioned decisions</p>"
        "<h1>Keep the original. Explain the change.</h1>"
        f"<p class='page-subtitle'>{escape(case['currency'])} · Two immutable research revisions · Simulated reviews</p>"
        "<p>The original underwriting survives a resource challenge. The revised forecast records what changed without rewriting the earlier judgment.</p>"
        "</div><aside class='hero-aside'><span class='metric-label'>Evidence boundary</span><p>No actual human review, company intervention or realized result is represented.</p></aside></section>"
        "<div class='metrics-grid'>"
    )
    for label, value, note in (
        ("Original year-one EBITDA", amount(before["year_one"]["incremental_ebitda"]), "Frozen original calculation"),
        ("Revised year-one EBITDA", amount(after["year_one"]["incremental_ebitda"]), "Capacity-constrained proposal"),
        (
            "Change in forecast",
            amount(
                Decimal(after["year_one"]["incremental_ebitda"]) - Decimal(before["year_one"]["incremental_ebitda"])
            ),
            "Timing change; costs retained",
        ),
        ("Observed financial result", "Unavailable", "No actual operating or accounting observations"),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{escape(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div><section class='panel' id='history'><h2>The review sequence</h2>"
    body += table(
        ["Revision / hypothetical stage", "Reason for the change", "Review receipt", "Human review"],
        [
            [
                f"<strong>Revision {r['sequence']}</strong><br>{escape(r['draft']['stage'].replace('_', ' '))}<br>{escape(r['draft']['effective_on'])}",
                escape(r["draft"]["reason"]),
                "<br>".join(
                    f"<strong>Simulated {escape(review['decision'].replace('_', ' '))}</strong><br>{escape(review['rationale'])}"
                    for review in report["reviews"]
                    if review["revision_id"] == r["revision_id"]
                ),
                "Not performed",
            ]
            for r in revisions
        ],
        "Effective dates are hypothetical exercise dates. Actual record creation times and service authorship are preserved separately.",
    )
    body += "<p>Each receipt binds a specific revision ID and content hash. Changing inputs creates a new revision; it does not transfer the earlier receipt to the new forecast. Simulated acceptance cannot become human acceptance or activate KPIs.</p></section>"
    designation = report["close_baseline"]
    baseline = designation["baseline"]
    body += "<section class='panel' id='close-baseline'><p class='eyebrow'>Constructed comparison anchor</p><h2>Freeze the reviewed hypothetical close</h2>"
    body += f"<p>{escape(designation['authority'])}</p><p><strong>Mode:</strong> {escape(baseline['request']['mode'])} · <strong>Supporting review:</strong> {escape(designation['supporting_review_status'])} · <strong>Scenario:</strong> {escape(baseline['request']['scenario_id'])}</p>"
    body += table(
        ["Frozen base scenario", "Case currency"],
        [
            ["Year-one incremental EBITDA", amount(designation["frozen_forecast"]["year_one"]["incremental_ebitda"])],
            ["Year-one pre-tax cash proxy", amount(designation["frozen_forecast"]["year_one"]["pre_tax_cash_proxy"])],
        ],
        "Read from the immutable revision snapshot. Subsequent forecasts do not recalculate or move this anchor.",
    )
    body += "<p>If its supporting review is superseded or withdrawn, the designation remains in history but becomes unusable for an accepted comparison. Replacing the baseline requires an explicit new designation; the original remains available. No observed actuals are attached yet.</p>"
    body += f"<details><summary>Inspect the frozen designation</summary><p>Baseline <code>{escape(baseline['baseline_id'])}</code></p><p>Designation SHA-256 <code>{escape(baseline['content_sha256'])}</code></p><p>Revision <code>{escape(baseline['request']['revision_id'])}</code></p><p>Review <code>{escape(baseline['request']['review_id'])}</code></p><p>{escape(baseline['request']['rationale'])}</p></details></section>"
    body += "<section class='panel' id='comparison'><h2>Original, current and actual</h2>"
    body += table(
        ["Base-scenario measure", "Original", "Current", "Change", "Actual"],
        [
            [
                label,
                amount(before[period][metric]),
                amount(after[period][metric]),
                amount(Decimal(after[period][metric]) - Decimal(before[period][metric])),
                "Unavailable",
            ]
            for label, period, metric in (
                ("First-100-day EBITDA", "day_100", "incremental_ebitda"),
                ("First-100-day pre-tax cash proxy", "day_100", "pre_tax_cash_proxy"),
                ("Year-one EBITDA", "year_one", "incremental_ebitda"),
                ("Year-one pre-tax cash proxy", "year_one", "pre_tax_cash_proxy"),
                ("Year-two recurring contribution", "year_two", "recurring_contribution"),
            )
        ],
        "Differences are between stored modeled forecasts, not financial attribution or realized value. All figures in the case currency.",
    )
    timing = json.loads(revisions[-1]["schedule_result_json"])["timing"]
    body += table(
        ["Base initiative", "Original benefit date", "Revised benefit date"],
        [
            [
                escape(t["initiative_id"]),
                escape(t["original_effective_on"]),
                escape(t["scheduled_effective_on"] or "Unavailable"),
            ]
            for t in timing
            if t["scenario_id"] == "base"
        ],
        "Dates come from the stored schedule revision. Original costs remain in the forecast.",
    )
    body += "<p><a href='operating-plan.html'>Inspect the capacity constraint and dates</a> · <a href='underwriting.html'>Challenge the original economics</a></p></section>"
    body += "<section class='panel' id='evidence'><h2>What remains unproven</h2><p>Commercial eligibility, confirmed assignments, accepted deliverables, observed performance, accounting reconciliation and causal attribution remain absent. The next realization layer must attach period evidence and preserve unexplained residuals; a favorable KPI or simulated review is insufficient.</p>"
    for revision in revisions:
        body += f"<details><summary>Revision {revision['sequence']}: immutable content and recording evidence</summary><p>Revision <code>{escape(revision['revision_id'])}</code></p><p>Parent <code>{escape(str(revision['parent_revision_id'] or 'None — original'))}</code></p><p>Content SHA-256 <code>{escape(revision['content_sha256'])}</code></p><p>Recorded {escape(revision['recorded_at'])} by {escape(revision['author'])}</p>"
        body += (
            table(
                ["Receipt", "Mode / decision", "Actor", "Exact revision hash"],
                [
                    [
                        escape(review["review_id"]),
                        escape(review["mode"] + " / " + review["decision"]),
                        escape(review["actor"]),
                        f"<code>{escape(review['revision_sha256'])}</code>",
                    ]
                    for review in report["reviews"]
                    if review["revision_id"] == revision["revision_id"]
                ],
                "Human identities are never invented for this exercise.",
            )
            + "</details>"
        )
    body += f"<p>{escape(report['note'])}</p><p><a href='{escape(json_name, quote=True)}' download>Download the complete case history and frozen forecast JSON</a></p></section>"
    return exhibit_page(
        title="Case revision history — constructed exercise",
        kind="Case history",
        provenance="Constructed exercise",
        nav=[("#history", "History"), ("#comparison", "Comparison"), ("#evidence", "Evidence")],
        body=body,
    )


def build_case_demo(underwriting: Path, operating_plan: Path, output: Path) -> Path:
    case = UnderwritingCase.model_validate_json(underwriting.read_bytes())
    plan = OperatingPlan.model_validate_json(operating_plan.read_bytes())
    report = demonstrate_revisions(case, plan)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {underwriting.resolve(), operating_plan.resolve()} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite its source inputs")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_case_history(report, json_path.name), encoding="utf-8")
    return html_path
