"""Self-contained executive memo, derived comparisons and a traceable technical appendix."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..api.presentation import CSS
from ..research.render import table
from .balances import BalanceBundle
from .growth import GrowthContext
from .memo import DecisionBrief, assemble_memo
from .models import FactBundle
from .peers import PeerContext
from .scheduling import OperatingPlan
from .underwriting import UnderwritingCase
from .valuation import ValuationSpec
from .valuation_render import valuation_summary

MEMO_CSS = """
.primary-nav{flex-wrap:wrap}
.memo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.memo-grid>article{border-top:3px solid var(--teal);padding:18px;background:#fafbf8;min-width:0}
.memo-grid h3{font-size:18px;line-height:1.4;margin-bottom:14px}
.memo-grid p{font-size:13px;line-height:1.7;margin-bottom:12px}
.layer-banner{padding:15px 20px;border-left:4px solid var(--copper);background:#f3eee5;margin:20px 0}
.memo-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:20px 0}
.memo-facts>div{padding:22px;border:1px solid var(--line);border-radius:8px;background:white}
.memo-facts strong{font-size:30px;display:block;letter-spacing:-.035em}
.memo-choice{padding:22px;background:#edf4ef;border:1px solid #c7ddce;border-radius:8px;margin:20px 0}
.memo-choice h3{margin-bottom:12px}.memo-note{font-size:12px;color:var(--muted)}
.memo-sources a{display:inline-block;margin:5px 12px 5px 0}.memo-body{padding:20px}
@media(max-width:800px){.memo-grid,.memo-facts{grid-template-columns:minmax(0,1fr)}}
@media print{.memo-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.memo-grid article,.memo-choice{break-inside:avoid}.memo-facts strong{font-size:20pt}.topbar{display:none}}
"""


def amount(value: Any, scale: int = 1000, places: int = 1) -> str:
    return "Withheld" if value is None else f"{Decimal(str(value)) / scale:,.{places}f}"


def _scenario(option: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in option["analysis"]["scheduled_financials"]["scenarios"] if s["scenario_id"] == name)


def render_memo(report: dict[str, Any], json_name: str = "decision-memo.json") -> str:
    brief = report["brief"]
    base = report["public_baseline"]
    growth = report["public_growth"]
    options = report["constructed_options"]
    preferred = next(o for o in options if o["option_id"] == brief["preferred_constructed_option"])
    docs = {d["document_id"]: d for d in report["source_documents"]}

    def source_link(fact_id: str) -> str:
        fact = report["source_facts"][fact_id]
        doc = docs[fact["document_id"]]
        return f"<a href='{escape(doc['url'], quote=True)}#page={fact['pdf_page']}'>Filing PDF {fact['pdf_page']}</a>"

    body = (
        "<section class='hero'><div><p class='eyebrow'>Executive decision memo / Public research</p>"
        f"<h1>{escape(report['company'])}</h1><p class='page-subtitle'>Advance the evidence. Hold the value commitment.</p>"
        f"<p>Information cutoff {report['as_of']} · Historical anchor {base['end']}</p></div>"
        "<aside class='hero-aside'><span class='metric-label'>Research recommendation</span>"
        f"<p>{escape(brief['recommendation'])}</p></aside></section>"
        "<p class='layer-banner'>Public issuer research informs the diligence questions. The operating alternatives below use authored, fictional inputs; they are not Progress customer records or company forecasts.</p>"
        "<section class='panel' id='thesis'><h2>Judgments that shape the next decision</h2><div class='memo-grid'>"
    )
    for point in brief["thesis"]:
        body += (
            f"<article><h3>{escape(point['conclusion'])}</h3><p><strong>Counterargument:</strong> {escape(point['counterargument'])}</p>"
            f"<p><strong>Next evidence:</strong> {escape(point['next_test'])}</p>"
            f"<p class='memo-note'>Evidence: {escape(', '.join(point['evidence_ids']))}. <a href='progress-baseline.html#research-decisions'>Inspect research decisions</a></p></article>"
        )
    body += "</div></section><section class='panel' id='economics'><p class='eyebrow'>Public financial baseline / USD millions</p><h2>What the accounts establish</h2><div class='memo-facts'>"
    for label, value, note in [
        ("Reported revenue", base["reported"]["revenue"]["value"], "US GAAP, annual"),
        ("Calculated EBITDA", base["derived"]["ebitda"]["value"], "Defined earnings bridge; not issuer-adjusted"),
        (
            "CFO less PP&E purchases",
            base["derived"]["cfo_less_ppe"]["value"],
            "Historical cash measure; not initiative savings",
        ),
    ]:
        body += f"<div><span class='metric-label'>{escape(label)}</span><strong>{amount(value, 1000000)}</strong><span class='memo-note'>{escape(note)}</span></div>"
    body += "</div>"
    interim = [p for p in report["public_financials"]["periods"] if p["basis"] != "annual"]
    if interim:
        last_end = max(p["end"] for p in interim)
        years = {int(last_end[:4]), int(last_end[:4]) - 1}
        selected = [p for p in interim if p["end"][5:] == last_end[5:] and int(p["end"][:4]) in years]
        body += table(
            ["Interim period", "Basis", "Revenue, USD millions", "Operating income, USD millions"],
            [
                [
                    escape(p["start"] + " to " + p["end"]),
                    escape(p["basis"].replace("_", " ")),
                    amount(p["reported"].get("revenue", {}).get("value"), 1000000, 3)
                    + (" · " + source_link(p["reported"]["revenue"]["fact_id"]) if "revenue" in p["reported"] else ""),
                    amount(p["reported"].get("operating_income", {}).get("value"), 1000000, 3),
                ]
                for p in selected
            ],
            "Latest available interim periods and their prior-year comparatives. Quarter and year-to-date amounts are separate; no annualization or organic-growth inference.",
        )
    body += (
        "<h3>Annual acquisition contribution bridge</h3>"
        + table(
            ["Growth bridge", "USD millions", "Interpretation"],
            [
                [
                    "Reported revenue change",
                    amount(growth["reported_change"], 1000000),
                    "Change in consolidated annual revenue",
                ],
                [
                    "Change in ShareFile contribution",
                    amount(growth["acquired_change"], 1000000),
                    "Approximate disclosed amounts; acquisition timing matters",
                ],
                [
                    "Non-ShareFile residual change",
                    amount(growth["residual_change"], 1000000),
                    "Not organic growth; currency, other acquisitions, mix and timing remain",
                ],
            ],
            "Approximate contribution bridge; source precision and the full revenue mix are retained in the public baseline.",
        )
        + "<p>The narrower peer cohorts cannot support a displayed median. Broad reported-margin context does not establish an avoidable cost pool. "
        "<a href='progress-baseline.html#peers'>Inspect the eligibility and exclusions</a>.</p>"
    )
    for event in report["public_financials"].get("context_events", []):
        doc = docs[event["document_id"]]
        body += f"<p><strong>Perimeter update:</strong> {escape(event['reported_summary'])} {escape(event['analytical_implication'])} <a href='{escape(doc['url'], quote=True)}'>Source filing</a>.</p>"
    body += "<details><summary>Reconcile EBITDA and inspect the adjustment register</summary><div class='memo-body'>"
    bridge = []
    for metric, sign, label in [
        ("net_income", 1, "Net income"),
        ("income_tax_expense", 1, "Tax provision"),
        ("interest_expense", -1, "Interest expense added back"),
        ("ppe_depreciation", 1, "PP&E depreciation"),
        ("intangible_amortization", 1, "Acquired intangible amortization"),
    ]:
        fact = base["reported"].get(metric)
        bridge.append(
            [
                label,
                amount(None if fact is None else Decimal(str(fact["value"])) * sign, 1000000, 3),
                source_link(fact["fact_id"]) if fact else "Missing source",
            ]
        )
    bridge.append(
        [
            "Calculated EBITDA",
            amount(base["derived"]["ebitda"]["value"], 1000000, 3),
            "Sum only when the defined reconciliation checks pass",
        ]
    )
    body += table(["Earnings bridge", "USD millions", "Source"], bridge, base["derived"]["ebitda"]["definition"])
    body += table(
        ["Item / period", "Reported USD millions", "Treatment", "Evidence needed"],
        [
            [
                escape(a["metric"].replace("_", " ") + " / " + a["period"]["end"]) + " · " + source_link(a["fact_id"]),
                amount(a["reported_amount"], 1000000, 3),
                escape(a["disposition"].replace("_", " ") + ": " + a["rationale"]),
                escape(a["evidence_needed"]),
            ]
            for a in report["adjustment_review"]
        ],
        "No incremental accounting addback is accepted. A register of review issues is not a normalized-earnings opinion.",
    )
    body += "<p>Normalized EBITDA remains unavailable. Earlier-year amortization scope differences remain explicit; this memo does not force comparability or replace the original facts.</p></div></details></section>"
    body += valuation_summary(report["historical_valuation"])
    body += "<p><a href='historical-valuation.html'>Inspect the historical equity bridge, all assumptions and source rows</a>.</p>"
    body += "<section class='panel' id='choices'><p class='eyebrow'>Constructed operating exercise / USD thousands</p><h2>Choose the sequence, then test its assumptions</h2><p>All alternatives retain the same scope, proposed resources, economic assumptions and dated costs. Only task priority changes. These are authored alternatives, not an optimization result.</p>"
    rows = []
    for option in options:
        s = _scenario(option, "base")
        rows.append(
            [
                escape(option["label"]),
                "Feasible under proposed capacity"
                if option["feasible"]
                else "Blocked: " + escape(", ".join(option["blocked_tasks"])),
                amount(s["year_one"]["incremental_ebitda"]),
                amount(s["year_one"]["pre_tax_cash_proxy"]),
                amount(s["maximum_dated_funding_need"]),
            ]
        )
    body += table(
        ["Sequence", "Capacity result", "Year-one EBITDA", "Year-one cash proxy", "Peak funding need"],
        rows,
        "Same committed costs and scope; funding is measured across the full 24-month modeled horizon. No actual assignments or approvals.",
    )
    body += (
        f"<div class='memo-choice'><h3>{'Conditional preference' if report['preference_status'] == 'conditional_research_preference' else 'Reopen blocked preference'}: {escape(preferred['label'])}</h3>"
        f"<p>{escape(brief['conditional_choice_reason'])}</p><ul>"
        + "".join(f"<li>{escape(t)}</li>" for t in brief["reopen_choice_if"])
        + "</ul></div>"
    )
    rows = []
    for scenario in preferred["analysis"]["scheduled_financials"]["scenarios"]:
        rows.append(
            [
                escape(scenario["scenario_id"].title()),
                amount(scenario["year_one"]["incremental_ebitda"]),
                amount(scenario["year_one"]["pre_tax_cash_proxy"]),
                amount(scenario["day_100"]["pre_tax_cash_proxy"]),
                amount(scenario["maximum_dated_funding_need"]),
            ]
        )
    body += table(
        [
            "Preferred option scenario",
            "Year-one EBITDA",
            "Year-one cash proxy",
            "Day-100 cash proxy",
            "Peak funding need",
        ],
        rows,
        "The downside remains adverse; this is a conditional scenario range, not a probability-weighted forecast.",
    )
    s = _scenario(preferred, "base")
    body += (
        f"<p><strong>Cash challenge:</strong> the base day-100 cash figure includes {amount(s['day_100']['working_capital_cash'])} thousand of temporary receivables acceleration. It reverses on the original collection date and creates no EBITDA. "
        "Cash also reflects operating settlement timing and capital purchases; it is a partial pre-tax proxy.</p>"
        "<details><summary>Inspect the earnings-to-cash bridge and incremental valuation sensitivity</summary><div class='memo-body'>"
    )
    y = s["year_one"]
    body += table(
        ["Year-one base bridge", "USD thousands"],
        [
            [label, amount(y[key])]
            for label, key in [
                ("Incremental EBITDA", "incremental_ebitda"),
                ("Operating accrual-to-cash adjustment", "operating_accrual_to_cash"),
                ("Existing receivables timing, net over year", "working_capital_cash"),
                ("Capital purchases", "capex_cash"),
                ("Pre-tax cash proxy", "pre_tax_cash_proxy"),
            ]
        ],
        "EBITDA + operating accrual-to-cash + working-capital timing + capex = the modeled cash proxy.",
    )
    body += table(
        ["Assumed multiple", "Incremental EV, USD thousands"],
        [[escape(str(v["multiple"])) + "×", amount(v["incremental_ev_sensitivity"])] for v in s["valuation"]],
        preferred["analysis"]["scheduled_financials"]["multiple_rationale"],
    )
    body += f"<p>{escape(report['valuation_limit'])}</p></div></details>"
    for option in options:
        body += f"<details><summary>{escape(option['label'])}: schedule, dependencies and challenge</summary><div class='memo-body'><p>{escape(option['challenge'])}</p>"
        body += table(
            ["Package / proposed owner", "Start", "Finish", "Acceptance evidence"],
            [
                [
                    escape(t["title"] + " / " + t["accountable_resource"]),
                    escape(str(t["scheduled_start"] or "Blocked")),
                    escape(str(t["scheduled_finish"] or "Blocked")),
                    escape(t["acceptance_evidence"]),
                ]
                for t in option["analysis"]["tasks"]
            ],
            "Dates reflect conditional scheduling; a scheduled gate is not an accepted deliverable.",
        )
        body += f"<p class='memo-note'>Schedule report <code>{option['analysis']['report_sha256']}</code> · financial calculation <code>{option['analysis']['scheduled_financials']['calculation_sha256']}</code></p></div></details>"
    body += "</section><section class='panel' id='next-decision'><h2>Next decision and evidence request</h2><p>Authorize a bounded data-discovery exercise only when an actual sponsor and data owner exist. No operating intervention is authorized by this memo.</p>"
    body += table(
        ["Decision gate", "Required evidence", "Who must validate"],
        [
            [
                "Baseline and scope",
                "Reconciled monthly P&L, revenue perimeter, account/contract population and source manifest",
                "Company finance/data owner",
            ],
            [
                "Pricing eligibility",
                "Notice periods, caps, concessions, channel rights and retained-customer economics",
                "Commercial owner and finance reviewer",
            ],
            [
                "Service cost action",
                "Vendor commitment or other verified spend change; quality evaluation and rollback criteria",
                "Service owner and finance reviewer",
            ],
            [
                "Collections timing",
                "Aged ledger, disputes, credits, original payment counterfactual and approved communications",
                "Controller and operator",
            ],
            [
                "First-wave feasibility",
                "Named operators, net weekly change capacity, exact-version decision and acceptance evidence",
                "Sponsor and accountable operators",
            ],
            [
                "Realization",
                "Observed accounting periods, baseline/counterfactual comparison, costs, attribution and unassigned residual",
                "Finance reviewer and sponsor",
            ],
        ],
        "Current status: no sponsor or authorized operating records; the pilot package is prepared, not performed.",
    )
    body += "<p><a href='../pilot/permissioned/README.md'>Pilot preparation package</a> · <a href='case-history.html'>Original/current constructed revision history</a></p></section>"
    body += f"<section class='panel' id='technical'><h2>Technical evidence and review limits</h2><p>{escape(report['authority'])}</p><p><a href='{escape(json_name, quote=True)}' download>Download the complete JSON decision packet</a>. It preserves all option schedule analyses, monthly financials, assumptions, source references and input hashes. Original/current case history is a separate constructed walkthrough; this conditional option comparison does not create an approved revision.</p><details><summary>Inspect bound inputs and calculation lineage</summary><div class='memo-body'>"
    body += table(
        ["Input", "SHA-256"],
        [[escape(k), f"<code>{v}</code>"] for k, v in report["input_hashes"].items()],
        "A changed input invalidates the decision brief until explicitly revised.",
    )
    body += f"<p>Memo version {report['memo_version']} · Brief <code>{report['brief_sha256']}</code></p></div></details><p class='memo-sources'><a href='progress-baseline.html'>Public source appendix</a><a href='underwriting.html'>Original constructed underwriting</a><a href='operating-plan.html'>Original capacity proposal</a></p></section>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(report['company'])} — executive decision memo</title><style>{CSS}{MEMO_CSS}</style></head><body>"
        "<a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'><a class='brand' href='../index.html'>Value Creation OS · Diligence</a><nav class='primary-nav' aria-label='Memo sections'><a class='nav-link' href='#thesis'>Thesis</a><a class='nav-link' href='#historical-valuation'>Valuation</a><a class='nav-link' href='#choices'>Choices</a><a class='nav-link' href='#next-decision'>Next decision</a><a class='nav-link' href='#technical'>Evidence</a></nav></div></header><main id='main' tabindex='-1' class='app-shell'>"
        + body
        + "</main></body></html>"
    )


def build_decision_memo(
    brief: Path,
    facts: Path,
    growth: Path,
    peers: Path,
    underwriting: Path,
    plan: Path,
    balances: Path,
    valuation: Path,
    output: Path,
) -> Path:
    inputs = [brief, facts, growth, peers, underwriting, plan, balances, valuation]
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in inputs} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("memo must not overwrite an input")
    report = assemble_memo(
        DecisionBrief.model_validate_json(brief.read_bytes()),
        FactBundle.model_validate_json(facts.read_bytes()),
        GrowthContext.model_validate_json(growth.read_bytes()),
        PeerContext.model_validate_json(peers.read_bytes()),
        UnderwritingCase.model_validate_json(underwriting.read_bytes()),
        OperatingPlan.model_validate_json(plan.read_bytes()),
        BalanceBundle.model_validate_json(balances.read_bytes()),
        ValuationSpec.model_validate_json(valuation.read_bytes()),
    )
    html = render_memo(report, json_path.name)
    # Complete public-source and exact-revision validation before writing either artifact.
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
