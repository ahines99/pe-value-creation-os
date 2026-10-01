"""Executive first-wave proposal and auditable resource/financial comparisons."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from ..research.render import table
from .exhibit_style import exhibit_page
from .scheduling import OperatingPlan, evaluate_plan
from .underwriting_models import read_underwriting
from .underwriting_render import amount, render_allocation


def render_plan(plan: OperatingPlan, report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, date):
            return f"<time style='white-space:nowrap' datetime='{value.isoformat()}'>{value.isoformat()}</time>"
        return escape(str(value if value is not None else "Unavailable"))

    tasks = report["tasks"]
    delayed = [t for t in tasks if t["candidate_rejections"] and t["status"] == "scheduled"]
    blocked = [t for t in tasks if t["status"] == "blocked"]
    original = {s["scenario_id"]: s for s in report["original_financials"]["scenarios"]}
    revised = {s["scenario_id"]: s for s in report["scheduled_financials"]["scenarios"]}
    base = revised["base"]
    currency = cell(report["scheduled_financials"]["currency"])
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed operating exercise / 100-day plan</p>"
        "<h1>Sequence the work. Reprice the delay.</h1>"
        f"<p class='page-subtitle'>{cell(plan.start)} to {cell(report['end'])} · {cell(report['scheduled_financials']['currency'])} · Proposed capacity and assignments</p>"
        "<p>A feasible first-wave proposal under explicit assumptions. No actual Progress staffing, management approval or completed intervention is represented.</p>"
        "</div><aside class='hero-aside'><span class='metric-label'>Decision due</span><p>Challenge the resource budgets, order and acceptance gates before authorizing a first wave.</p></aside></section>"
        "<div class='metrics-grid'>"
    )
    for label, value, note in (
        (
            "Work packages scheduled",
            str(len(tasks) - len(blocked)),
            f"{len(blocked)} blocked; {len(delayed)} delayed by capacity",
        ),
        (
            "Year-one EBITDA change",
            amount(base["year_one"]["incremental_ebitda"]),
            "Base scenario after schedule constraints",
        ),
        (
            "First 100 days: cash",
            amount(base["day_100"]["pre_tax_cash_proxy"]),
            "Pre-tax cash proxy; collection timing is temporary",
        ),
        (
            "Maximum funding need",
            amount(base["maximum_dated_funding_need"]),
            "Dated cash; original cost commitments retained",
        ),
    ):
        unit = "" if label == "Work packages scheduled" else f" <span class='x-unit'>{currency}</span>"
        body += f"<div class='metric-card'><span class='metric-label'>{cell(label)}</span><strong class='metric-value'>{cell(value)}{unit}</strong><span class='metric-note'>{cell(note)}</span></div>"
    body += (
        "</div><section class='panel'><h2>Proposed first-wave decision</h2>"
        f"<p>{cell(plan.sequencing_rationale)}</p><p>{cell(report['authority'])}</p>"
        "<p>Scheduled acceptance is a forecasting assumption. Actual benefit recognition still requires evidence that the deliverable was accepted and the operating effect occurred.</p>"
        f"<p><strong>Cost discipline:</strong> {cell(report['cost_treatment'])}</p>"
        "<p><a href='underwriting.html'>Inspect the original economic assumptions</a> · <a href='progress-baseline.html'>Review the separate public-company baseline</a></p></section>"
    )
    if "selected_initiatives" in report:
        body += (
            "<section class='panel'><h2>Work excluded from this selection</h2>"
            f"<p>{cell(report['selection_treatment'])}</p>"
            + table(
                ["Work package", "Initiative", "Acceptance requirement retained for future selection"],
                [
                    [cell(t["title"]), cell(t["initiative_id"]), cell(t["acceptance_evidence"])]
                    for t in report["excluded_tasks"]
                ],
                "Excluded work consumes no capacity in this proposal; it remains visible for a later explicit decision.",
            )
            + "</section>"
        )
        if "interaction_policy" in report["scheduled_financials"]:
            body += render_allocation(report["scheduled_financials"])
    body += "<section class='panel' id='plan'><h2>100-day work and acceptance gates</h2>"
    body += table(
        ["Work / accountable role", "Start", "Finish", "Status / dependencies", "Required acceptance evidence"],
        [
            [
                f"<strong>{cell(t['title'])}</strong><br>{cell(t['accountable_resource'])}<br><small>{cell(t['task_id'])}</small>",
                cell(t["scheduled_start"]),
                cell(t["scheduled_finish"]),
                f"{cell(t['status'])}<br>{cell(', '.join(t['prerequisites']) or 'None')}<br>{cell(t['reason'])}",
                f"{cell(t['acceptance_evidence'])}<br><small>Reviewer: {cell(t['acceptance_reviewer'])}</small>",
            ]
            for t in tasks
        ],
        "Proposed dates, not completed milestones. Foundation work consumes capacity without creating a separate financial benefit.",
    )
    for task in tasks:
        if task["candidate_rejections"]:
            body += f"<details><summary>Why {cell(task['title'])} could not start earlier</summary>"
            body += (
                table(
                    ["Candidate start", "Week", "Constraint", "Competing work / remaining hours"],
                    [
                        [
                            cell(candidate["start"]),
                            cell(conflict["week"]),
                            cell(conflict["kind"] + ": " + conflict.get("resource_id", "workstreams")),
                            cell(", ".join(conflict.get("competing_tasks", conflict.get("workstreams", []))))
                            + "<br>"
                            + (
                                f"Remaining {cell(conflict['available'])}; requires {cell(conflict['required'])}"
                                if "required" in conflict
                                else "Concurrent workstream limit"
                            ),
                        ]
                        for candidate in task["candidate_rejections"]
                        for conflict in candidate["conflicts"]
                    ],
                    "Every rejected earlier slot retains its actual capacity or concurrency conflict.",
                )
                + "</details>"
            )
    body += "</section><section class='panel' id='economics'><h2>Timing changes the forecast</h2>"
    body += table(
        [
            "Scenario",
            "Original year-one EBITDA",
            "Scheduled year-one EBITDA",
            "EBITDA change",
            "Original day-100 cash",
            "Scheduled day-100 cash",
        ],
        [
            [
                cell(key),
                amount(original[key]["year_one"]["incremental_ebitda"]),
                amount(value["year_one"]["incremental_ebitda"]),
                amount(value["year_one"]["incremental_ebitda"] - original[key]["year_one"]["incremental_ebitda"]),
                amount(original[key]["day_100"]["pre_tax_cash_proxy"]),
                amount(value["day_100"]["pre_tax_cash_proxy"]),
            ]
            for key, value in revised.items()
        ],
        "Same shared financial engine, assumptions and original costs. Only benefit availability and start dates change.",
    )
    body += table(
        ["Scenario / initiative", "Original benefit date", "Scheduled benefit date", "Rule / limitation"],
        [
            [
                cell(t["scenario_id"] + " / " + t["initiative_id"]),
                cell(t["original_effective_on"]),
                cell(t["scheduled_effective_on"]),
                cell(t["reason"]),
            ]
            for t in report["timing"]
        ],
        "No earlier-than-original benefit. Missing a collections counterfactual date cannot create a fictitious cash advantage.",
    )
    body += "<p>Valuation remains a multiple sensitivity on year-two recurring contribution, not company fair value. Full monthly, cash and valuation comparisons are in the companion JSON.</p></section>"
    body += "<section class='panel' id='capacity'><h2>Weekly change capacity</h2>"
    for resource in report["capacity"]:
        body += f"<details><summary>{cell(resource['proposed_operator'])} · {cell(resource['assignment'])}</summary>"
        body += (
            table(
                ["Week / period", "Net budget hours", "Planned hours", "Work packages"],
                [
                    [
                        f"{cell(w['week'])} · {cell(w['start'])}–{cell(w['end'])}",
                        cell(w["budget_hours"]),
                        cell(w["used_hours"]),
                        cell(", ".join(w["tasks"]) or "No planned work"),
                    ]
                    for w in resource["weeks"]
                ],
                "Unknown capacity is not zero and cannot authorize allocation. All hours are constructed, net of ordinary duties.",
            )
            + "</details>"
        )
    body += f"<p>{cell(report['method'])}</p></section>"
    body += "<section class='panel'><h2>Steering and evidence still due</h2><p>Days 30, 60 and 100 are proposed review checkpoints. Review source exceptions and eligibility; then intervention and quality evidence; then financial variance, attribution and unresolved claims. A failed acceptance gate requires a revised forecast, not a retroactive success claim.</p><p><a href='case-history.html'>Case history</a> preserves original forecasts and exact-version research reviews separately. Actual assignments, accepted deliverables and financial actuals remain unobserved; the attribution ledger remains implementation work.</p>"
    body += f"<details><summary>Calculation lineage</summary><p>Plan {cell(plan.plan_id)} · revision {cell(plan.revision_id)}</p><p>Original underwriting <code>{report['original_underwriting_sha256']}</code></p><p>Plan <code>{report['plan_sha256']}</code></p><p>Report <code>{report['report_sha256']}</code></p><p>{cell(report['schedule_version'])} · {cell(report['scheduled_financials']['calculation_version'])}</p></details></section>"
    return exhibit_page(
        title="100-day operating plan — constructed exercise",
        kind="Operating plan",
        provenance="Constructed exercise",
        nav=[("#plan", "Plan"), ("#economics", "Economics"), ("#capacity", "Capacity")],
        body=body,
    )


def build_operating_report(source: Path, underwriting: Path, output: Path) -> Path:
    plan = OperatingPlan.model_validate_json(source.read_bytes())
    case = read_underwriting(underwriting.read_bytes())
    report = evaluate_plan(plan, case)
    html = render_plan(plan, report)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {source.resolve(), underwriting.resolve()} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite its inputs")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
