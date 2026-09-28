"""Executive source challenge with the same financial ledger behind every exhibit."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..api.presentation import CSS
from ..research.render import table as financial_table
from .operating_sources import OperatingSourceBook, source_forecast
from .scheduling import OperatingPlan
from .underwriting import UnderwritingCase


def money(value: Any) -> str:
    return f"{Decimal(str(value)):,.2f}"


def table(headers: list[str], rows: list[list[str]], caption: str) -> str:
    # Keep the explanation inside the viewport while the numeric table scrolls.
    # The region retains its descriptive accessible name from the shared helper.
    rendered = financial_table(headers, rows, caption)
    return f"<p class='muted'>{escape(caption)}</p>" + rendered.replace(
        f"<caption class='table-caption'>{escape(caption)}</caption>", ""
    )


def render_sources(report: dict[str, Any], download: str) -> str:
    base = next(s for s in report["scenarios"] if s["scenario_id"] == "base")
    reference = {s["scenario_id"]: s for s in report["reference_forecast"]["scenarios"]}
    book = report["source_book"]
    renewals = [d for d in base["decisions"] if d["kind"] == "renewal"]
    invoices = [d for d in base["decisions"] if d["kind"] == "invoice"]
    missed = sum((d["monthly_revenue"] for d in renewals if d["reason"] == "Notice deadline missed"), Decimal(0))
    eligible = [d for d in renewals if d["eligible"]]
    disputed = sum((d["disputed"] for d in invoices), Decimal(0))
    collection_scope = sum((d["eligible_balance"] for d in invoices if d["eligible"]), Decimal(0))
    first_spend = next((m["start"] for m in base["monthly"] if m["cost_removed"] > 0), None)
    decision = (
        "Rework the first wave: the base case has negative year-one EBITDA."
        if base["year_one"]["incremental_ebitda"] < 0
        else "Review the constrained forecast and unresolved evidence before any operating decision."
    )
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed operating records / Decision challenge</p>"
        "<h1>Source constraints can overturn the case.</h1>"
        f"<p class='page-subtitle'>{escape(report['company'])} · {escape(report['currency'])}</p>"
        f"<p>{len(book['renewals'])} authored contracts, a monthly service/vendor schedule and {len(book['invoices'])} opening invoices challenge the original assumptions. These are fictional records, not company operating data.</p>"
        "</div><aside class='hero-aside'><span class='metric-label'>Proposed research decision</span>"
        f"<p>{decision} This is an unapproved analytical alternative; it does not replace the frozen case.</p></aside></section><div class='metrics-grid'>"
    )
    for label, value, note in (
        ("Year-one EBITDA", base["year_one"]["incremental_ebitda"], "Base · after original implementation costs"),
        ("Year-one cash", base["year_one"]["pre_tax_cash_proxy"], "Pre-tax proxy · after collection reversal"),
        (
            "First 100 days: cash",
            base["day_100"]["pre_tax_cash_proxy"],
            "Temporary collections benefit remains separate",
        ),
        ("Peak funding need", base["maximum_dated_funding_need"], "Dated cash deficits · base assumptions"),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{money(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div><section class='panel' id='decision'><h2>What changed the decision</h2>"
    body += (
        table(
            ["Constraint", "Financial consequence", "Next evidence request"],
            [
                [
                    "Contract notice windows",
                    f"{money(missed)} monthly revenue excluded for missed notice",
                    "Verify notice rights and whether any earlier notice was actually authorized and served",
                ],
                [
                    "Rights, caps and bounded recognition terms",
                    f"{len(eligible)} of {len(renewals)} contracts meet the modeled conditions",
                    "Reconcile rights, concessions, retained units and revenue recognition by term",
                ],
                [
                    "Vendor minimum and release evidence",
                    f"First month with modeled spend reduction: {first_spend or 'Unavailable'}",
                    "Verify the vendor amendment and retained QA workload",
                ],
                [
                    f"{money(disputed)} of opening invoices disputed",
                    f"{money(collection_scope)} has an eligible acceleration window",
                    "Confirm collectibility, disputes and the counterfactual payment dates",
                ],
            ],
            "These are outcomes of the supplied constructed example, not findings about Progress. A changed source book recomputes the exhibits below.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='comparison'><h2>Keep the original forecast beside the challenge</h2>"
    body += (
        table(
            [
                "Scenario",
                "Existing scheduled EBITDA / year one",
                "Source-constrained EBITDA / year one",
                "Source-constrained cash / year one",
                "24-month cash",
            ],
            [
                [
                    escape(s["scenario_id"]),
                    money(reference[s["scenario_id"]]["year_one"]["incremental_ebitda"]),
                    money(s["year_one"]["incremental_ebitda"]),
                    money(s["year_one"]["pre_tax_cash_proxy"]),
                    money(s["total"]["pre_tax_cash_proxy"]),
                ]
                for s in report["scenarios"]
            ],
            "All original costs remain. Source controls cover only the authored population. Low/base/high are judgmental scenarios, not probabilities. No exit multiple is applied to expiring or unreviewed benefits.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='contracts'><h2>Contract rights and notice come before pricing credit</h2>"
    body += (
        table(
            ["Record", "Monthly revenue", "Renewal / term end", "Modeled notice / deadline", "Base disposition"],
            [
                [
                    escape(d["record_id"]),
                    money(d["monthly_revenue"]),
                    f"{d['renewal_on']} / {d['term_ends_on']}",
                    f"{d['notice_on']} / {d['notice_deadline']}",
                    escape(d["reason"]),
                ]
                for d in base["decisions"]
                if d["kind"] == "renewal"
            ],
            "Notice can occur only after the proposed acceptance gate and source cutoff. Missing rights/caps block pricing. No renewal is automatically rolled forward; cash from recognized revenue may settle after term expiry.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='service'><h2>Capacity is not a vendor saving</h2>"
    body += (
        table(
            ["Month", "Modeled net hours / full month", "Releasable spend cap", "Spend available from", "Disposition"],
            [
                [
                    str(d["month"]),
                    money(d.get("net_full_month_hours", 0)) if "net_full_month_hours" in d else "Unavailable",
                    money(d["monthly_cost_action_cap"]) if "monthly_cost_action_cap" in d else "Unavailable",
                    str(d.get("spend_release_from") or "Unavailable"),
                    escape(d["reason"]),
                ]
                for d in [d for d in base["decisions"] if d["kind"] == "service"][:7]
            ],
            "First seven months of the supplied case. Hours subtract QA and repeated-contact effects; coverage/resolution assumptions cap the authored evaluation evidence. Quality-failed or unevaluated queues cannot contribute. The financial ledger prorates the actual modeled activity window.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='invoices'><h2>Collect existing receivables without inventing earnings</h2>"
    body += (
        table(
            ["Invoice", "Open / disputed", "Undisputed balance", "Acceleration / original date", "Disposition"],
            [
                [
                    escape(d["record_id"]),
                    f"{money(d['open_balance'])} / {money(d['disputed'])}",
                    money(d["eligible_balance"]),
                    f"{d['accelerated_on']} / {d['counterfactual_on']}",
                    escape(d["reason"]),
                ]
                for d in base["decisions"]
                if d["kind"] == "invoice"
            ],
            "Credits and already-paid amounts are removed first. A missed payment window contributes nothing. Every positive acceleration has an equal negative reversal on its declared counterfactual date; EBITDA stays zero.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='sources'><h2>Source scope and reproducibility</h2>"
    body += f"<p>{escape(book['scope_description'])}</p><p>{escape(report['limitation'])}</p>"
    body += f"<p><a href='{escape(download, quote=True)}'>Download the complete source, decision and daily ledger JSON</a>. Read the <a href='operating-plan.html'>original proposed plan</a> and <a href='decision-memo.html'>executive memo</a>.</p>"
    body += "<details><summary>Monthly base-case financial bridge</summary>"
    body += (
        table(
            [
                "Month",
                "Pricing benefit",
                "Churn leakage",
                "Vendor cost removed",
                "EBITDA",
                "Receivables timing",
                "Cash proxy",
            ],
            [
                [
                    str(m["start"]),
                    money(m["gross_price_benefit"]),
                    money(m["revenue_leakage"]),
                    money(m["cost_removed"]),
                    money(m["incremental_ebitda"]),
                    money(m["working_capital_cash"]),
                    money(m["pre_tax_cash_proxy"]),
                ]
                for m in base["monthly"]
            ],
            "Shared Decimal ledger. EBITDA includes variable costs, recurring fees and implementation expense. Cash additionally reflects settlement timing and capex; taxes, financing and other working-capital accounts are omitted.",
        )
        + "</details>"
    )
    body += "<details><summary>Declared controls and exact input fingerprints</summary>"
    body += f"<p>Renewal monthly revenue control: {money(book['renewal_monthly_revenue_control'])}. Invoice open-balance control: {money(book['invoice_open_balance_control'])}. Service months provided: {len(book['service_months'])}; missing: {len(report['missing_service_months'])}.</p>"
    for label in ("book_sha256", "underwriting_sha256", "plan_sha256", "report_sha256"):
        body += f"<p>{escape(label)} <code>{escape(report[label])}</code></p>"
    body += "</details></section>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Operating source challenge — {escape(report['company'])}</title><style>{CSS}</style></head><body>"
        "<a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'>"
        "<a class='brand' href='#main'>Value Creation OS · Operating evidence</a><nav class='primary-nav' aria-label='Sections'>"
        "<a class='nav-link' href='#decision'>Decision</a><a class='nav-link' href='#contracts'>Contracts</a><a class='nav-link' href='#sources'>Evidence</a></nav></div></header>"
        f"<main class='app-shell' id='main' tabindex='-1'>{body}</main></body></html>"
    )


def build_sources_report(source: Path, underwriting: Path, plan: Path, output: Path) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in (source, underwriting, plan)} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("source report must not overwrite an input")
    book = OperatingSourceBook.model_validate_json(source.read_bytes())
    case = UnderwritingCase.model_validate_json(underwriting.read_bytes())
    proposed = OperatingPlan.model_validate_json(plan.read_bytes())
    report = source_forecast(book, case, proposed)
    html = render_sources(report, json_path.name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
