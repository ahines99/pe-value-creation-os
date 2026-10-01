"""Self-contained executive research memo with source definitions and audit detail."""

from __future__ import annotations

import re
from decimal import Decimal
from html import escape
from typing import Any

from ..diligence.exhibit_style import exhibit_page
from .pilot import METRICS


def text(value: Any) -> str:
    return escape(str(value))


def number(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "Not available"
    amount = Decimal(str(value))
    return f"{amount * 100:,.1f}%" if percent else f"{amount:,.3f}"


# A displayed figure: signed, grouped and optionally a percentage, multiple or point change, or two
# such figures separated by " / ", or a figure followed by its share in parentheses.
_FIGURE = r"[-+−]?\$?\d[\d,]*(?:\.\d+)?(?:%| ?pp|x|×)?"
_NUMERIC = re.compile(rf"^{_FIGURE}(?: / {_FIGURE}| \({_FIGURE}\))?$")
# Placeholders that may sit in a figure column without making it a text column.
_PLACEHOLDERS = {"", "—", "Withheld", "Not available", "Unavailable", "Missing source"}
_TAG = re.compile(r"<[^>]+>")
# Short ISO dates or date ranges that read badly when wrapped mid-date.
_DATE = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?(?: to \d{4}-\d{2}-\d{2})?(?: · [a-z_ ]+)?$")


def _column_classes(rows: list[list[str]]) -> dict[int, str]:
    """Classify columns after the first: figures (or explicit placeholders) and unbroken dates.

    Callers exclude total rows, whose status text (for example "Reconciled") follows the column.
    """
    classes: dict[int, str] = {}
    for i in range(max((len(r) for r in rows), default=0)):
        cells = [_TAG.sub("", r[i]).strip() for r in rows if i < len(r)]
        if i and any(_NUMERIC.match(c) for c in cells) and all(_NUMERIC.match(c) or c in _PLACEHOLDERS for c in cells):
            classes[i] = " class='num'"
        elif cells and all(_DATE.match(c) for c in cells):
            classes[i] = " class='x-date'"
    return classes


def table(headers: list[str], rows: list[list[str]], caption: str, *, totals: tuple[int, ...] = ()) -> str:
    """Render an accessible table; figure columns align right and ``totals`` rows read as totals."""
    emphasis = {t % len(rows) for t in totals} if rows else set()
    classes = _column_classes([row for r, row in enumerate(rows) if r not in emphasis] or rows)

    def cls(i: int) -> str:
        return classes.get(i, "")

    return (
        f"<div class='table-wrap' tabindex='0' role='region' aria-label='{text(caption)}'>"
        f"<table><caption class='table-caption'>{text(caption)}</caption><thead><tr>"
        + "".join(f"<th scope='col'{cls(i)}>{text(h)}</th>" for i, h in enumerate(headers))
        + "</tr></thead><tbody>"
        + "".join(
            ("<tr class='x-total'>" if r in emphasis else "<tr>")
            + "".join(f"<td{cls(i)}>{cell}</td>" for i, cell in enumerate(row))
            + "</tr>"
            for r, row in enumerate(rows)
        )
        + "</tbody></table></div>"
    )


def render_report(report: dict[str, Any]) -> str:
    focal = report["focal"]
    currency = text(focal["currency"])
    classification = (
        "Private licensed research" if report["classification"] == "licensed_private" else "Synthetic test research"
    )
    origin = (
        "Licensed company financial statements"
        if report["classification"] == "licensed_private"
        else "Fictional financial statements"
    )
    cards = [
        ("Revenue", number(focal["revenue"]), f"{currency} millions · annual"),
        (
            "Revenue growth",
            number(report["focal_metrics"]["revenue_growth"], percent=True),
            "Includes acquisition effects",
        ),
        ("Comparison set", str(len(report["peers"])), "Candidate peers · reviewer selection pending"),
        ("Decision status", "Research", "Human acceptance pending"),
    ]
    body = (
        f"<section class='hero'><div><p class='eyebrow'>{classification} / Investment diligence</p>"
        f"<h1>{text(focal['company'])}</h1><p class='page-subtitle'>What do the financials suggest we should investigate?</p>"
        f"<p class='page-subtitle'>Annual anchor: {text(focal['period_end'])} · {text(focal['ticker'])} · "
        f"Data cutoff: {text(report['as_of'][:10])}</p></div><div class='hero-aside'>"
        "<span class='metric-label'>Mandate</span><p>Establish the baseline. Compare the cost structure. "
        "Design the diligence that would support an operating decision.</p></div></section>"
        "<div class='metrics-grid'>"
        + "".join(
            f"<div class='metric-card'><span class='metric-label'>{a}</span>"
            f"<strong class='metric-value'>{b}</strong><span class='metric-note'>{c}</span></div>"
            for a, b, c in cards
        )
        + "</div><section class='panel'><h2>Investment committee readout</h2>"
        f"<p>{origin} provide the baseline for this review. "
        "Peer differences identify questions; they do not establish avoidable cost, organic growth, or achievable EBITDA.</p>"
        "<p>Before sizing an initiative, reconcile accounting definitions, acquisition effects, revenue mix and fiscal periods. "
        "Customer, contract, headcount and process-level operating data remain necessary.</p></section>"
    )
    comparison = []
    for key, label in METRICS.items():
        benchmark = report["benchmarks"][key]
        own = report["focal_metrics"][key]
        delta = (
            (Decimal(str(own)) - Decimal(str(benchmark["median"]))) * 100
            if own is not None and benchmark["median"] is not None
            else None
        )
        comparison.append(
            [
                text(label),
                number(own, percent=True),
                number(benchmark["median"], percent=True),
                f"{delta:+.1f} pp" if delta is not None else "Not available",
                str(benchmark["n"]),
            ]
        )
    body += "<section class='panel' id='comparison'><h2>Peer context</h2>"
    body += table(
        ["Metric", "Focal company", "Peer median", "Difference", "Peer n"],
        comparison,
        "Equal-weight medians exclude the focal company; each metric shows its available sample.",
    )
    body += "<p class='muted'>Standardized metrics are not interchangeable with issuer GAAP or non-GAAP metrics. "
    body += "Periods may differ by up to 183 days. No currency conversion is applied.</p></section>"
    peer_rows = []
    for peer in report["peers"]:
        row = peer["statement"]
        peer_rows.append(
            [
                text(row["ticker"]),
                text(row["period_end"]),
                str(peer["alignment_days"]),
                number(row["revenue"]),
                number(peer["metrics"]["sga_intensity"], percent=True),
                text(peer["rationale"]),
                text(peer["limitation"]),
            ]
        )
    body += "<details><summary>Inspect the candidate peer group and comparability limits</summary>"
    body += (
        table(
            [
                "Company",
                "Period end",
                "Days vs anchor",
                f"Revenue ({currency}m)",
                "SG&A / revenue",
                "Reason",
                "Limitation",
            ],
            peer_rows,
            "Nearest eligible annual period in the same reporting currency; a reviewer must approve the comparison set.",
        )
        + "</details>"
    )
    annual: list[list[str]] = []
    quarterly: list[list[str]] = []
    for item in report["history"]:
        row = item["statement"]
        cells = [
            text(row["period_end"]),
            text(row["fiscal_year"]),
            text(row["currency"]),
            number(row["revenue"]),
            number(item["metrics"]["revenue_growth"], percent=True),
            number(item["metrics"]["sga_intensity"], percent=True),
            number(item["metrics"]["operating_margin"], percent=True),
        ]
        (annual if row["period"] == "annual" else quarterly).append(cells)
    body += "<section class='panel' id='history'><h2>Financial trajectory</h2>"
    headers = [
        "Period end",
        "Fiscal year",
        "Currency",
        "Revenue (millions)",
        "Year-on-year",
        "SG&A / revenue",
        "Standardized operating margin",
    ]
    body += table(headers, annual, "Annual history; current-vintage statements, not a historical trading backtest.")
    body += "<details><summary>Recent quarterly observations</summary>"
    body += (
        table(headers, quarterly[-12:], "Discrete quarters only; no monthly interpolation or annualization.")
        + "</details></section>"
    )
    body += "<section class='panel' id='reconciliation'><h2>Source reconciliation</h2>"
    checks = []
    for check in report["reconciliations"]:
        checks.append(
            [
                text(check["metric"]),
                number(check["reported_millions"]),
                number(check["bridge_millions"]),
                number(check["actual"]),
                text(check["status"]),
                text(check["explanation"]),
                f"<a href='{text(check['source_url'])}' rel='noreferrer'>{text(check['source_locator'])}</a>",
            ]
        )
    body += table(
        ["Field", "Reported", "Bridge", "Standardized", "Result", "Interpretation", "Source"],
        checks,
        "Amounts in source-currency millions. Reported figure + documented bridge = standardized field; tolerance 0.001m.",
    )
    body += "<p>A matched arithmetic bridge is a source check, not independent human acceptance. "
    body += "Unreconciled fields and peer definitions still require review.</p></section>"
    body += "<section class='panel'><h2>Scale of a margin hypothesis</h2><p>Illustrative sensitivities, not forecasts or savings estimates. "
    body += (
        "A basis point is 0.01% of annual revenue. Implementation cost, feasibility, timing and tax are unmodeled.</p>"
    )
    body += (
        table(
            ["Assumed margin change", f"Gross annual effect ({currency}m)"],
            [
                [f"{r['basis_points']} basis points", number(r["gross_annual_effect_millions"])]
                for r in report["sensitivity"]
            ],
            "Revenue × assumed basis points / 10,000. Scenarios are alternatives and must not be added together.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='diligence'><h2>100-day diligence agenda</h2>"
    body += (
        table(
            ["Window", "Accountable reviewer", "Evidence to collect", "Decision unlocked"],
            [
                [
                    "Days 1–15",
                    "Finance lead",
                    "Source-to-filing bridges; acquisition and currency bridges; peer inclusion rationale",
                    "Accept or revise the baseline",
                ],
                [
                    "Days 16–30",
                    "Commercial lead",
                    "Customer cohorts, price books, renewal terms and discount approvals",
                    "Whether a pricing hypothesis is supportable",
                ],
                [
                    "Days 31–60",
                    "Operating partner + functional owners",
                    "Cost-center detail, workflow volumes, unit costs and service-quality baselines",
                    "Select a bounded operational experiment",
                ],
                [
                    "Days 61–100",
                    "Human approver",
                    "Experiment results, implementation costs, risks and named KPI owners",
                    "Approve, reject or revise an operating plan",
                ],
            ],
            "Research agenda only. No company participation, management approval or operating benefit is implied.",
        )
        + "</section>"
    )
    gaps = report["gaps"] or ["No structural data gaps detected by the automated checks; domain review remains open."]
    body += "<section class='panel'><h2>Open diligence items</h2><ul>" + "".join(f"<li>{text(g)}</li>" for g in gaps)
    body += "<li>Independent analyst recomputation and peer-selection review.</li><li>Operating-partner usefulness assessment and explicit acceptance.</li></ul></section>"
    body += (
        "<details id='methodology'><summary>Technical method and evidence trail</summary><div class='details-content'>"
    )
    body += "<p>Current-vintage retrospective analysis. Overlapping extracts are deduplicated as whole rows by entity, period type and period end; "
    body += "latest eligible vintage wins. Future periods, availability dates and vintages are excluded. No point-in-time historical claim is made.</p>"
    body += f"<p>Input SHA-256: <code>{text(report['input_sha256'])}</code></p><ul>"
    body += "".join(f"<li>{text(note)}</li>" for note in report["source_notes"]) + "</ul>"
    body += table(
        ["Entity", "Period", "End", "Source", "Row", "Vintage", "File SHA-256"],
        [
            [
                text(r[k])
                for k in ("entity_id", "period", "period_end", "source", "source_row", "vintage", "source_sha256")
            ]
            for r in report["selected_statements"]
        ],
        "Exact source row and content hash for each selected statement.",
    )
    body += "</div></details>"
    return exhibit_page(
        title=f"{focal['ticker']} research memo | Value Creation OS",
        kind="Research memo",
        provenance=classification,
        nav=[("#comparison", "Peer context"), ("#reconciliation", "Evidence"), ("#diligence", "Diligence")],
        nav_label="Memo",
        body=body,
        home="#main-content",
        main_id="main-content",
        footer=f"{classification} · Current-vintage analysis · Human acceptance pending. "
        "Keep licensed inputs and derived outputs in authorized private storage.",
    )
