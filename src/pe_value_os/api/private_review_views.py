"""Executive private review pages; every dynamic string is escaped."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from .presentation import icon, money, page, page_header, status_badge

ASSESSMENTS = {
    "accounting_reconciliation": "How do the amounts reconcile to accepted accounting records?",
    "mechanism_and_delivery": "What mechanism and accepted delivery support these claims?",
    "alternative_explanations": "What alternative explanations remain?",
    "double_counting_and_residuals": "How were overlaps and unassigned differences handled?",
    "attribution_limits": "What can and cannot be concluded from this review?",
}
DECISIONS = {
    "accept": "Accepted",
    "reject": "Rejected",
    "request_changes": "Changes requested",
    "withdraw": "Acceptance withdrawn",
}


def _e(value: Any) -> str:
    return escape(str(value))


def review_path(company_id: str, revision_id: str) -> str:
    return f"/companies/{quote(company_id, safe='')}/private-reviews/{quote(revision_id, safe='')}"


def _table(caption: str, columns: tuple[str, ...], rows: list[list[Any]], numeric: tuple[int, ...] = ()) -> str:
    def cls(index: int) -> str:
        return " class='num'" if index in numeric else ""

    return (
        f"<div class='table-wrap' role='region' aria-label='{_e(caption)}' tabindex='0'><table>"
        f"<caption class='sr-only'>{_e(caption)}</caption><thead><tr>"
        + "".join(f"<th scope='col'{cls(i)}>{_e(c)}</th>" for i, c in enumerate(columns))
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td{cls(i)}>{_e(c)}</td>" for i, c in enumerate(row)) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def _initials(name: str) -> str:
    return _e("".join(word[0] for word in str(name).split()[:2]))


def index_page(cards: list[dict[str, Any]]) -> str:
    body = page_header(
        "Finance decision desk",
        eyebrow="<span class='eyebrow'>Private workspace</span>",
        subtitle="Review the bridge from accepted accounting to initiative claims. "
        "Current support is checked when you open a review.",
        symbol="private",
    )
    if cards:
        body += (
            "<section class='table-card' aria-labelledby='review-list-title'><div class='table-toolbar'>"
            f"<div class='toolbar-title'>{icon('scale')}<h2 id='review-list-title'>Private reviews</h2>"
            f"<span class='count'>{len(cards)}</span></div>"
            "<div class='toolbar-meta'><span>Source origin shown per case</span></div></div><ul class='review-list'>"
        )
    for card in cards:
        body += (
            f"<li class='review-row'><div class='entity'><span class='company-monogram' aria-hidden='true'>{_initials(card['company_name'])}</span>"
            f"<div><h3 class='entity-name'>{_e(card['company_name'])}</h3><p>{_e(card['case_key'])} · <span class='badge'>"
            + _e("Fictional rehearsal" if card["origin"] == "synthetic_test_fixture" else "Permissioned company data")
            + "</span></p></div></div>"
            + f"<p>Measurement begins {_e(card['first_month'])} · {_e(card['months'])} month(s)</p>"
            + f"<p class='muted'>Recorded finance decision: {_e(DECISIONS.get(card['decision'], 'Awaiting review'))}</p>"
            + f"<a class='button secondary' href='{_e(review_path(card['company_id'], card['revision_id']))}'>Open review &rarr;</a></li>"
        )
    if cards:
        body += "</ul></section>"
    else:
        body += (
            f"<section class='panel empty-state'><span class='page-icon'>{icon('private')}</span>"
            "<h2>No private claims to review</h2><p>An authorized operator must first prepare accepted source records, "
            "a baseline, observations and an attribution proposal.</p></section>"
        )
    # Mixed origins are labeled per card; avoid a global claim that all data are synthetic.
    return page("Private finance reviews", body, active="private", private_origin="mixed")


def review_page(
    packet: dict[str, Any],
    csrf: str,
    nonce: str,
    *,
    error: str | None = None,
    submitted: dict[str, str] | None = None,
) -> str:
    submitted = submitted or {}
    proposal, observation = packet["proposal"], packet["observation"]
    baseline, plan, execution = packet["baseline"], packet["plan"], packet["execution"]
    checks, reviews = packet["checks"], packet["reviews"]
    currency = packet["currency"]
    historical = not checks["proposal_supported"]
    accepted = checks["finance_acceptance_supported"]
    status = "Reviewed claim" if accepted else ("Historical / unsupported" if historical else "Finance review required")
    path = review_path(packet["company_id"], proposal["revision_id"])
    origin = (
        "Fictional private-workflow rehearsal"
        if packet["origin"] == "synthetic_test_fixture"
        else "Permissioned private company data"
    )
    explanation = (
        "Finance acceptance is recorded. Continue to distinguish reviewed claims from proven causal impact."
        if accepted
        else "Current support is unavailable. These are historical receipts; a prior acceptance can still be withdrawn."
        if historical
        else "Inspect the accounting bridge, delivery evidence and residual before recording a finance decision."
    )
    body = page_header(
        packet["company_name"],
        crumbs=[("Private reviews", "/private-reviews"), (str(packet["company_name"]), None)],
        eyebrow=f"<span class='eyebrow'>{_e(origin)}</span>",
        subtitle=f"Financial attribution review · {_e(packet['case_key'])}",
        meta=f"<span>{icon('calendar')}Measurement: <strong>{_e(observation['result']['first_month'])} to "
        f"{_e(observation['result']['end'])}</strong></span><span>{icon('value')}<strong>{_e(currency)} units</strong></span>",
        symbol="scale",
        aside=f"<div class='status-card'><p class='metric-label'>Decision status</p><h2>{_e(status)}</h2><p>{explanation}</p></div>",
    )
    if error:
        body += f"<div class='alert bad' role='alert'><h2>Decision was not recorded</h2><p>{_e(error)}</p></div>"
    if historical:
        body += "<div class='alert' role='status'><strong>Historical values only.</strong> Source, baseline, delivery or version support is unavailable. These amounts are not presented as currently supported claims.</div>"
    elif not accepted:
        body += "<div class='alert'><strong>Proposed allocation.</strong> The figures below have current technical support but no current finance acceptance. Review notes and evidence references do not prove causation.</div>"
    totals = proposal["result"]["totals"]
    body += "<section aria-label='Attribution bridge' class='summary-strip cols-3'>"
    for key, title, symbol in (
        ("difference", "Accounting difference", "scale"),
        ("proposed_attribution", "Reviewed allocation" if accepted else "Proposed allocation", "value"),
        ("residual", "Unassigned difference", "alert"),
    ):
        values = totals[key]
        body += (
            f"<div class='summary-item'><p class='metric-label'>{icon(symbol)}{_e(title)}</p><div class='metric-value'>"
            + money(values["mapped_ebitda"])
            + "</div><p class='metric-note'>EBITDA proxy · "
            + _e(currency)
            + "</p><p>Cash proxy: <strong>"
            + money(values["pre_tax_cash_proxy"])
            + "</strong></p></div>"
        )
    body += "</section><section><div class='block-head'><div><h2>Accounting to attribution</h2><p>Whole closed months. Allocation plus residual equals the accounting difference.</p></div></div>"
    observation_totals = observation["result"]["totals"]
    body += _table(
        "Financial comparison",
        ("Measure", "Actual", "Counterfactual", "Difference", "Frozen incremental plan", "Variance to plan"),
        [
            [
                title,
                *[
                    money(observation_totals[kind][measure])
                    for kind in ("actual", "counterfactual", "difference", "frozen_forecast", "variance")
                ],
            ]
            for measure, title in (("mapped_ebitda", "EBITDA proxy"), ("pre_tax_cash_proxy", "Cash proxy"))
        ],
        numeric=(1, 2, 3, 4, 5),
    )
    rows = []
    observed_months = {m["start"]: m for m in observation["result"]["monthly"]}
    for month in proposal["result"]["monthly"]:
        actual_rows = {r["component"]: r for r in observed_months[month["start"]]["components"]}
        for row in month["components"]:
            actual = actual_rows[row["component"]]
            rows.append(
                [
                    month["start"],
                    row["component"].replace("_", " ").capitalize(),
                    *[
                        money(value)
                        for value in (
                            actual["actual"],
                            actual["counterfactual"],
                            row["difference"],
                            row["proposed_attribution"],
                            row["residual"],
                        )
                    ],
                ]
            )
    body += "<details><summary>Monthly accounting components</summary><div class='details-content'>"
    body += _table(
        "Monthly accounting bridge",
        ("Month", "Component", "Actual", "Counterfactual", "Difference", "Allocation", "Residual"),
        rows,
        numeric=(2, 3, 4, 5, 6),
    )
    body += "</div></details>"
    body += "<p class='table-caption'>EBITDA uses the accepted mapping of revenue and operating expenses. It is not normalized maintainable earnings. Cash is the defined pre-tax operating, working-capital and capex proxy; it excludes financing and tax.</p>"
    counterfactual = packet["counterfactual"]
    body += "<details><summary>Source scope and counterfactual assumptions</summary><div class='details-content'>"
    body += f"<p><strong>Comparability assessment:</strong> {_e(observation['request']['scope_comparability_attestation'])}</p>"
    body += f"<p><strong>Counterfactual design:</strong> {_e(counterfactual['request']['design_timing'])}. {_e(counterfactual['request']['timing_rationale'])}</p>"
    body += f"<p>{_e(counterfactual['request']['scope_and_limits'])}</p>"
    body += _table(
        "Counterfactual adjustments",
        ("Month", "Component", "Historical anchor", "Adjustment", "Rationale"),
        [
            [
                component["period"],
                component["component"].replace("_", " "),
                component["anchor_month"],
                money(adjustment["amount"]),
                adjustment["rationale"],
            ]
            for component in counterfactual["request"]["components"]
            for adjustment in component["adjustments"]
        ],
        numeric=(3,),
    )
    source_path = f"/companies/{quote(packet['company_id'], safe='')}/private-intakes/{quote(packet['actual_snapshot']['request']['intake_id'], safe='')}/source"
    body += f"<p><a href='{_e(source_path)}'>Inspect the accounting export</a> · access requires current processing permission.</p></div></details></section>"
    body += (
        "<div class='brief-grid'><section class='panel record-card'><div class='record-head'><div><h2>Frozen plan</h2>"
        "<p class='record-sub'>The approved comparison stays fixed when observations or claims change.</p></div></div>"
    )
    frozen = baseline["frozen_forecast"]
    body += _table(
        "Frozen plan economics",
        ("Horizon", "Incremental EBITDA", "Cash proxy"),
        [
            [label, money(frozen[key]["incremental_ebitda"]), money(frozen[key]["pre_tax_cash_proxy"])]
            for key, label in (("day_100", "Day 100"), ("year_one", "Year one"), ("year_two", "Year two"))
        ],
        numeric=(1, 2),
    )
    body += f"<p class='muted'>Scenario: {_e(baseline['request']['scenario_id'])} · frozen {_e(baseline['recorded_at'])}</p>"
    body += "<details><summary>Valuation sensitivity and limits</summary><div class='details-content'>"
    body += _table(
        "Incremental value sensitivity",
        ("Assumed multiple", "Incremental enterprise-value sensitivity"),
        [[money(v["multiple"]), money(v["incremental_ev_sensitivity"])] for v in frozen["valuation"]],
        numeric=(0, 1),
    )
    body += f"<p>{_e(plan['schedule_result']['scheduled_financials']['valuation_definition'])}</p></div></details></section>"
    supported = execution["recorded_authorization_currently_supported"]
    body += (
        "<section class='panel record-card'><div class='record-head'><div><h2>Delivery and operating permission</h2>"
        "<p class='record-sub'>"
        + (
            "Recorded operating authorization is currently supported."
            if supported
            else "No currently supported operating authorization. Finance review does not authorize operating changes."
        )
        + "</p></div>"
        + status_badge("active" if supported else "blocked")
        + "</div>"
    )
    task_names = {t["task_id"]: t["title"] for t in plan["request"]["plan"]["tasks"]}
    body += _table(
        "Delivery support",
        ("Work package", "Acceptance support"),
        [
            [task_names[t["task_id"]], "Supported" if t["acceptance_supported"] else "Unavailable"]
            for t in execution["tasks"]
        ],
    )
    body += "<p>Reported delivery cost: <strong>" + money(execution["reported_cost"]) + f" {_e(currency)}</strong></p>"
    body += "<p class='form-help'>Reported costs have not been reconciled to individual ledger entries. Their reporting dates and scope may differ from this measurement window.</p></section></div>"
    body += "<section class='panel record-card claims'><div class='record-head'><div><h2>Claims and competing explanations</h2></div>"
    body += f"<span class='count'>{len(proposal['request']['allocations'])}</span></div>"
    for allocation in proposal["request"]["allocations"]:
        body += f"<details><summary>{_e(allocation['initiative_id'])} · {_e(allocation['period'])} · {_e(allocation['component'].replace('_', ' '))} · {money(allocation['amount'])} {_e(currency)}</summary><div class='details-content'>"
        body += f"<p><strong>Mechanism:</strong> {_e(allocation['mechanism'])}</p><p><strong>Alternative explanations:</strong> {_e(allocation['alternative_explanations'])}</p>"
        body += f"<p><strong>Evidence:</strong> {_e(allocation['evidence']['reference'])}</p><p>{_e(allocation['evidence']['attestation'])}</p><code>{_e(allocation['evidence']['sha256'])}</code></div></details>"
    if not proposal["request"]["allocations"]:
        body += "<p>No initiative allocations are proposed. All accounting differences remain unassigned.</p>"
    body += f"<p class='muted'>{_e(proposal['request']['method_and_limits'])}</p></section>"
    body += (
        "<section class='decision-panel' id='finance-decision'><div class='decision-head'>"
        f"<span class='page-icon'>{icon('shield')}</span><div><h2>Finance decision</h2><p>Acceptance records your assessment "
        "of this exact claim version. It does not authorize operations or prove causal impact.</p></div></div>"
    )
    substantive, withdraw = packet["can_record_substantive_review"], packet["can_withdraw_review"]
    if substantive or withdraw:
        hidden = dict(
            csrf=csrf,
            idempotency_key=nonce,
            expected_previous_sha256=packet["current_review_sha256"] or "",
            expected_attribution_sha256=proposal["content_sha256"],
            expected_execution_head_sha256=packet["execution_head_sha256"] or "",
        )
        body += f"<form method='post' action='{_e(path)}/decision'>"
        body += "".join(f"<input type='hidden' name='{key}' value='{_e(value)}'>" for key, value in hidden.items())
        body += (
            "<div class='decision-body'><label for='rationale'>Decision rationale</label><textarea id='rationale' name='rationale' required maxlength='6000'>"
            + _e(submitted.get("rationale", ""))
            + "</textarea>"
        )
        if substantive:
            body += "<fieldset><legend>Assessment notes — complete all five to accept</legend>"
            for key, title in ASSESSMENTS.items():
                body += f"<label for='{key}'>{_e(title)}</label><textarea id='{key}' name='{key}' maxlength='6000'>{_e(submitted.get(key, ''))}</textarea>"
            body += "</fieldset></div><div class='decision-actions'>"
            for decision, title, style in (
                ("accept", "Accept reviewed claims", "button"),
                ("request_changes", "Request changes", "button secondary"),
                ("reject", "Reject claims", "button danger"),
            ):
                body += f"<button class='{style}' type='submit' name='decision' value='{decision}'>{title}</button>"
        else:
            body += "</div><div class='decision-actions'>"
        if withdraw:
            body += "<button class='button secondary' type='submit' name='decision' value='withdraw'>Withdraw acceptance</button>"
        body += "<p class='form-help'>Your authenticated identity and these review notes will be recorded. Notes are fingerprinted as an internal review record; no external document verification is implied.</p></div></form>"
    else:
        body += "<div class='decision-record'><p class='alert'>No decision is available for this identity and version. Substantive review needs current support and an authorized finance reviewer distinct from the proposal author.</p></div>"
    body += "</section><section class='panel record-card'><div class='record-head'><div><h2>Decision history</h2></div>"
    body += f"<span class='count'>{len(reviews)}</span></div>"
    body += (
        _table(
            "Finance decision history",
            ("Recorded at", "Reviewer", "Decision", "Rationale"),
            [
                [r["recorded_at"], r["author"], DECISIONS[r["request"]["decision"]], r["request"]["rationale"]]
                for r in reviews
            ],
        )
        if reviews
        else "<p>No finance decision has been recorded for this version.</p>"
    )
    for review in reviews:
        request = review["request"]
        body += f"<details><summary>{_e(DECISIONS[request['decision']])} · {_e(review['recorded_at'])} · review notes</summary><div class='details-content'>"
        for key, value in (request["assessment"] or {}).items():
            body += f"<p><strong>{_e(ASSESSMENTS[key])}</strong></p><p>{_e(value)}</p>"
        evidence = request["evidence"]
        body += (
            f"<p><strong>Review evidence:</strong> {_e(evidence['reference'])}</p><p>{_e(evidence['attestation'])}</p>"
        )
        body += f"<p><strong>Evidence fingerprint:</strong> <code>{_e(evidence['sha256'])}</code></p>"
        body += f"<p><strong>Decision receipt:</strong> <code>{_e(review['content_sha256'])}</code></p></div></details>"
    body += "</section><details><summary>Version and evidence trail</summary><div class='details-content'>"
    for label, value in (
        ("Attribution", proposal["content_sha256"]),
        ("Observation", observation["content_sha256"]),
        ("Frozen baseline", baseline["content_sha256"]),
        ("Execution head", packet["execution_head_sha256"] or "No execution recorded"),
        ("Review data", packet["packet_sha256"]),
    ):
        body += f"<p><strong>{label}:</strong> <code>{_e(value)}</code></p>"
    body += f"<p>Generated {_e(packet['generated_at'])}. Current support can change; every submitted decision is checked again.</p></div></details>"
    body = "<div class='private-review'>" + body + "</div>"
    return page("Private attribution review", body, active="private", private_origin=packet["origin"])
