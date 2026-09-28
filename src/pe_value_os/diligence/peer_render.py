"""Executive peer exhibit with visible sample limits and inspectable selection evidence."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from ..research.render import table


def _percent(value: Any) -> str:
    return "Withheld" if value is None else f"{Decimal(str(value)) * 100:,.1f}%"


def render_peers(report: dict[str, Any]) -> str:
    rows = []
    for metric in report["metrics"].values():
        cohorts = metric["cohorts"]
        rows.append(
            [
                escape(metric["label"]),
                _percent(metric["focal"]["value"]),
                f"{_percent(cohorts['all_eligible']['median'])} · n={cohorts['all_eligible']['count']}",
                f"{_percent(cohorts['strict']['median'])} · n={cohorts['strict']['count']}",
            ]
        )
    html = (
        "<section class='panel' id='peers'><p class='eyebrow'>Peer context / Selection sensitivity</p>"
        "<h2>Comparable enough to inform questions, not set targets</h2>"
        "<p>Reported margin context depends on the metric and the selected cohort. "
        "Medians are withheld below three eligible companies. Organic growth and ARR comparisons remain withheld.</p>"
        + table(
            ["Measure", "Progress annual anchor", "All eligible context", "Stricter cohort"],
            rows,
            f"Annual periods closest to {report['anchor']['end']}; actual dates and eligibility below. At least three observations are required for a median.",
        )
        + f"<p>{escape(report['limitation'])}</p>"
        + "<p><strong>Decision implication:</strong> investigate revenue recognition, acquisition accounting and cash timing "
        "before interpreting a margin difference. No peer-implied EBITDA opportunity is sized.</p>"
        "<details><summary>Inspect candidate selection, exclusions and source evidence</summary>"
    )
    html += "<ol>" + "".join(f"<li>{escape(rule)}</li>" for rule in report["context"]["selection_rules"]) + "</ol>"
    supplement = report["context"]["focal_cash_reconciliation"]
    doc = supplement["documents"][0]
    html += f"<p>Progress cash reconciliation adds three net-income rows from <a href='{escape(doc['url'], quote=True)}#page=41'>FY2025 filing PDF page 41</a>, reconciled to the income statement. The original financial bundle remains unchanged.</p>"
    candidates = {c["candidate_id"]: c for c in report["context"]["candidates"]}
    for observation in report["observations"]:
        candidate = candidates[observation["candidate_id"]]
        period = observation["period"]
        period_text = f"{period['start']} to {period['end']}" if period else "No verified annual facts"
        html += f"<h3>{escape(candidate['company'])}</h3><p>{escape(period_text)} · {escape(candidate['selection_rationale'])}</p>"
        html += table(
            ["Metric", "Eligibility", "Reported ratio", "Rationale / blockers"],
            [
                [
                    escape(report["metrics"][key]["label"]),
                    escape(m["status"].replace("_", " ")),
                    _percent(m["value"]),
                    escape(m["rationale"] + (" " + "; ".join(m["blocked_by"]) if m["blocked_by"] else "")),
                ]
                for key, m in observation["metrics"].items()
            ],
            "Eligibility is specific to the metric; strict eligibility does not establish executable savings.",
        )
        html += f"<p><a href='{escape(candidate['filing_index'], quote=True)}'>Filing identity and date</a></p>"
        if candidate["facts"] is not None:
            doc = candidate["facts"]["documents"][0]
            for note in candidate["disclosures"]:
                html += (
                    f"<p><a href='{escape(doc['url'], quote=True)}#page={note['pdf_page']}'>"
                    f"{escape(note['evidence_id'])} · PDF page {note['pdf_page']}</a>: "
                    f"{escape(note['reported_summary'])} {escape(note['analytical_limit'])}</p>"
                )
            html += "<details><summary>Inspect mapped financial rows and document fingerprint</summary>"
            html += table(
                ["Period end", "Metric", "Reported amount", "Units", "Source row"],
                [
                    [
                        escape(f["period"]["end"]),
                        escape(f["metric"].replace("_", " ")),
                        escape(str(f["reported_amount"])),
                        f"{escape(f['currency'])} × {f['unit_scale']:,}",
                        f"<a href='{escape(doc['url'], quote=True)}#page={f['pdf_page']}'>PDF {f['pdf_page']}</a> · {escape(f['source_row'])}",
                    ]
                    for f in candidate["facts"]["facts"]
                ],
                "Original comparative rows are preserved. Only the selected annual period enters the comparison.",
            )
            html += f"<p class='muted'>Source SHA-256 <code>{doc['sha256']}</code> · extraction {escape(doc['extraction_version'])}</p></details>"
    return (
        html
        + f"</details><p class='muted'>Context SHA-256 <code>{report['context_sha256']}</code> · metric-peer-context/1</p></section>"
    )
