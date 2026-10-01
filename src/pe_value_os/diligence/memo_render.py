"""Self-contained executive memo, derived comparisons and a traceable technical appendix."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..research.render import table
from .balances import BalanceBundle
from .exhibit_style import exhibit_page
from .growth import GrowthContext
from .memo import DecisionBrief, assemble_memo
from .memo_review import MemoReviewContext
from .models import FactBundle
from .operating_sources_render import table as review_table
from .peers import PeerContext
from .scheduling import OperatingPlan
from .underwriting_models import read_underwriting
from .underwriting_render import render_allocation
from .valuation import ValuationSpec
from .valuation_render import valuation_summary

MEMO_CSS = """
.memo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}
.memo-grid>article{border-radius:var(--r-lg);background:var(--bg);min-width:0}
.memo-grid h3{font-size:14px;line-height:1.4;margin:0 0 10px}
.memo-grid p{font-size:13px;line-height:1.55;margin:0 0 8px;color:var(--text-2)}
.memo-grid p strong{color:var(--text)}
.memo-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}
.memo-facts>div{padding:16px 18px 18px;border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg);display:flex;flex-direction:column}
.memo-facts strong{font-size:var(--x-figure);font-weight:600;display:block;letter-spacing:-.025em;line-height:1.1;margin:4px 0 0}
.memo-facts .memo-note{margin-top:auto;padding-top:10px}
.memo-note{font-size:12px;color:var(--x-quiet)}
.waterfall-row{display:grid;align-items:center}.waterfall-track{position:relative}.waterfall-bar{position:absolute}.waterfall-zero{position:absolute}.waterfall-value{text-align:right}
@media(max-width:800px){.memo-grid,.memo-facts{grid-template-columns:minmax(0,1fr)}}
@media print{.memo-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.memo-grid article,.memo-choice{break-inside:avoid}.memo-facts strong{font-size:20pt}.topbar{display:none}}
"""


def amount(value: Any, scale: int = 1000, places: int = 1) -> str:
    return "Withheld" if value is None else f"{Decimal(str(value)) / scale:,.{places}f}"


def _scenario(option: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in option["analysis"]["scheduled_financials"]["scenarios"] if s["scenario_id"] == name)


def incremental_waterfall(year: dict[str, Any]) -> str:
    parts = [
        ("Gross pricing", Decimal(str(year["gross_price_benefit"]))),
        ("Revenue leakage", Decimal(str(year["revenue_leakage"]))),
        ("Variable cost", Decimal(str(year["variable_cost"]))),
        ("Vendor savings", Decimal(str(year["cost_removed"]))),
        ("Recurring costs", Decimal(str(year["recurring_cost"]))),
        ("Implementation", Decimal(str(year["implementation_expense"]))),
    ]
    cumulative = [Decimal(0)]
    for _, value in parts:
        cumulative.append(cumulative[-1] + value)
    if cumulative[-1] != Decimal(str(year["incremental_ebitda"])):
        raise ValueError("incremental earnings waterfall must reconcile exactly")
    low, high = min(cumulative), max(cumulative)
    width = max(high - low, Decimal(1))
    zero = (0 - low) / width * 100
    visual = (
        "<figure class='x-chart' aria-hidden='true'><div class='x-chart-head'><span class='x-chart-title'>Constructed year-one base EBITDA bridge · USD thousands</span>"
        "<span class='x-legend'><span style='--x-swatch:var(--chart-up)'>Increase</span><span style='--x-swatch:var(--chart-down)'>Decrease</span>"
        "<span style='--x-swatch:var(--chart-total)'>Net</span></span></div><div class='earnings-waterfall' aria-hidden='true'>"
    )
    rows = []
    for i, (label, value) in enumerate(parts):
        left = (min(cumulative[i], cumulative[i + 1]) - low) / width * 100
        size = abs(value) / width * 100
        color = "var(--chart-up)" if value >= 0 else "var(--chart-down)"
        visual += f"<div class='waterfall-row'><span>{escape(label)}</span><div class='waterfall-track'><span class='waterfall-zero' style='left:{zero:.3f}%'></span><span class='waterfall-bar' style='left:{left:.3f}%;width:{size:.3f}%;background:{color}'></span></div><span class='waterfall-value'>{amount(value)}</span></div>"
        rows.append([escape(label), amount(value, places=3), amount(cumulative[i + 1], places=3)])
    net = cumulative[-1]
    net_left = (min(Decimal(0), net) - low) / width * 100
    net_width = abs(net) / width * 100
    visual += f"<div class='waterfall-row'><strong>Net EBITDA</strong><div class='waterfall-track'><span class='waterfall-zero' style='left:{zero:.3f}%'></span><span class='waterfall-bar' style='left:{net_left:.3f}%;width:{net_width:.3f}%;background:var(--chart-total)'></span></div><strong class='waterfall-value'>{amount(net)}</strong></div></div></figure>"
    rows.append(["Incremental EBITDA", amount(cumulative[-1], places=3), "Reconciled"])
    return visual + review_table(
        ["Component", "Change, USD thousands", "Cumulative"],
        rows,
        "Constructed year-one base earnings bridge, starting at zero. This is not a bridge from Progress reported earnings to a company target. Collections and capex are excluded from EBITDA.",
        totals=(-1,),
    )


def source_challenge_summary(report: dict[str, Any]) -> str:
    review = report["source_review"]
    original = {o["option_id"]: o for o in report["constructed_options"]}
    preferred = next(o for o in review["options"] if o["option_id"] == report["brief"]["preferred_constructed_option"])
    base = _scenario(preferred, "base")
    body = ""
    if "interaction_policy" in review["latest_financials"]:
        body += render_allocation(review["latest_financials"])
    body += "<section class='panel' id='evidence-update'><p class='eyebrow'>Latest constructed evidence / Decision reopened</p><h2>Task order cannot substitute for a supported cost action.</h2>"
    body += f"<p><strong>{escape(review['recommendation'])}</strong></p><p>Authored exercise review {escape(str(review['exercise_effective_on']))}. The public research cutoff above remains unchanged; these future-dated operating records are fictional.</p>"
    body += review_table(
        ["Sequence", "Original base EBITDA", "Corrected base EBITDA", "Corrected cash", "Peak funding"],
        [
            [
                escape(o["label"]),
                amount(_scenario(original[o["option_id"]], "base")["year_one"]["incremental_ebitda"]),
                amount(_scenario(o, "base")["year_one"]["incremental_ebitda"]),
                amount(_scenario(o, "base")["year_one"]["pre_tax_cash_proxy"]),
                amount(_scenario(o, "base")["maximum_dated_funding_need"]),
            ]
            for o in review["options"]
        ],
        "USD thousands. Original and corrected columns use different evidence/assumptions. Within each column, only task sequencing varies; all implementation costs remain.",
    )
    body += f"<p>Each alternative keeps the latest operating assumptions, source records, resources, work packages and costs. Only task order and resulting dates change.</p><p>Latest stored-case review: <strong>{escape(review['review_state'].replace('_', ' '))}</strong>. That receipt does not approve the alternatives displayed here.</p>"
    body += "<h3>Why the previously preferred sequence no longer supports its commitment</h3>"
    body += incremental_waterfall(base["year_one"])
    body += review_table(
        ["Corrected service-first scenario", "Year-one EBITDA", "Year-one cash", "Day-100 cash", "Peak funding"],
        [
            [
                escape(s["scenario_id"].title()),
                amount(s["year_one"]["incremental_ebitda"]),
                amount(s["year_one"]["pre_tax_cash_proxy"]),
                amount(s["day_100"]["pre_tax_cash_proxy"]),
                amount(s["maximum_dated_funding_need"]),
            ]
            for s in preferred["analysis"]["scheduled_financials"]["scenarios"]
        ],
        "USD thousands. These scenarios are not probabilities. Capacity released without a spend action is not a saving; bounded source terms do not establish maintainable exit value.",
    )
    y = base["year_one"]
    body += f"<p><strong>Cash bridge:</strong> {amount(y['incremental_ebitda'])} EBITDA + {amount(y['operating_accrual_to_cash'])} accrual-to-cash + {amount(y['working_capital_cash'])} net collection timing + {amount(y['capex_cash'])} capex = {amount(y['pre_tax_cash_proxy'])} pre-tax cash, USD thousands. It omits tax, financing and other full-free-cash-flow requirements.</p>"
    body += "<p class='x-callout'><strong>Decision now:</strong> revise the intervention scope and cost commitments, or defer it. Verify contract rights and vendor-release evidence before requesting a new first-wave selection. No revised alternative is automatically selected.</p>"
    body += f"<details><summary>Inspect the latest case binding and review boundary</summary><div class='memo-body'><p>{escape(review['authority'])}</p><p>Revision <code>{escape(review['current_revision_id'])}</code> · hash <code>{escape(review['current_revision_sha256'])}</code></p><p>Review context <code>{escape(review['context_sha256'])}</code></p></div></details><p><a href='source-review.html'>Trace the source correction and unchanged accounting history</a></p></section>"
    return body


def render_memo(report: dict[str, Any], json_name: str = "decision-memo.json") -> str:
    brief = report["brief"]
    base = report["public_baseline"]
    growth = report["public_growth"]
    options = report["constructed_options"]
    preferred = next(o for o in options if o["option_id"] == brief["preferred_constructed_option"])
    review = report.get("source_review")
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
        f"<p>{escape(review['recommendation'] if review else brief['recommendation'])}</p></aside></section>"
        "<p class='layer-banner'>Public issuer research informs the diligence questions. The operating alternatives below use authored, fictional inputs; they are not Progress customer records or company forecasts.</p>"
    )
    if review:
        body += source_challenge_summary(report)
        if "lineage_review" in review["latest_financials"]:
            body += "<section class='panel'><h2>Preserve the decision history as work changes</h2><p>The latest case includes a pricing split, an explicit KPI target change and reading correction, and a later merge. Original sequence priorities follow the recorded task ancestry. Costs and frozen financial claims remain intact.</p><p><a href='lineage-review.html'>Inspect the ten-revision lifecycle, source ownership and KPI history</a>.</p></section>"
    body += "<section class='panel' id='thesis'><h2>Judgments that shape the next decision</h2><div class='memo-grid'>"
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
        body += f"<div><span class='metric-label'>{escape(label)}</span><strong>{amount(value, 1000000)}{'' if value is None else " <span class='x-unit'>USD m</span>"}</strong><span class='memo-note'>{escape(note)}</span></div>"
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
    body += table(
        ["Earnings bridge", "USD millions", "Source"], bridge, base["derived"]["ebitda"]["definition"], totals=(-1,)
    )
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
    body += "<p><a href='exit-review.html'>Review the constructed exit sensitivity and its separate operating-evidence limits</a>.</p>"
    body += (
        "<section class='panel' id='choices'><p class='eyebrow'>Original constructed alternatives / USD thousands</p>"
    )
    body += (
        "<h2>Original preference — reopened by the source challenge</h2><p>These earlier figures preserve the initial reasoning. They are not the current source-constrained forecast.</p><details><summary>Inspect the original sequence comparison and conditional preference</summary><div class='memo-body'>"
        if review
        else "<h2>Choose the sequence, then test its assumptions</h2>"
    )
    body += "<p>All alternatives retain the same scope, proposed resources, economic assumptions and dated costs. Only task priority changes. These are authored alternatives, not an optimization result.</p>"
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
        f"<div class='memo-choice'><h3>{'Original conditional preference — now reopened' if review else 'Conditional preference' if report['preference_status'] == 'conditional_research_preference' else 'Reopen blocked preference'}: {escape(preferred['label'])}</h3>"
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
        totals=(-1,),
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
    if review:
        body += "</div></details>"
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
    context_note = (
        "The packet includes the exact imported case history and recomputed source-constrained alternatives; the original comparisons preserve the prior reasoning."
        if review
        else "Original/current case history is a separate constructed walkthrough."
    )
    body += f"<section class='panel' id='technical'><h2>Technical evidence and review limits</h2><p>{escape(report['authority'])}</p><p><a href='{escape(json_name, quote=True)}' download>Download the complete JSON decision packet</a>. It preserves all option schedule analyses, monthly financials, assumptions, source references and input hashes. {context_note} This comparison does not create an approved revision.</p><details><summary>Inspect bound inputs and calculation lineage</summary><div class='memo-body'>"
    if review:
        body += f"<p>{escape(review['source_treatment'])}</p>"
    body += table(
        ["Input", "SHA-256"],
        [[escape(k), f"<code>{v}</code>"] for k, v in report["input_hashes"].items()],
        "A changed input invalidates the decision brief until explicitly revised.",
    )
    body += f"<p>Memo version {report['memo_version']} · Brief <code>{report['brief_sha256']}</code></p></div></details><p class='memo-sources'><a href='progress-baseline.html'>Public source appendix</a><a href='underwriting.html'>Original constructed underwriting</a><a href='operating-plan.html'>Original capacity proposal</a></p></section>"
    rendered = exhibit_page(
        title=f"{report['company']} — executive decision memo",
        kind="Executive decision memo",
        provenance="Public research · constructed exercise",
        nav=[
            ("#thesis", "Thesis"),
            ("#historical-valuation", "Valuation"),
            ("#choices", "Choices"),
            ("#next-decision", "Next decision"),
            ("#technical", "Evidence"),
        ],
        nav_label="Memo sections",
        body=body,
        extra_css=MEMO_CSS,
    )
    if report["memo_version"] in {"executive-decision-packet/6", "executive-decision-packet/7"}:
        for previous, current in (
            ("underwriting", "allocation-underwriting"),
            ("operating-plan", "allocation-operating-plan"),
            (
                "case-history",
                "allocation-lineage-review"
                if report["memo_version"] == "executive-decision-packet/7"
                else "allocation-review",
            ),
        ):
            rendered = rendered.replace(f"href='{previous}.html'", f"href='{current}.html'")
    return rendered


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
    case_review: Path | None = None,
) -> Path:
    inputs = [brief, facts, growth, peers, underwriting, plan, balances, valuation]
    if case_review is not None:
        inputs.append(case_review)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in inputs} & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("memo must not overwrite an input")
    report = assemble_memo(
        DecisionBrief.model_validate_json(brief.read_bytes()),
        FactBundle.model_validate_json(facts.read_bytes()),
        GrowthContext.model_validate_json(growth.read_bytes()),
        PeerContext.model_validate_json(peers.read_bytes()),
        read_underwriting(underwriting.read_bytes()),
        OperatingPlan.model_validate_json(plan.read_bytes()),
        BalanceBundle.model_validate_json(balances.read_bytes()),
        ValuationSpec.model_validate_json(valuation.read_bytes()),
        MemoReviewContext.from_export(json.loads(case_review.read_bytes())) if case_review is not None else None,
    )
    html = render_memo(report, json_path.name)
    # Complete public-source and exact-revision validation before writing either artifact.
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
