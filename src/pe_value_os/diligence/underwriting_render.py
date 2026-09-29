"""Executive exhibits for a constructed incremental model, with inspectable assumptions."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..api.presentation import CSS
from ..research.render import table
from .interactions import InteractionCase
from .underwriting import evaluate
from .underwriting_models import UnderwritingModel, read_underwriting


def amount(value: Any) -> str:
    return f"{Decimal(str(value)):,.0f}"


def render_allocation(report: dict[str, Any]) -> str:
    """Show effective scope beside the unchanged authored selection and rules."""
    policy = report["interaction_policy"]
    basis = report["selection_basis"]
    base = next(s for s in report["scenarios"] if s["scenario_id"] == "base")
    rules = {p["pool_id"]: p for p in policy["pools"]}
    body = (
        "<section class='panel' id='allocation'><h2>One economic pool, explicit choices</h2>"
        f"<p><strong>Calculation selection:</strong> {escape(basis['mode'].replace('_', ' '))}. "
        f"{escape('; '.join(basis['effective_selected_initiatives']) or 'None')}.</p>"
        f"<p><strong>Recorded selection:</strong> {escape('; '.join(basis['recorded_selected_initiatives']) or 'None')}. "
        f"{escape(policy['selection_rationale'])}</p><p>{escape(basis['authority'])}</p>"
    )
    body += table(
        ["Economic pool / rule", "Member", "Population share", "Calculation scope", "Owner / rationale / challenge"],
        [
            [
                escape(pool["pool_id"] + " / " + pool["mode"]),
                escape(member["initiative_id"]),
                f"{Decimal(str(member['population_share'])):.1%}",
                "Selected; benefit blocked"
                if member["initiative_id"] in pool["blocked_members"]
                else "Selected"
                if member["selected"]
                else "Excluded",
                "<br>".join(escape(rules[pool["pool_id"]][key]) for key in ("owner", "rationale", "invalidated_by")),
            ]
            for pool in base["interaction"]["pools"]
            for member in pool["members"]
        ],
        "Partition shares apply before rates, churn and spend caps. Exclusive alternatives each describe the full pool; at most one is selected. Unselected, unassigned and blocked exposure is never redistributed.",
    )
    body += "<p>Shares describe authored population scope. They are not probabilities or attribution of realized earnings.</p>"
    for rule in policy["cost_allocations"]:
        body += (
            f"<details><summary>Cost explanation: {escape(rule['cost_id'])}</summary>"
            f"<p>{escape(rule['owner'])}: {escape(rule['rationale'])} Challenge: {escape(rule['invalidated_by'])}</p>"
            + table(
                ["Date", "Owner", "Component", "Allocated amount"],
                [
                    [
                        escape(str(e["day"])),
                        escape(e["initiative_id"]),
                        escape(e["component"]),
                        f"{Decimal(str(e['amount'])):,.2f}",
                    ]
                    for e in base["interaction"]["cost_allocation_entries"]
                    if e["reference"] == rule["cost_id"]
                ],
                "Each cost posting is explained once across owners and any shared remainder. Retained commitments are not canceled by exclusion; this explanation does not alter case totals.",
            )
            + "</details>"
        )
    return body + "</section>"


def render_underwriting(case: UnderwritingModel, report: dict[str, Any]) -> str:
    case.require_public()
    scenarios = report["scenarios"]
    base = next(s for s in scenarios if s["scenario_id"] == "base")
    selected_titles = [d["title"] for d in base["drivers"] if d["initiative_id"] in report["selected_initiatives"]]
    body = (
        "<section class='hero'><div><p class='eyebrow'>Constructed operating exercise / Underwriting</p>"
        f"<h1>Separate earnings from cash.</h1><p class='page-subtitle'>{escape(case.company)} · {escape(case.currency)} · 24-month scenario</p>"
        "<p>Analyst-authored operating assumptions. No actual Progress contracts, service records, staffing actions or receivables are represented.</p>"
        "</div><aside class='hero-aside'><span class='metric-label'>Decision boundary</span>"
        "<p>Challenge the mechanism, costs and feasibility before selecting a first wave. These calculations do not authorize execution.</p></aside></section>"
        "<div class='metrics-grid'>"
    )
    for label, value, note in (
        (
            "Year-one EBITDA change",
            base["year_one"]["incremental_ebitda"],
            "Base scenario · after implementation expense",
        ),
        ("Year-one cash proxy", base["year_one"]["pre_tax_cash_proxy"], "Pre-tax · includes explicit capex and timing"),
        (
            "First 100 days: cash",
            base["day_100"]["pre_tax_cash_proxy"],
            "Exact dated ledger · includes temporary collection timing",
        ),
        ("Funding need", base["maximum_dated_funding_need"], "Base scenario · peak on modeled cash dates"),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{amount(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += (
        "</div><section class='panel'><h2>Three economic mechanisms</h2>"
        "<p><strong>Renewal pricing:</strong> an assumed eligible revenue cohort, captured price uplift and incremental churn combine once; variable servicing cost changes with the net revenue effect.</p>"
        "<p><strong>Service intervention:</strong> successful resolution releases capacity. Financial benefit is capped by avoided work, an explicit vendor-spend action and addressable spend. A zero cost action produces zero gross financial savings.</p>"
        "<p><strong>Collections:</strong> existing receivables are collected earlier. The temporary cash advantage reverses on the original collection date; it creates no revenue, EBITDA or recurring valuation benefit.</p>"
        f"<p><strong>Included scope:</strong> {escape('; '.join(selected_titles) or 'None; retained commitments only')}.</p>"
        f"<p><strong>First-100-day cash:</strong> the base scenario includes {amount(base['day_100']['working_capital_cash'])} of temporary receivables timing. Review its later reversal alongside implementation spending.</p>"
        "<p>Platform fees start at kickoff. Implementation expense, its payment and capitalized spend have separate dates. Shared committed foundation costs survive exclusion. "
        + (
            "Overlapping benefit pools use the explicit allocation and exclusion rules below."
            if isinstance(case, InteractionCase)
            else "Overlapping benefit pools require a combined driver before aggregation."
        )
        + "</p></section>"
    )
    if isinstance(case, InteractionCase):
        body += render_allocation(report)
    body += (
        "<section class='panel' id='scenarios'><h2>Downside, base and upside</h2>"
        + table(
            [
                "Scenario",
                "Day-100 EBITDA",
                "Day-100 cash",
                "Year-one EBITDA",
                "Year-one cash",
                "Year-two recurring contribution",
                "24-month cash",
            ],
            [
                [
                    escape(s["scenario_id"]),
                    amount(s["day_100"]["incremental_ebitda"]),
                    amount(s["day_100"]["pre_tax_cash_proxy"]),
                    amount(s["year_one"]["incremental_ebitda"]),
                    amount(s["year_one"]["pre_tax_cash_proxy"]),
                    amount(s["year_two"]["recurring_contribution"]),
                    amount(s["total"]["pre_tax_cash_proxy"]),
                ]
                for s in scenarios
            ],
            "Deterministic judgmental scenarios, not confidence intervals or calibrated probabilities. An adverse result stays adverse.",
        )
        + "</section>"
    )
    rows = [
        ("Price benefit on retained cohort", "gross_price_benefit"),
        ("Lost baseline revenue from incremental churn", "revenue_leakage"),
        ("Variable servicing cost change", "variable_cost"),
        ("Explicit service cost action", "cost_removed"),
        ("Recurring fees and governance expense", "recurring_cost"),
        ("Temporary implementation expense", "implementation_expense"),
        ("Incremental in-period EBITDA", "incremental_ebitda"),
        ("Accrual-to-operating-cash timing adjustment", "operating_accrual_to_cash"),
        ("Existing receivables timing movement", "working_capital_cash"),
        ("Capital expenditure cash outflow", "capex_cash"),
        ("Incremental pre-tax cash proxy", "pre_tax_cash_proxy"),
    ]
    body += (
        "<section class='panel' id='bridges'><h2>Base scenario: two financial bridges</h2>"
        + table(
            ["Signed component", "First 100 days", "Year one", "Year two"],
            [[label, *(amount(base[p][key]) for p in ("day_100", "year_one", "year_two"))] for label, key in rows],
            "The first six lines sum to EBITDA. EBITDA plus the timing adjustment, receivables movement and capex equals cash. Implementation expense is not deducted twice.",
        )
        + f"<p>{escape(report['cash_definition'])}</p><p>After month 24, the base scenario has {amount(base['cash_settlement_after_horizon'])} of scheduled incremental cash settlement. This is disclosed separately, not silently discarded.</p>"
        + f"<p><strong>Base cash-proxy recovery:</strong> {escape(str(base['cash_proxy_recovery_date'] or base['cash_proxy_recovery_state'].replace('_', ' ')))}. This is recovery after the final negative cumulative balance within the modeled horizon; it includes collection reversals and is not actual payback evidence.</p></section>"
    )
    body += (
        "<section class='panel' id='valuation'><h2>Incremental enterprise-value sensitivity</h2>"
        + table(
            ["Scenario", "Year-two recurring contribution", *(f"{m}×" for m in case.multiples)],
            [
                [
                    escape(s["scenario_id"]),
                    amount(s["year_two"]["recurring_contribution"]),
                    *(amount(v["incremental_ev_sensitivity"]) for v in s["valuation"]),
                ]
                for s in scenarios
            ],
            "Operating contribution and multiple assumptions are separate. A change in the multiple changes no operating or cash result.",
        )
        + f"<p>{escape(report['valuation_definition'])}</p><p>{escape(case.multiple_rationale)}</p></section>"
    )
    body += "<section class='panel' id='monthly'><h2>Monthly execution economics</h2>"
    for scenario in scenarios:
        body += (
            f"<details><summary>{escape(scenario['scenario_id'].title())} · 24 monthly periods</summary>"
            + table(
                [
                    "Month",
                    "EBITDA",
                    "Operating timing adjustment",
                    "Receivables timing",
                    "Capex",
                    "Cash proxy",
                    "Capacity hours",
                ],
                [
                    [
                        str(r["start"]),
                        *(
                            amount(r[k])
                            for k in (
                                "incremental_ebitda",
                                "operating_accrual_to_cash",
                                "working_capital_cash",
                                "capex_cash",
                                "pre_tax_cash_proxy",
                                "capacity_hours",
                            )
                        ),
                    ]
                    for r in scenario["monthly"]
                ],
                report["timing_convention"],
            )
            + "</details>"
        )
    body += "</section><section class='panel' id='assumptions'><h2>Assumptions to challenge</h2>"
    for scenario in scenarios:
        body += (
            f"<details><summary>{escape(scenario['scenario_id'].title())} assumptions and dated costs</summary>"
            + table(
                ["Assumption", "Value", "Unit", "Rationale", "Invalidating evidence"],
                [
                    [
                        escape(a["assumption_id"]),
                        escape(a["value"]),
                        escape(a["unit"]),
                        escape(a["rationale"]),
                        escape(a["invalidated_by"]),
                    ]
                    for a in scenario["assumptions"]
                ],
                "All operating inputs are constructed; source context does not turn assumptions into company facts.",
            )
            + table(
                ["Cost", "Kind", "Amount reference", "Recognition", "Payment", "Retained if excluded"],
                [
                    [
                        escape(c["cost_id"]),
                        escape(c["kind"]),
                        escape(c["amount"]),
                        escape(c["recognized_on"]),
                        escape(c["paid_on"]),
                        "Yes" if c["retained_if_excluded"] else "No",
                    ]
                    for c in scenario["costs"]
                ],
                "Shared costs are recorded once. Exclusion removes only costs explicitly treated as avoidable.",
            )
            + "</details>"
        )
    body += f"<p>{escape(report['review'])}</p><p class='muted'>Calculation {escape(report['calculation_version'])} · SHA-256 <code>{report['calculation_sha256']}</code></p></section>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Constructed underwriting — {escape(case.company)}</title><style>{CSS}</style></head><body><a class='skip-link' href='#main'>Skip to content</a>"
        "<header class='topbar'><div class='topbar-inner'><a class='brand' href='#main'>Value Creation OS · Underwriting</a><nav class='primary-nav' aria-label='Sections'><a class='nav-link' href='#scenarios'>Scenarios</a><a class='nav-link' href='#bridges'>Economics</a><a class='nav-link' href='#assumptions'>Assumptions</a></nav></div></header>"
        f"<main class='app-shell' id='main' tabindex='-1'>{body}</main></body></html>"
    )


def build_underwriting_report(
    source: Path, output: Path, excluded: frozenset[str] = frozenset(), *, selected: frozenset[str] | None = None
) -> Path:
    case = read_underwriting(source.read_bytes())
    ids = frozenset(d.initiative_id for d in case.scenarios[0].drivers)
    if not excluded <= ids:
        raise ValueError("exclusion contains an unknown initiative")
    if selected is not None and excluded:
        raise ValueError("select and exclude are mutually exclusive")
    default = frozenset(case.interaction_policy.selected_initiatives) if isinstance(case, InteractionCase) else ids
    report = evaluate(case, default - excluded if selected is None else selected)
    html = render_underwriting(case, report)
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if source.resolve() in {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite its input")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
