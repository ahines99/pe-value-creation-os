"""Render the public baseline using the executive design system and inspectable source rows."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..api.presentation import CSS
from ..research.render import table
from .financials import analyze_facts
from .models import FactBundle


def _money(value: Any) -> str:
    return "Not available" if value is None else f"{Decimal(str(value)) / 1000000:,.3f}"


def render_baseline(bundle: FactBundle, report: dict[str, Any]) -> str:
    bundle.require_public()
    annual = [p for p in report["periods"] if p["basis"] == "annual"]
    if not annual:
        raise ValueError("public baseline needs an annual period; quarterly facts are not annualized")
    latest = annual[-1]
    currency = latest["currency"]
    company = escape(bundle.company)
    metrics = [
        ("Reported revenue", latest["reported"].get("revenue", {}).get("value"), "US GAAP · annual"),
        ("Reported operating income", latest["reported"].get("operating_income", {}).get("value"), "US GAAP · annual"),
        ("Calculated EBITDA", latest["derived"]["ebitda"]["value"], "Defined below · not issuer-adjusted"),
        (
            "CFO less PP&E purchases",
            latest["derived"]["cfo_less_ppe"]["value"],
            "Historical cash measure · not savings",
        ),
    ]
    body = (
        "<section class='hero'><div><p class='eyebrow'>Public filing diligence / Financial baseline</p>"
        f"<h1>{company}</h1><p class='page-subtitle'>Establish the economics before underwriting an intervention.</p>"
        f"<p>Annual anchor {escape(latest['end'])} · Information cutoff {bundle.information_cutoff} · "
        f"Amounts in {escape(currency)} millions</p></div><aside class='hero-aside'><span class='metric-label'>Decision</span>"
        "<p>Proceed to commercial and operating diligence. Consolidated accounts establish a baseline; "
        "they do not establish executable savings.</p></aside></section><div class='metrics-grid'>"
        + "".join(
            f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{_money(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
            for label, value, note in metrics
        )
        + "</div><section class='panel'><h2>What this case establishes</h2>"
        "<p>Reported annual financials, their source rows and explicit calculation bridges are reproducible "
        "without a vendor account. This is a public-company research case, not a client engagement. "
        "There are no customer records, operating interventions or independently validated savings in this baseline.</p>"
        "<p>Peer eligibility, acquisition effects, contract economics, staffing capacity and implementation costs "
        "must be examined before selecting a value-creation plan. Missing operating information remains a diligence request.</p></section>"
    )
    history = []
    for period in annual:
        history.append(
            [
                escape(period["end"]),
                escape(period["currency"]),
                _money(period["reported"].get("revenue", {}).get("value")),
                _money(period["reported"].get("operating_income", {}).get("value")),
                _money(period["derived"]["ebitda"]["value"]),
                _money(period["derived"]["cfo_less_ppe"]["value"]),
            ]
        )
    body += (
        "<section class='panel' id='history'><h2>Reported financial history</h2>"
        + table(
            ["Year end", "Currency", "Revenue", "Operating income", "Calculated EBITDA", "CFO less PP&E"],
            history,
            "Source-filing comparative periods; missing or unreconciled derived measures are withheld.",
        )
        + "</section>"
    )
    bridges = []
    for period in annual:
        for measure in period["derived"].values():
            operands = measure["formula"]
            lines = [
                f"{'+' if sign > 0 else '−'} {escape(metric.replace('_', ' '))}: {_money(period['reported'].get(metric, {}).get('value'))}"
                for metric, sign in operands.items()
            ]
            status = (
                "Available"
                if measure["value"] is not None
                else "Withheld: " + ", ".join(measure["missing"] + measure["blocked_by"])
            )
            bridges.append(
                [
                    escape(period["end"]),
                    escape(measure["label"]),
                    "<br>".join(lines),
                    _money(measure["value"]),
                    escape(status),
                ]
            )
    body += "<section class='panel' id='bridges'><h2>Earnings and cash definitions</h2>" + table(
        ["Year end", "Measure", "Signed calculation inputs", "Result", "State"],
        bridges,
        "All calculations use native currency units; presentation divides by one million.",
    )
    for measure in latest["derived"].values():
        body += f"<p><strong>{escape(measure['label'])}.</strong> {escape(measure['definition'])}</p>"
    body += "</section><section class='panel' id='checks'><h2>Reconciliation exceptions</h2>"
    exceptions = [
        [
            escape(p["end"]),
            escape(c["target"]),
            escape(c["status"]),
            _money(c["difference"]),
            escape(", ".join(c["missing"])),
        ]
        for p in report["periods"]
        for c in p["reconciliations"]
        if c["status"] != "matched"
    ]
    body += (
        table(
            ["Period end", "Check", "State", "Difference", "Missing fields"],
            exceptions,
            "A difference is a question to resolve, not permission to force an adjustment.",
        )
        if exceptions
        else "<p>All supplied statement checks reconcile exactly.</p>"
    )
    body += "<p>Cash-flow amortization includes ‘other’ items; a difference from the two income-statement amortization rows "
    body += "requires review. The current conservative gate withholds derived measures for an unreconciled period. "
    body += "Reported facts stay visible. No difference is automatically called a source error or an avoidable cost.</p></section>"
    docs = {d.document_id: d for d in bundle.documents}
    rows = []
    for fact in sorted(bundle.facts, key=lambda f: (f.period.end, f.metric), reverse=True):
        source = docs[fact.document_id]
        link = f"{source.url}#page={fact.pdf_page}"
        rows.append(
            [
                escape(fact.metric),
                escape(fact.period.end.isoformat()),
                _money(fact.amount),
                f"{escape(fact.currency)} × {fact.unit_scale:,}",
                f"<a href='{escape(link, quote=True)}'>Filing page {escape(fact.printed_page)}</a>",
                escape(fact.source_row),
            ]
        )
    body += (
        "<section class='panel' id='evidence'><h2>Source facts and technical evidence</h2><details><summary>Inspect all extracted source rows</summary>"
        + table(
            ["Metric", "Period end", "Value, millions", "Original units", "Source", "Reported row"],
            rows,
            "Source row contains the filing's ordered comparative columns; no licensed vendor extract is used.",
        )
        + "</details>"
    )
    for doc in bundle.documents:
        body += f"<p><a href='{escape(str(doc.url), quote=True)}'>{escape(doc.title)}</a> · filed {doc.filed_on} · accession {escape(doc.accession)}</p><p class='muted'>Document SHA-256 <code>{doc.sha256}</code><br>Mapping SHA-256 <code>{doc.mapping_sha256}</code></p>"
    body += f"<p class='muted'>Analysis {escape(report['analysis_version'])} · Input SHA-256 <code>{report['input_sha256']}</code>. Independent financial review has not been performed.</p></section>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        + f"<title>{company} — public diligence baseline</title><style>{CSS}</style></head><body><a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'><a class='brand' href='#main'>Value Creation OS · Diligence</a><nav class='primary-nav' aria-label='Sections'><a class='nav-link' href='#history'>History</a><a class='nav-link' href='#bridges'>Definitions</a><a class='nav-link' href='#evidence'>Evidence</a></nav></div></header><main id='main' tabindex='-1' class='app-shell'>"
        + body
        + "</main></body></html>"
    )


def build_public_report(source: Path, output: Path) -> Path:
    bundle = FactBundle.model_validate_json(source.read_bytes())
    bundle.require_public()
    report = analyze_facts(bundle)
    html = render_baseline(bundle, report)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if source.resolve() in {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite the source fact bundle")
    # Validate and render before any filesystem mutation; private sources never create output.
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
