"""Readable original / non-reliance / corrected disclosure exhibit."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..api.presentation import CSS
from ..research.render import table
from .restatements import RestatementHistory, analyze_restatement


def render_restatement(report: dict[str, Any], json_name: str) -> str:
    history = report["history"]
    values = {r["metric"]: r for r in report["comparison"]}

    def money(value: str) -> str:
        return f"{Decimal(value) / 1000000:,.3f}"

    body = (
        "<section class='hero'><div><p class='eyebrow'>Progress Software / Historical accounting correction</p>"
        "<h1>Preserve the original. Suspend reliance. Review the correction.</h1>"
        "<p class='page-subtitle'>FY2005 financial statements, corrected in 2006.</p>"
        "<p>A real accounting-error restatement, with separately retrieved original and amended filings. "
        "This historical example is separate from the current-company thesis and constructed operating case.</p></div>"
        "<aside class='hero-aside'><span class='metric-label'>Exact public-availability replay</span>"
        f"<strong class='metric-value'>{'Withheld' if report['public_availability']['status'].startswith('withheld') else 'Registered sources only'}</strong>"
        "<span class='metric-note'>A dated chronology does not establish intraday availability.</span></aside></section>"
        "<section class='panel' id='decision'><h2>The diligence decision</h2>"
        "<p><strong>Reopen the earnings baseline when reliance is withdrawn.</strong> "
        "Keep the original record for audit history, suspend its use in a current decision, "
        "and review the correction before accepting a replacement baseline.</p>"
        f"<p>FY2005 operating income changes from ${money(values['operating_income']['original'])} million "
        f"to ${money(values['operating_income']['restated'])} million; net income changes from "
        f"${money(values['net_income']['original'])} million to ${money(values['net_income']['restated'])} million. "
        f"Operating cash flow remains ${money(values['operating_cash_flow']['restated'])} million. "
        "An earnings correction is not automatically a cash outflow or an EBITDA add-back.</p>"
        f"<p>Cash and equivalents change by ${money(values['cash']['adjustment'])} million, "
        "with an offsetting short-term-investment reclassification. Combined cash and investments "
        "are unchanged. This is not an operating cash-saving initiative.</p></section>"
        "<section class='panel' id='chronology'><h2>Four disclosures, distinct roles</h2>"
        "<p>The table reconstructs stated release dates and filing metadata. It does not assert "
        "that an investor could access a document at a particular historical instant.</p>"
    )
    body += table(
        ["Reported date", "Disclosure", "Date basis", "Evidence"],
        [
            [
                escape(e["reported_on"]),
                escape(e["kind"].replace("_", " ")),
                escape(e["date_basis"].replace("_", " ")),
                f"<a href='{escape(e['source_url'], quote=True)}'>Source</a><p>{escape(e['locator'])}</p>",
            ]
            for e in history["events"]
        ],
        "The August notice predates the December correction. The announcement and amended filing retain different dates.",
    )
    body += "<h3>Calendar reconstruction</h3>"
    body += table(
        ["Date cutoff", "Registered state", "Numeric snapshot"],
        [
            [
                escape(r["cutoff"]),
                escape(r["status"].replace("_", " ")),
                escape(r["selected"]["snapshot_id"] if r["selected"] else "None selected"),
            ]
            for r in report["date_replay"]
        ],
        "Retrospective date-only selection. The non-reliance interval returns no financial snapshot; the announcement does not substitute for the mapped amendment.",
    )
    body += (
        "<p>Exact-publication selection remains withheld because the required timestamps are missing. "
        "Neither SEC acceptance nor today's PDF retrieval supplies that missing evidence. "
        "The publication-time portion of OP-16 remains open.</p></section>"
        "<section class='panel' id='numbers'><h2>Reconcile the correction</h2>"
    )
    body += table(
        ["FY2005 measure", "Original / USD millions", "Adjustment / USD millions", "Restated / USD millions"],
        [
            [escape(r["label"]), *[money(r[k]) for k in ("original", "adjustment", "restated")]]
            for r in report["comparison"]
        ],
        "The original column comes from the original filing. The amendment's reported/adjustment/restated columns independently tie to both snapshots.",
    )
    bridge = history["net_income_bridge"]
    body += (
        f"<p>Net income bridge, USD millions: {money(values['net_income']['original'])} "
        f"less {Decimal(bridge['additional_stock_compensation']) / 1000:,.3f} additional stock compensation, "
        f"less {Decimal(bridge['additional_payroll_withholding']) / 1000:,.3f} payroll withholding, "
        f"plus {Decimal(bridge['income_tax_benefit']) / 1000:,.3f} tax benefit "
        f"equals {money(values['net_income']['restated'])}. "
        f"See amendment PDF page {bridge['pdf_page']}.</p>"
        "<p>Each snapshot separately reconciles revenue to operating income, pretax income to net income, "
        "cash plus investments, cash-flow subtotals and opening-to-closing cash. These arithmetic checks "
        "do not establish independent finance approval.</p></section>"
        "<section class='panel' id='sources'><h2>Inspect the source versions</h2>"
    )
    for key in ("original", "amended"):
        source = history[key]
        body += (
            f"<details><summary>{escape(source['snapshot_id'])} / {escape(source['form'])}</summary>"
            f"<p><a href='{escape(source['url'], quote=True)}'>Issuer-hosted PDF</a> · "
            f"accession {escape(source['accession'])} · retrieved {escape(source['retrieved_at'])}</p>"
            f"<p>Source SHA-256: <code>{escape(source['sha256'])}</code></p>"
        )
        body += (
            table(
                ["Measure", "Reported / USD thousands", "PDF / printed page", "Column"],
                [
                    [
                        escape(r["label"]),
                        escape(r["amount"]),
                        f"{r['pdf_page']} / {escape(r['printed_page'])}",
                        escape(r["column"]),
                    ]
                    for r in source["rows"]
                ],
                "Selected FY2005 rows only; full filings remain available at the linked sources.",
            )
            + "</details>"
        )
    body += "<h3>Limits retained</h3><ul>" + "".join(f"<li>{escape(x)}</li>" for x in report["limitations"]) + "</ul>"
    body += (
        f"<p><a href='{escape(json_name, quote=True)}' download>Download sources, corrections and date reconstruction</a> · "
        "<a href='disclosure-history.html'>Acquisition disclosure comparison</a> · "
        "<a href='decision-memo.html'>Current executive memo</a></p></section>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Progress Software — accounting restatement</title><style>{CSS}</style></head><body>"
        "<a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'>"
        "<a class='brand' href='../index.html'>Value Creation OS · Diligence</a>"
        "<nav class='primary-nav' aria-label='Restatement sections'><a class='nav-link' href='#decision'>Decision</a>"
        "<a class='nav-link' href='#chronology'>Chronology</a><a class='nav-link' href='#numbers'>Numbers</a>"
        "<a class='nav-link' href='#sources'>Sources</a></nav></div></header>"
        "<main id='main' tabindex='-1' class='app-shell'>" + body + "</main></body></html>"
    )


def build_restatement_report(source: Path, output: Path) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if source.resolve() in {html_path.resolve(), json_path.resolve()}:
        raise ValueError("restatement output must not overwrite its source")
    report = analyze_restatement(RestatementHistory.model_validate_json(source.read_bytes()))
    html = render_restatement(report, json_path.name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    html_path.write_text(html, encoding="utf-8", newline="\n")
    return html_path
