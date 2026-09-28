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
from .growth import GrowthContext, analyze_growth
from .growth_render import render_growth
from .models import FactBundle
from .peer_render import render_peers
from .peers import PeerContext, analyze_peers
from .quarterly import derive_quarters


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
        + "</div>"
    )
    sources = {d.document_id: d for d in bundle.documents}
    for event in bundle.events:
        doc = sources[event.document_id]
        body += (
            f"<section class='panel'><p class='eyebrow'>Business perimeter update · {event.occurred_on}</p><h2>{escape(event.title)}</h2>"
            f"<p>{escape(event.reported_summary)}</p><p><strong>Implication for this analysis:</strong> {escape(event.analytical_implication)}</p>"
            f"<p><a href='{escape(str(doc.url), quote=True)}'>{escape(doc.title)}</a> · {escape(event.source_locator)}</p></section>"
        )
    if "growth_analysis" in report:
        body += render_growth(bundle, report["growth_analysis"])
    if "peer_analysis" in report:
        body += render_peers(report["peer_analysis"])
    body += (
        "<section class='panel'><h2>What this case establishes</h2>"
        "<p>Reported financial periods, their source rows and explicit calculation bridges are reproducible "
        "without a vendor account. This is a public-company research case, not a client engagement. "
        "There are no customer records, operating interventions or independently validated savings in this baseline.</p>"
        "<p>Peer eligibility, remaining perimeter effects, contract economics, staffing capacity and implementation costs "
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
    interim = [p for p in report["periods"] if p["basis"] != "annual"]
    quarter_calculations = {
        (str(q["start"]), str(q["end"])): q for q in report.get("quarterly_derivations", {}).get("quarters", [])
    }
    if interim:
        interim_rows = []
        for period in sorted(interim, key=lambda p: (p["end"], p["basis"])):
            calculated = quarter_calculations.get((period["start"], period["end"]), {})
            measures = calculated.get("measures") or period["derived"]
            method = "Reported period inputs"
            if calculated:
                method = (
                    "Quarter earnings + YTD-minus-prior cash/D&A"
                    if calculated["status"] == "matched"
                    else calculated["reason"]
                )
            interim_rows.append(
                [
                    escape(period["start"] + " to " + period["end"]),
                    escape(period["basis"].replace("_", " ")),
                    escape(period["currency"]),
                    _money(period["reported"]["revenue"]["value"]),
                    _money(period["reported"]["operating_income"]["value"]),
                    _money(measures["ebitda"]["value"]),
                    _money(measures["cfo_less_ppe"]["value"]),
                    escape(method),
                ]
            )
        body += (
            "<section class='panel' id='interim'><h2>Interim financial update</h2>"
            + table(
                [
                    "Period",
                    "Basis",
                    "Currency",
                    "Reported revenue",
                    "Reported operating income",
                    "Calculated EBITDA",
                    "CFO less PP&E",
                    "Calculation inputs",
                ],
                interim_rows,
                "Amounts in millions of each period's currency. Discrete quarters and cumulative YTD periods are separate; none is annualized or added to an overlapping period.",
            )
            + "<p>Review dated business-perimeter updates alongside these historical periods before assessing the current business.</p></section>"
        )
        derivation_rows = []
        mix_rows = []
        for period in sorted(interim, key=lambda p: p["end"]):
            reported = period["reported"]
            if (
                period["basis"] == "discrete_quarter"
                and {"software_license_revenue", "maintenance_saas_services_revenue"} <= reported.keys()
            ):
                mix_rows.append(
                    [
                        escape(period["end"]),
                        escape(period["currency"]),
                        _money(reported["software_license_revenue"]["value"]),
                        _money(reported["maintenance_saas_services_revenue"]["value"]),
                    ]
                )
        if mix_rows:
            body += (
                "<section class='panel'><h2>Revenue mix: reported categories</h2>"
                + table(
                    ["Quarter end", "Currency", "Software licenses", "Maintenance, SaaS and professional services"],
                    mix_rows,
                    "Amounts in millions. The combined service category is not a separately reported SaaS ARR series.",
                )
                + "<p>These categories constrain peer comparisons and commercial hypotheses. Contract duration, channel economics, renewal eligibility and acquired-company contributions still require separate diligence.</p></section>"
            )
        for quarter in quarter_calculations.values():
            for metric, component in quarter["components"].items():
                derivation_rows.append(
                    [
                        str(quarter["start"]) + " to " + str(quarter["end"]),
                        escape(metric.replace("_", " ")),
                        _money(component["value"]),
                        escape(component["status"]),
                        "<br>".join(f"<code>{escape(i)}</code>" for i in component["evidence_ids"]),
                    ]
                )
        body += (
            "<section class='panel'><h2>Quarter derivation and comparability</h2><p>Before subtracting prior-period amounts from YTD cash flow, twelve income-statement checks must reproduce the separately reported quarter. A mismatch blocks the derivation. Arithmetic agreement alone does not certify the business perimeter or absence of reclassifications.</p><details><summary>Inspect calculated quarterly components and input fact IDs</summary>"
            + table(
                ["Quarter", "Component", "Calculated amount", "State", "Source fact IDs (YTD minus prior)"],
                derivation_rows,
                "These are calculations with two-source lineage, not reported quarterly cash-flow rows.",
            )
            + "</details></section>"
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
    resolved_amort_periods = {
        key
        for key, q in quarter_calculations.items()
        if q.get("components", {}).get("intangible_amortization", {}).get("status") == "available"
    }
    exceptions = [
        [
            escape(f"{p['start']} to {p['end']} · {p['basis']}"),
            escape(c["target"].replace("_", " ")),
            escape(c["status"]),
            _money(c["difference"]),
            escape(", ".join(c["missing"])),
        ]
        for p in report["periods"]
        for c in p["reconciliations"]
        if c["status"] != "matched"
        and not (
            c["target"] == "intangible_amortization"
            and c["status"] == "unavailable"
            and (p["start"], p["end"]) in resolved_amort_periods
        )
    ]
    for quarter in quarter_calculations.values():
        unresolved = sorted(
            {
                reason
                for measure in quarter.get("measures", {}).values()
                for reason in (*measure["missing"], *measure["blocked_by"])
            }
            - {"intangible_amortization", "cross_filing_comparability"}
        )
        if unresolved:
            exceptions.append(
                [
                    str(quarter["start"]) + " to " + str(quarter["end"]),
                    "Calculated quarter measure inputs",
                    "review required",
                    "",
                    escape(", ".join(unresolved).replace("_", " ")),
                ]
            )
        for check in quarter["checks"]:
            if check["status"] != "matched":
                exceptions.append(
                    [
                        str(quarter["start"]) + " to " + str(quarter["end"]) + " · discrete quarter",
                        "YTD − prior − quarter: " + escape(check["metric"]),
                        escape(check["status"]),
                        _money(check["difference"]),
                        "",
                    ]
                )
        if quarter.get("amortization_difference") not in (None, 0):
            exceptions.append(
                [
                    str(quarter["start"]) + " to " + str(quarter["end"]) + " · discrete quarter",
                    "Calculated quarterly intangible amortization",
                    "definition review",
                    _money(quarter["amortization_difference"]),
                    "",
                ]
            )
    body += (
        table(
            ["Period and basis", "Check", "State", "Difference", "Missing fields"],
            exceptions,
            "A difference is a question to resolve, not permission to force an adjustment.",
        )
        if exceptions
        else "<p>All supplied statement checks reconcile exactly.</p>"
    )
    body += "<p>Cash-flow amortization includes ‘other’ items; a difference from the two income-statement amortization rows "
    body += "requires review. Dependent earnings measures are withheld; independently supported cash measures remain available. "
    body += "Reported facts stay visible. No difference is automatically called a source error or an avoidable cost.</p></section>"
    docs = {d.document_id: d for d in bundle.documents}
    rows = []
    for fact in sorted(bundle.facts, key=lambda f: (f.period.end, f.metric), reverse=True):
        source = docs[fact.document_id]
        link = f"{source.url}#page={fact.pdf_page}"
        rows.append(
            [
                escape(fact.metric),
                escape(f"{fact.period.start} to {fact.period.end} · {fact.period.basis}"),
                _money(fact.amount),
                f"{escape(fact.currency)} × {fact.unit_scale:,}",
                f"<a href='{escape(link, quote=True)}'>Filing page {escape(fact.printed_page)}</a>",
                escape(fact.source_row),
            ]
        )
    body += (
        "<section class='panel' id='evidence'><h2>Source facts and technical evidence</h2><details><summary>Inspect all extracted source rows</summary>"
        + table(
            ["Metric", "Period and basis", "Value, millions", "Original units", "Source", "Reported row"],
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


def build_public_report(
    source: Path, output: Path, growth_source: Path | None = None, peer_source: Path | None = None
) -> Path:
    bundle = FactBundle.model_validate_json(source.read_bytes())
    bundle.require_public()
    report = analyze_facts(bundle)
    report["quarterly_derivations"] = derive_quarters(bundle)
    report["context_events"] = [e.model_dump(mode="json") for e in bundle.events]
    if growth_source is not None:
        context = GrowthContext.model_validate_json(growth_source.read_bytes())
        report["growth_analysis"] = analyze_growth(bundle, context)
    if peer_source is not None:
        peer_context = PeerContext.model_validate_json(peer_source.read_bytes())
        report["peer_analysis"] = analyze_peers(bundle, peer_context)
    html = render_baseline(bundle, report)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    inputs = {source.resolve()} | ({growth_source.resolve()} if growth_source is not None else set())
    if peer_source is not None:
        inputs.add(peer_source.resolve())
    if inputs & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite the source fact bundle")
    # Validate and render before any filesystem mutation; private sources never create output.
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
