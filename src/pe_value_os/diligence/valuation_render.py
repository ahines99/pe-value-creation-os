"""A public, dated EV-to-equity exhibit with inspectable assumptions and source rows."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..research.render import table
from .balances import BalanceBundle
from .exhibit_style import exhibit_page
from .models import FactBundle
from .valuation import ValuationSpec, analyze_valuation


def millions(value: Any) -> str:
    return "Withheld" if value is None else f"{Decimal(str(value)) / 1000000:,.3f}"


def valuation_summary(report: dict[str, Any]) -> str:
    """Reuse the same calculated matrix in the executive memo and full exhibit."""
    body = (
        "<section class='panel' id='historical-valuation'><p class='eyebrow'>Historical sensitivity / USD millions</p>"
        "<h2>Enterprise value is not the equity claim</h2>"
        f"<p>Balance date {report['historical_date']}; information cutoff {report['information_cutoff']}. "
        "Later-filed evidence supports this historical exercise. It is not a current or contemporaneous valuation.</p>"
        f"<p>Calculated annual EBITDA: <strong>{millions(report['earnings']['value'])}</strong>. "
        f"Debt principal: <strong>{millions(report['debt_principal'])}</strong>; "
        f"debt carrying value net of issuance costs: <strong>{millions(report['debt_carrying_value'])}</strong>. "
        "Principal, rather than carrying value net of issuance costs, is deducted under the assumed cash settlement.</p>"
    )
    if report["blocked_by"]:
        body += "<p><strong>Valuation withheld:</strong> " + escape("; ".join(report["blocked_by"])) + "</p>"
    body += table(
        ["Assumed multiple", "Enterprise value"]
        + [escape(s["label"]) + " / equity sensitivity" for s in report["scenarios"]],
        [
            [escape(str(row["multiple"])) + "x", millions(row["enterprise_value"])]
            + [millions(s["rows"][i]["equity_sensitivity"]) for s in report["scenarios"]]
            for i, row in enumerate(report["scenarios"][0]["rows"])
        ],
        "Explicit analyst assumptions. Negative residuals are retained; they are funding shortfalls in this arithmetic, not negative share-price estimates.",
    )
    body += (
        f"<p>{escape(report['spec']['multiple_rationale'])}</p>"
        "<p><strong>Formula:</strong> EBITDA × assumed multiple + available cash + nonoperating assets − debt principal − selected lease claims − other claims − transaction costs.</p>"
        "<p>Historical company earnings and fictional operating improvements remain separate. No current equity value, share-price target or transaction proceeds are established.</p></section>"
    )
    return body


def render_valuation(report: dict[str, Any], json_name: str = "historical-valuation.json") -> str:
    body = (
        "<section class='hero'><div><p class='eyebrow'>Progress Software / Historical public research</p>"
        "<h1>From earnings to the equity claim</h1><p class='page-subtitle'>Reconcile the debt. Expose the assumptions.</p>"
        f"<p>{escape(report['limitation'])}</p></div><aside class='hero-aside'><span class='metric-label'>Historical anchor</span>"
        f"<strong class='metric-value'>{report['historical_date']}</strong><span class='metric-note'>USD millions throughout</span></aside></section>"
    )
    body += valuation_summary(report)
    body += "<section class='panel' id='assumptions'><h2>What each column assumes</h2><p>Zero-valued claims are explicit unverified assumptions. They are never inferred from missing evidence.</p>"
    for scenario in report["scenarios"]:
        body += f"<h3>{escape(scenario['label'])}</h3>"
        body += table(
            ["Input", "Assumed treatment", "Rationale"],
            [
                [
                    "Available reported cash",
                    f"{Decimal(scenario['available_cash_fraction']) * 100:g}%",
                    escape(scenario["cash_rationale"]),
                ],
                [
                    "Operating lease liabilities",
                    escape(scenario["lease_treatment"].replace("_", " ")),
                    escape(scenario["lease_rationale"]),
                ],
            ]
            + [
                [label, millions(scenario[key]["amount"]), escape(scenario[key]["rationale"])]
                for label, key in [
                    ("Nonoperating assets credited", "nonoperating_assets"),
                    ("Other claims deducted", "other_claims"),
                    ("Transaction costs deducted", "transaction_costs"),
                ]
            ],
            "All amounts are authored assumptions in USD millions; reported debt and cash are shown separately.",
        )
        body += "<details><summary>Inspect every bridge component</summary>"
        body += (
            table(
                [
                    "Multiple",
                    "EV",
                    "+ Cash",
                    "+ Assets",
                    "− Principal",
                    "− Leases",
                    "− Other claims",
                    "− Costs",
                    "Equity residual",
                ],
                [
                    [str(row["multiple"]) + "x"]
                    + [
                        millions(row.get(key))
                        for key in (
                            "enterprise_value",
                            "cash_added",
                            "nonoperating_assets_added",
                            "debt_principal_deducted",
                            "lease_claim_deducted",
                            "other_claims_deducted",
                            "transaction_costs_deducted",
                            "equity_sensitivity",
                        )
                    ]
                    for row in scenario["rows"]
                ],
                "Each row preserves the full enterprise-to-equity arithmetic in USD millions.",
            )
            + "</details>"
        )
    body += f"<p><strong>Convertible settlement assumption:</strong> {escape(report['spec']['settlement_rationale'])}</p></section>"
    body += "<section class='panel' id='evidence'><h2>Source and reconciliation trail</h2>"
    doc = report["balances"]["document"]
    body += f"<p><a href='{escape(doc['url'], quote=True)}'>Progress FY2025 Form 10-K</a>, filed {doc['filed_on']}. {len(report['balances']['facts'])} point-in-time facts retain original units, date columns and row labels. Cash is a reported balance; its availability is assumed.</p>"
    body += table(
        ["Reconciliation", "Status", "Difference, USD millions"],
        [
            [escape(c["target"].replace("_", " ")), escape(c["status"]), millions(c["difference"])]
            for c in report["reconciliations"]
        ],
        "A missing input, unexpected sign or mismatch withholds every dependent valuation row.",
    )
    body += "<details><summary>Inspect the reported balances</summary>"
    body += (
        table(
            ["Source row", "USD millions", "Date", "Source"],
            [
                [
                    escape(f["row_label"]),
                    millions(Decimal(f["reported_amount"]) * f["unit_scale"]),
                    f["as_of"],
                    f"<a href='{escape(doc['url'], quote=True)}#page={f['pdf_page']}'>PDF {f['pdf_page']}</a>",
                ]
                for f in report["balances"]["facts"]
            ],
            "Amounts as of November 30, 2025; original source tables report USD thousands.",
        )
        + "</details><details><summary>Inspect the annual earnings anchor</summary>"
    )
    sources = {d["document_id"]: d for d in report["source_documents"]}
    body += f"<p>{escape(report['earnings']['definition'])}</p>"
    body += (
        table(
            ["Source component", "Reported amount, USD millions", "Bridge sign", "Source"],
            [
                [
                    escape(f["row_label"]),
                    millions(Decimal(f["reported_amount"]) * f["unit_scale"]),
                    str(report["earnings"]["formula"][f["metric"]]),
                    f"<a href='{escape(sources[f['document_id']]['url'], quote=True)}#page={f['pdf_page']}'>PDF {f['pdf_page']}</a>",
                ]
                for f in report["earnings_facts"]
            ],
            "Apply each sign once; interest expense is reported as a negative income-statement amount.",
        )
        + "<p><a href='progress-baseline.html'>Open the complete earnings reconciliation and accounting scope exceptions</a>.</p></details></section>"
    )
    body += (
        "<section class='panel' id='limits'><h2>Evidence still required for an actual valuation</h2><ul>"
        + "".join(f"<li>{escape(item)}</li>" for item in report["spec"]["unresolved_items"])
        + "</ul>"
    )
    for event in report["subsequent_events"]:
        body += f"<p><strong>Subsequent event, {event['occurred_on']}:</strong> {escape(event['reported_summary'])} {escape(event['analytical_implication'])}</p>"
    body += f"<p><a href='{escape(json_name, quote=True)}' download>Download the complete valuation JSON</a> · <a href='decision-memo.html'>Return to the executive memo</a></p>"
    body += (
        "<details><summary>Inspect exact input fingerprints</summary>"
        + table(
            ["Input", "SHA-256"],
            [[key, f"<code>{report[key + '_sha256']}</code>"] for key in ("financial", "balances", "spec")],
            "Source facts and analyst assumptions have separate immutable fingerprints.",
        )
        + "</details></section>"
    )
    return exhibit_page(
        title="Progress Software — historical equity bridge",
        kind="Historical equity bridge",
        provenance="Public filings · authored assumptions",
        nav=[
            ("#historical-valuation", "Sensitivity"),
            ("#assumptions", "Assumptions"),
            ("#evidence", "Evidence"),
            ("#limits", "Limits"),
        ],
        nav_label="Valuation sections",
        body=body,
    )


def build_valuation_report(facts: Path, balances: Path, spec: Path, output: Path) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in (facts, balances, spec)} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("valuation must not overwrite an input")
    report = analyze_valuation(
        FactBundle.model_validate_json(facts.read_bytes()),
        BalanceBundle.model_validate_json(balances.read_bytes()),
        ValuationSpec.model_validate_json(spec.read_bytes()),
    )
    html = render_valuation(report, json_path.name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
