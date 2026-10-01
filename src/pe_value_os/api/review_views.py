"""Executive decision memos and evidence-backed operating performance views."""

from __future__ import annotations

import re
from decimal import Decimal
from html import escape, unescape
from typing import Any

from ..domain.baselines import REGISTRY
from ..domain.kpi_models import KpiDefinition, KpiObservation
from ..domain.models import Finding
from ..domain.project_models import Opportunity, ValueCase
from ..domain.runs import ApprovalRecord, PlanRecord, RunRecord, Status
from ..kpi import covers_plan_period
from .presentation import icon, label, money, page, page_header, status_badge


def _e(value: Any) -> str:
    return escape(str(value))


def _number(value: Any) -> Decimal:
    return Decimal(str(value))


def _percent(value: Any) -> str:
    return f"{_number(value) * 100:,.1f}%"


def _metric(metric: str, value: Any) -> str:
    """Use registered units; a tickets/customer ratio is not a percentage."""
    if metric == "tier1_tickets_per_customer_month":
        return f"{_number(value):,.3f} tickets / customer / month"
    spec = REGISTRY.get(metric)
    if spec and spec.unit == "ratio":
        return _percent(value)
    if spec and spec.unit == "months":
        return f"{_number(value):,.2f} months"
    if spec and spec.unit == "currency":
        return money(value)
    return f"{_number(value):,.4f}".rstrip("0").rstrip(".")


def _list(values: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{_e(v)}</li>" for v in values) + "</ul>"


def _evidence(ids: list[str], run_id: str) -> str:
    if not ids:
        return "<span class='muted'>No linked evidence</span>"
    return (
        "<div class='evidence-links'>"
        + "".join(
            f"<a href='/evidence/{_e(e)}/review?run_id={_e(run_id)}' title='Evidence {_e(e)}'>Source {n:02d}</a>"
            for n, e in enumerate(dict.fromkeys(ids), 1)
        )
        + "</div>"
    )


def _card(name: str, value: str, note: str, symbol: str = "chart") -> str:
    return (
        f"<div class='summary-item'><p class='metric-label'>{icon(symbol)}{_e(name)}</p>"
        f"<div class='metric-value'>{value}</div><p class='metric-note'>{_e(note)}</p></div>"
    )


def _timeline(ws: dict[str, Any]) -> str:
    milestones = ws.get("milestones", {})
    if not milestones:
        return ""
    return (
        "<div class='timeline-grid'>"
        + "".join(
            f"<section class='timeline-stage'><h4>{label(stage)}</h4>{_list(entries)}</section>"
            for stage, entries in milestones.items()
            if entries
        )
        + "</div>"
    )


def _workstream(ws: dict[str, Any], rank: int) -> str:
    initiatives = ws.get("initiatives", [])
    annual = sum((_number(i["run_rate_ebitda_base"]) for i in initiatives), Decimal(0))
    in_year = sum((_number(i["in_year_ebitda_base"]) for i in initiatives), Decimal(0))
    count = f"{len(initiatives)} initiative{'' if len(initiatives) == 1 else 's'}"
    h = [
        "<article class='panel record-card workstream-card'><div class='record-head'><div class='record-title'>",
        f"<span class='record-num' aria-hidden='true'>{rank:02d}</span><div><h3>{_e(ws['name'])}</h3>",
        f"<p class='record-sub'><span>Workstream {rank:02d}</span>"
        f"<span>{icon('user')}{_e(ws.get('owner_role', 'Owner not assigned'))}</span></p>",
        f"</div></div><span class='badge'>{count}</span></div>",
        "<div class='table-wrap' tabindex='0' role='region' aria-label='Workstream initiatives'><table class='data-table stack-table'>"
        "<thead><tr><th scope='col'>Initiative</th><th scope='col'>Type</th>"
        "<th scope='col' class='num'>Annual EBITDA</th><th scope='col' class='num'>In-year</th></tr></thead><tbody>",
    ]
    for i in initiatives:
        reasons = i.get("requires_approval_reasons", [])
        condition = "<small>Approval condition: " + "; ".join(_e(r) for r in reasons) + "</small>" if reasons else ""
        h.append(
            f"<tr><th scope='row'>{_e(i['title'])}{condition}</th><td data-label='Type'><span class='badge'>{label(i['classification'])}</span></td>"
            f"<td class='num' data-label='Annual EBITDA'>{money(i['run_rate_ebitda_base'])}</td><td class='num' data-label='In-year'>{money(i['in_year_ebitda_base'])}</td></tr>"
        )
    h.append(
        f"</tbody><tfoot><tr><th scope='row' colspan='2'>Workstream total</th><td class='num' data-label='Annual EBITDA'>{money(annual)}</td>"
        f"<td class='num' data-label='In-year'>{money(in_year)}</td></tr></tfoot></table></div>"
    )
    if ws.get("dependencies"):
        h.append(
            "<div class='alert warning'><strong>Before implementation</strong>" + _list(ws["dependencies"]) + "</div>"
        )
    h.append("<details class='disclosure'><summary>100-day milestones &amp; measurement</summary>")
    h.append(_timeline(ws))
    if ws.get("kpis"):
        h.append(
            "<div class='table-wrap' tabindex='0' role='region' aria-label='Workstream operating targets'><table class='data-table'><caption>Workstream targets</caption><thead><tr><th scope='col'>Operating metric</th><th scope='col'>Baseline</th><th scope='col'>Day 100</th><th scope='col'>Run rate</th></tr></thead><tbody>"
        )
        for k in ws["kpis"]:
            h.append(
                f"<tr><th scope='row'>{_e(k['description'])}<small>{label(k['direction'])} is better</small></th>"
                f"<td>{_metric(k['metric'], k['baseline'])}</td><td>{_metric(k['metric'], k['day_100_target'])}</td>"
                f"<td>{_metric(k['metric'], k['run_rate_target'])}</td></tr>"
            )
        h.append("</tbody></table></div>")
    h.append("</details>")
    if ws.get("risks"):
        h.append(
            "<details class='disclosure'><summary>Execution assumptions &amp; risks</summary>"
            + _list(ws["risks"])
            + "</details>"
        )
    h.append("</article>")
    return "".join(h)


def _case_row(o: Opportunity, vc: ValueCase | None, included: bool) -> str:
    attrs = f"data-opportunity-id='{_e(o.opportunity_id)}' data-included='{str(included).lower()}'"
    outside = "" if included else " class='is-outside'"
    return (
        f"<tr {attrs}{outside}><th scope='row'>"
        f"<a class='row-link' href='#case-{_e(o.opportunity_id)}'>{_e(o.title)}</a>"
        f"<small>{label(o.lever.value)} · {_e(o.confidence.value)} confidence</small></th>"
        f"<td><span class='badge'>{'In plan' if included else 'Outside plan'}</span></td>"
        f"<td class='num'>{money(vc.annual_ebitda_base) if vc else 'Not sized'}</td>"
        f"<td class='row-chevron'>{icon('chevron')}</td></tr>"
    )


def _selected_rows(ids: list[str]) -> str:
    """Highlight the value case whose panel is open; the first case is selected when no fragment is present."""
    rows = [".split:not(:has(.detail-panel:target)) .case-table tbody tr:first-child"]
    rows += [
        f".split:has(#case-{i}:target) .case-table tr[data-opportunity-id='{i}']"
        for i in ids
        if re.fullmatch(r"[A-Za-z0-9_-]+", i)
    ]
    return (
        "<style>"
        + ",".join(f"{r}>*" for r in rows)
        + "{background:var(--accent-soft)}"
        + ",".join(f"{r}>th" for r in rows)
        + "{box-shadow:inset 3px 0 0 var(--accent)}"
        + ",".join(f"{r} .row-link" for r in rows)
        + "{color:var(--text);font-weight:600}"
        + ",".join(f"{r} .row-chevron" for r in rows)
        + "{color:var(--accent)}</style>"
    )


def _case(o: Opportunity, vc: ValueCase | None, included: bool) -> str:
    oid = _e(o.opportunity_id)
    scope = "Included in displayed plan" if included else "Outside displayed plan"
    h = [
        f"<article class='detail-panel value-case' id='case-{oid}' data-opportunity-id='{oid}' "
        f"data-included='{str(included).lower()}' aria-labelledby='case-title-{oid}'><div class='detail-head'>",
        f"<p class='detail-kicker'><span class='record-icon'>{icon('value')}</span>Value case · {label(o.lever.value)}</p>",
        f"<h3 id='case-title-{oid}'>{_e(o.title)}</h3>",
        f"<div class='detail-tags'><span class='badge'>{_e(o.confidence.value)} confidence</span>"
        f"<span class='badge'>{scope}</span></div></div><div class='detail-body'>",
        f"<p class='detail-lede'>{_e(o.rationale)}</p>",
    ]
    if vc:
        h.append(
            "<section class='detail-section'><h4>Annual EBITDA scenarios</h4>"
            "<div class='scenario-grid' aria-label='Annual EBITDA scenario comparison'>"
        )
        for name, value in [
            ("Low", vc.annual_ebitda_low),
            ("Base", vc.annual_ebitda_base),
            ("High", vc.annual_ebitda_high),
        ]:
            classes = " negative" if value < 0 else (" base" if name == "Base" else "")
            h.append(
                f"<div class='scenario-card{classes}'><span class='metric-label'>{name} case</span><strong class='metric-value'>{money(value)}</strong><small class='metric-note'>Annual EBITDA</small></div>"
            )
        h.append(
            "</div><p class='metric-note'>Scenarios are modeled outcomes, not probabilities or realized returns. Negative values represent an EBITDA reduction.</p></section>"
        )
    h.append(
        "<section class='detail-section'><h4>Financial assumptions</h4><dl class='definition-list'>"
        f"<div><dt>Baseline · {label(o.baseline_metric)}</dt><dd>{_metric(o.baseline_metric, o.baseline_value)}</dd></div>"
        f"<div><dt>EBITDA flow-through</dt><dd>{_percent(o.ebitda_flow_through)}</dd></div>"
        f"<div><dt>Recurring annual cost</dt><dd>{money(o.annual_run_cost)}</dd></div>"
        f"<div><dt>One-time implementation cost</dt><dd>{money(o.one_time_cost)}</dd></div></dl>"
        "<div class='table-wrap' tabindex='0' role='region' aria-label='Scenario input assumptions'><table class='data-table'><caption>Scenario input rates</caption><thead><tr><th scope='col'>Assumption</th><th scope='col' class='num'>Low</th><th scope='col' class='num'>Base</th><th scope='col' class='num'>High</th></tr></thead><tbody>"
        f"<tr><th scope='row'>Improvement</th><td class='num'>{_percent(o.low.improvement_rate)}</td><td class='num'>{_percent(o.base.improvement_rate)}</td><td class='num'>{_percent(o.high.improvement_rate)}</td></tr>"
        f"<tr><th scope='row'>Realization</th><td class='num'>{_percent(o.low.realization_rate)}</td><td class='num'>{_percent(o.base.realization_rate)}</td><td class='num'>{_percent(o.high.realization_rate)}</td></tr></tbody></table></div>"
        "<p class='metric-note'>Annual EBITDA = baseline × improvement × realization × flow-through − recurring annual cost. One-time cost is shown separately; it is not deducted from annual EBITDA.</p>"
    )
    if o.assumptions:
        h.append(_list(o.assumptions))
    h.append(
        "</section><section class='detail-section'><h4>Source evidence</h4>"
        + _evidence(o.evidence_ids, o.run_id)
        + "</section></div>"
    )
    if vc:
        h.append(
            f"<p class='detail-foot'>Calculation {_e(vc.calc_version)} · Input fingerprint <code>{_e(vc.inputs_hash)}</code></p>"
        )
    h.append("</article>")
    return "".join(h)


def _decision(
    run: RunRecord,
    plan: PlanRecord | None,
    approval: ApprovalRecord | None,
    csrf: str,
    can_decide: bool,
    error: str | None,
    rationale: str,
    selected_initiatives: list[str],
) -> str:
    form = bool(approval and approval.decision is None and plan and can_decide)
    lede = (
        "Confirm the scope and operating conditions. This records a plan decision; each implementation condition remains the owner's responsibility."
        if form
        else "A human approver decides whether this plan enters execution. The decision and its rationale are recorded for audit."
    )
    h = [
        "<section id='decision' class='panel decision-panel'><div class='decision-head'>"
        f"<span class='page-icon'>{icon('shield')}</span><div><p class='eyebrow'>Human control</p>"
        f"<h2>Investment in execution</h2><p>{lede}</p></div></div>"
    ]
    if error:
        h.append(
            f"<div class='alert warning' role='alert'><strong>Decision not recorded</strong><p>{_e(error)}</p></div>"
        )
    if approval and approval.decision is not None:
        h.append(
            f"<div class='decision-record'><p class='inline-meta'>{status_badge(approval.decision.value)} <span>Decision recorded by <strong>{_e(approval.decided_by or 'Unknown actor')}</strong></span></p>"
        )
        if approval.decided_at:
            h.append(f"<p class='metric-note'>{_e(approval.decided_at.strftime('%d %b %Y · %H:%M UTC'))}</p>")
        h.append(f"<p>{_e(approval.rationale or 'No rationale supplied.')}</p>")
        if approval.diff.get("removed_titles"):
            h.append("<h3>Excluded by the approver</h3>" + _list(approval.diff["removed_titles"]))
        h.append(
            "<p class='metric-note'>This decision is read-only. The approved scope, when present, is reflected in the executive figures above.</p></div>"
        )
    elif approval and plan:
        if can_decide:
            h.append(
                f"<form method='post' action='/runs/{_e(run.run_id)}/approvals/form'>"
                f"<input type='hidden' name='csrf' value='{_e(csrf)}'><div class='decision-body'>"
                f"<details class='disclosure'{' open' if selected_initiatives else ''}><summary>Adjust the decision scope</summary><p>Selected initiatives are excluded when you approve or request a revised plan.</p>"
            )
            for ws in plan.plan.get("workstreams", []):
                for i in ws.get("initiatives", []):
                    h.append(
                        f"<label class='scope-option'><input type='checkbox' name='remove_initiatives' value='{_e(i['opportunity_id'])}'{' checked' if i['opportunity_id'] in selected_initiatives else ''}> <span>Exclude from this decision: {_e(i['title'])} <small>{money(i['run_rate_ebitda_base'])} annual EBITDA</small></span></label>"
                    )
            h.append(
                "</details><div class='field'><label for='rationale'>Decision rationale</label>"
                "<p id='rationale-help' class='form-help'>Required to reject or request changes. Record conditions, trade-offs and follow-up owners.</p>"
                f"<textarea class='input-field' id='rationale' name='rationale' rows='4' aria-describedby='rationale-help'>{_e(rationale)}</textarea></div></div>"
                "<div class='decision-actions'><button class='button' name='decision' value='approved'>Approve plan</button>"
                "<button class='button secondary' name='decision' value='changes_requested'>Request changes</button>"
                "<button class='button danger' name='decision' value='rejected'>Reject plan</button></div></form>"
            )
        else:
            h.append(
                "<div class='decision-record'><p>You can view this plan but only a human approver can decide. Your current access is read-only.</p></div>"
            )
    else:
        h.append(
            "<div class='decision-record'><p>No plan decision is available at this stage. Resolve the evidence or workflow conditions before submitting a plan for approval.</p></div>"
        )
    h.append("</section>")
    return "".join(h)


def review_page(
    run: RunRecord,
    plan: PlanRecord | None,
    opps: list[Opportunity],
    cases: dict[str, ValueCase],
    findings: list[Finding],
    approval: ApprovalRecord | None,
    csrf: str,
    can_decide: bool,
    *,
    company_name: str | None = None,
    currency: str | None = None,
    error: str | None = None,
    rationale: str = "",
    selected_initiatives: list[str] | None = None,
    workflow_state: dict[str, Any] | None = None,
) -> str:
    name = company_name or unescape(label(run.company_id))
    p = (plan.approved_plan if plan.approved_plan is not None else plan.plan) if plan else None
    approved = bool(plan and plan.approved_plan is not None)
    if plan and approval and approval.decision and approval.decision.value == "approved":
        # A recorded approval is authoritative before the worker applies it.
        if isinstance(approval.edits.get("approved_plan"), dict):
            p = approval.edits["approved_plan"]
        approved = True
    scope = "Approved" if approved else "Proposed"
    display_status = run.status.value
    if display_status == "awaiting_approval" and approval and approval.decision:
        display_status = {
            "approved": "approval_recorded",
            "rejected": "rejection_recorded",
            "changes_requested": "revisions_queued",
        }[approval.decision.value]
    units = currency or "source currency"
    gaps = [f for f in findings if f.finding_type.value == "data_gap"]
    meta = (
        f"<span>{icon('calendar')}As of <strong>{_e(run.updated_at.strftime('%d %b %Y · %H:%M UTC'))}</strong></span>"
    )
    if p is not None:
        meta += f"<span>{icon('layers')}<strong>{scope}</strong> scope</span><span>{icon('value')}Figures in <strong>{_e(units)}</strong></span>"
    h = [
        page_header(
            name,
            crumbs=[("Portfolio", "/"), ("Plan review", None)],
            subtitle=(
                "A decision-ready value creation plan, with the evidence behind every lever."
                if p
                else "Review the evidence requirements before committing to a value creation plan."
            ),
            badge=status_badge(display_status),
            meta=meta,
            symbol="company",
            tabs=True,
            actions=(
                f"<a class='button' href='#decision'>{'Review decision' if approval and approval.decision else 'Review &amp; decide'}</a>"
                if p is not None
                else ""
            ),
        ),
        "<nav class='section-nav' aria-label='Plan sections'>"
        f"<a href='#executive'>{icon('chart')}Decision brief</a><a href='#workstreams'>{icon('layers')}Execution plan</a>"
        f"<a href='#evidence'>{icon('file')}Value cases &amp; evidence</a><a href='#decision'>{icon('shield')}Decision record</a>",
        f"<a href='/companies/{_e(run.company_id)}/kpis?run_id={_e(run.run_id)}'>{icon('activity')}Operating performance</a></nav>",
    ]
    if run.status.value == "failed":
        state = workflow_state or {}
        h.append(
            "<section class='alert warning' role='status'><h2>Assessment interrupted</h2>"
            f"<p>The workflow stopped at <strong>{label(str(state.get('current_step') or 'an unreported step'))}</strong>. "
            "Completed work and audit history are retained. Resolve the recorded failure before an operator resumes this assessment.</p>"
            "<details class='disclosure'><summary>Failure and recovery details</summary>"
            + _list([str(item) for item in state.get("errors", [])])
            + f"<p class='form-help'>An authorized operator can resume this run after resolving the cause: <code>pvc resume {_e(run.run_id)}</code>.</p></details></section>"
        )
    if p is not None:
        workstreams = p.get("workstreams", [])
        initiatives = [i for ws in workstreams for i in ws.get("initiatives", [])]
        included = {i["opportunity_id"] for i in initiatives}
        annual = _number(p["total_run_rate_ebitda_base"])
        h.append(
            f"<section id='executive'><div class='block-head'><div><p class='eyebrow'>{scope} scope · {_e(units)}</p><h2>Value creation at a glance</h2></div></div><div class='summary-strip'>"
        )
        h.append(
            _card(
                "Modeled annual EBITDA",
                f"<span data-metric='run-rate-ebitda' data-value='{_e(annual)}' data-currency='{_e(units)}'>{money(annual)}</span>",
                f"{scope} run-rate uplift · not realized returns",
                "value",
            )
        )
        h.append(
            _card(
                "Modeled in-year EBITDA",
                money(p["total_in_year_ebitda_base"]),
                "Reflects implementation start and ramp",
                "calendar",
            )
        )
        h.append(
            _card(
                "Execution scope",
                str(len(initiatives)),
                f"Initiatives across {len(workstreams)} accountable workstreams",
                "layers",
            )
        )
        h.append(_card("Open data gaps", str(len(gaps)), "Review limitations before committing resources", "alert"))
        h.append(
            "</div><p class='summary-foot'>Totals sum independently sized value cases and are not adjusted for overlap. Validate interactions between initiatives before treating the total as an investment case.</p>"
            "<div class='brief-grid'><article class='panel'><div class='brief-head'><p class='eyebrow'>Contribution to the base case</p><h3>Where the value comes from</h3></div><div class='brief-body'>"
        )
        contributions = [
            (ws["name"], sum((_number(i["run_rate_ebitda_base"]) for i in ws.get("initiatives", [])), Decimal(0)))
            for ws in workstreams
        ]
        maximum = max((abs(value) for _, value in contributions), default=Decimal(0))
        for title, value in sorted(contributions, key=lambda pair: pair[1], reverse=True):
            width = abs(value) / maximum * 100 if maximum else Decimal(0)
            h.append(
                f"<div class='contribution-row'><div><span>{_e(title)}</span><strong>{money(value)}</strong></div><div class='bar-track' aria-hidden='true'><div class='bar-fill{' negative' if value < 0 else ''}' style='--value:{width:.2f}%;width:{width:.2f}%'></div></div></div>"
            )
        if not contributions:
            h.append("<p class='empty-state'>No initiatives remain in this scope. No modeled uplift is attributed.</p>")
        h.append(
            "<p class='metric-note'>Annual EBITDA by workstream. Bars scale to the largest absolute contribution; amounts sum to the displayed scope.</p></div></article>"
            "<article class='panel'><div class='brief-head'><p class='eyebrow'>Decision brief</p><h3>Conditions for execution</h3></div><div class='brief-body'>"
        )
        conditions = p.get("decisions_requiring_approval", [])
        h.append(
            _list(conditions) if conditions else "<p>No additional approval conditions recorded in this scope.</p>"
        )
        if p.get("narrative"):
            h.append(f"<p>{_e(p['narrative'])}</p>")
        if p.get("governance"):
            h.append(
                "<p class='metric-note'><strong>Governance:</strong> "
                + " · ".join(_e(x) for x in p["governance"])
                + "</p>"
            )
        h.append(
            "</div></article></div></section><section id='workstreams'><div class='block-head'><div><p class='eyebrow'>100-day implementation</p>"
            f"<h2>Accountable workstreams</h2></div><span class='count'>{len(workstreams)}</span></div><div class='stack records'>"
        )
        for rank, ws in enumerate(workstreams, 1):
            h.append(_workstream(ws, rank))
        h.append("</div></section>")
        if approved and plan:
            h.append(
                "<details class='disclosure'><summary>Original proposal &amp; approval changes</summary>"
                + f"<p>Original proposed annual EBITDA: <strong>{money(plan.plan['total_run_rate_ebitda_base'])}</strong>; in-year: <strong>{money(plan.plan['total_in_year_ebitda_base'])}</strong>. Executive figures show approved scope only.</p></details>"
            )
        if p.get("excluded_opportunities"):
            titles = {o.opportunity_id: o.title for o in opps}
            h.append(
                "<details class='disclosure'><summary>Excluded opportunities</summary>"
                + _list(
                    [
                        f"{x.get('title') or titles.get(x.get('opportunity_id'), 'Opportunity')}: {x.get('reason', 'No reason recorded')}"
                        for x in p["excluded_opportunities"]
                    ]
                )
                + "</details>"
            )
    else:
        included = set()
        pause = run.state.get("pause_reason") or {}
        h.append(
            f"<section id='executive' class='panel empty-state'><span class='page-icon'>{icon('alert')}</span><p class='eyebrow'>Controlled review boundary</p><h2>Evidence before commitment</h2><p>A decision-ready plan is not available. No modeled financial result is shown until the workflow can support it.</p>"
        )
        if pause.get("detail"):
            h.append(f"<p>{_e(pause['detail'])}</p>")
        h.append(
            "<p>Review the evidence requirements below, supply the missing source data, then resume the diagnostic through the authorized workflow.</p></section><section id='workstreams'><div class='block-head'><div><p class='eyebrow'>100-day implementation</p><h2>Execution plan</h2></div></div><p class='empty-state'>Workstreams will appear once a plan is ready for review.</p></section>"
        )
    suspicious = [f for f in findings if f.finding_type.value == "suspicious_content"]
    if suspicious:
        h.append(
            "<section class='alert warning'><h2>Source integrity requires review</h2><p>Suspicious content was treated as data and not followed.</p>"
            + _list([f"{f.title.rstrip('.:')}. {f.statement}" for f in suspicious])
            + "</section>"
        )
    if gaps:
        h.append(
            "<section class='panel record-card gap-card'><div class='record-head'><div class='record-title'>"
            f"<span class='record-num warn' aria-hidden='true'>{icon('alert')}</span><div><p class='eyebrow'>Diligence limitations</p><h2>Data gaps &amp; required evidence</h2></div></div>"
            f"<span class='count'>{len(gaps)}</span></div>"
            + _list([f"{f.title.rstrip('.:')}. {f.statement}" for f in gaps])
            + "</section>"
        )
    h.append(
        f"<section id='evidence'><div class='block-head'><div><p class='eyebrow'>Analytical diligence · {_e(units)}</p><h2>Value cases and evidence</h2>"
        "<p>Select a value case to inspect its scenarios, costs, input assumptions and source evidence. Values outside the displayed plan are not included in its totals.</p></div></div>"
    )
    ranked = sorted(
        opps,
        key=lambda o: cases[o.opportunity_id].annual_ebitda_base if o.opportunity_id in cases else Decimal(0),
        reverse=True,
    )
    if ranked:
        h.append(
            _selected_rows([o.opportunity_id for o in ranked])
            + "<div class='split'><div class='table-card'><div class='table-toolbar'><div class='toolbar-title'>"
            f"{icon('value')}<h3>Value cases</h3><span class='count'>{len(ranked)}</span></div>"
            f"<div class='toolbar-meta'><span>{len([o for o in ranked if o.opportunity_id in included])} in plan</span><span>Ranked by base annual EBITDA</span></div></div>"
            "<div class='table-wrap' tabindex='0' role='region' aria-label='Value cases'><table class='data-table case-table'>"
            f"<thead><tr><th scope='col'><span class='th-label'>{icon('file')}Value case</span></th>"
            f"<th scope='col'><span class='th-label'>{icon('status')}Scope</span></th>"
            f"<th scope='col' class='num'><span class='th-label'>{icon('value')}Base annual EBITDA</span></th>"
            "<th scope='col' class='row-chevron'><span class='sr-only'>Open</span></th></tr></thead><tbody>"
            + "".join(_case_row(o, cases.get(o.opportunity_id), o.opportunity_id in included) for o in ranked)
            + "</tbody></table></div></div><div class='detail-stack'>"
            + "".join(_case(o, cases.get(o.opportunity_id), o.opportunity_id in included) for o in ranked)
            + "</div></div>"
        )
    else:
        h.append("<div class='empty-state'>No sized value cases are available for this diagnostic.</div>")
    h.append(
        "</section>" + _decision(run, plan, approval, csrf, can_decide, error, rationale, selected_initiatives or [])
    )
    h.append(
        "<details class='disclosure'><summary>Workflow &amp; audit identifiers</summary><dl class='definition-list'>"
        + f"<div><dt>Workflow status</dt><dd><code>{_e(run.status.value)}</code></dd></div>"
        + f"<div><dt>Company</dt><dd><code>{_e(run.company_id)}</code></dd></div><div><dt>Run</dt><dd><code>{_e(run.run_id)}</code></dd></div><div><dt>Current step</dt><dd>{label(run.current_step) if run.current_step else ('Not started' if run.status == Status.PENDING else 'None')}</dd></div><div><dt>Reference date</dt><dd>{_e(run.reference_date or 'Not specified')}</dd></div>"
        + (f"<div><dt>Plan</dt><dd><code>{_e(plan.plan_id)}</code></dd></div>" if plan else "")
        + "</dl></details>"
    )
    return page(f"{name} · Plan review", "".join(h))


def _kpi_card(d: KpiDefinition, history: list[KpiObservation]) -> str:
    measured = [o for o in history if covers_plan_period(d, o)]
    latest = measured[-1] if measured else None
    h = [
        "<article class='panel record-card kpi-card'><div class='record-head'><div class='record-title'>",
        f"<span class='record-num' aria-hidden='true'>{icon('activity')}</span><div>",
        f"<h3>{_e(d.description)}</h3><p class='record-sub'><span>{label(d.metric)}</span>"
        f"<span>{icon('calendar')}Every {d.cadence_days} days</span></p></div></div>",
        status_badge(latest.status) if latest else "<span class='badge'>Awaiting post-plan data</span>",
        "</div><div class='metric-comparison'>",
    ]
    for name, value in [
        ("Baseline", d.baseline),
        ("Latest post-plan reading", latest.value if latest else None),
        ("Day-100 target", d.day_100_target),
        ("Run-rate target", d.run_rate_target),
    ]:
        h.append(
            f"<div><span class='metric-label'>{name}</span><strong class='metric-value'>{_metric(d.metric, value) if value is not None else 'None yet'}</strong></div>"
        )
    h.append("</div><div class='kpi-progress'>")
    if latest:
        move = d.run_rate_target - d.baseline
        if move:
            progress = (latest.value - d.baseline) / move * 100
            width = max(Decimal(0), min(Decimal(100), progress))
            h.append(
                f"<div class='progress-track' aria-hidden='true'><div class='progress-fill' style='--value:{width:.2f}%;width:{width:.2f}%'></div></div><p class='metric-note'><strong>{progress:,.1f}% of the baseline-to-run-rate movement</strong> · {'Lower' if d.direction == 'decrease' else 'Higher'} is better. Progress may be negative or exceed 100%; the bar is bounded for display.</p>"
            )
        else:
            h.append(
                "<p class='metric-note'>The run-rate target equals baseline. No improvement percentage is calculated.</p>"
            )
        h.append(
            f"<p class='metric-note'>Observed {_e(latest.observed_at.strftime('%d %b %Y · %H:%M UTC'))} · Source period {_e(latest.period_end or 'not specified')} · Target for this observation: <strong>{_metric(d.metric, latest.target)}</strong>. Status uses the policy tolerance against that dated target.</p>"
        )
    else:
        h.append(
            "<p class='empty-state'>No reading covers a period after the plan started. Approval establishes a target; "
            "it does not establish realized impact.</p>"
        )
    h.append(
        "</div><details class='disclosure'><summary>Observation history &amp; measurement provenance</summary>"
        + f"<p class='metric-note'>Plan starts {_e(d.start_date)} · Source {_e(d.source)} · {'Active' if d.active else 'Inactive'} definition</p>"
        + _evidence(d.evidence_ids, d.run_id)
    )
    if history:
        h.append(
            "<div class='table-wrap' tabindex='0' role='region' aria-label='Recorded KPI observations'><table class='data-table'><caption>Recorded observations, most recent first</caption><thead><tr><th scope='col'>Observed / source period</th><th scope='col'>Actual</th><th scope='col'>Dated target</th><th scope='col'>Status</th><th scope='col'>Evidence</th></tr></thead><tbody>"
        )
        for o in reversed(history):
            badge = (
                status_badge(o.status) if covers_plan_period(d, o) else "<span class='badge'>Pre-plan reading</span>"
            )
            h.append(
                f"<tr><th scope='row'>{_e(o.observed_at.strftime('%d %b %Y %H:%M UTC'))}<small>{_e(o.period_end or 'Period not specified')}</small></th><td>{_metric(d.metric, o.value)}</td><td>{_metric(d.metric, o.target)}</td><td>{badge}</td><td>{_evidence(o.evidence_ids, d.run_id)}</td></tr>"
            )
        h.append("</tbody></table></div>")
    h.append(
        f"<p class='metric-note'>KPI <code>{_e(d.kpi_id)}</code> · Plan <code>{_e(d.plan_id)}</code></p></details></article>"
    )
    return "".join(h)


def kpi_page(
    company_id: str,
    defs: list[KpiDefinition],
    obs: list[KpiObservation],
    *,
    company_name: str | None = None,
    currency: str | None = None,
    include_inactive: bool = False,
) -> str:
    name = company_name or unescape(label(company_id))
    by: dict[str, list[KpiObservation]] = {}
    for o in sorted(obs, key=lambda o: o.observed_at):
        if o.company_id == company_id:
            by.setdefault(o.kpi_id, []).append(o)
    groups: dict[tuple[str, str], list[KpiDefinition]] = {}
    for d in sorted(defs, key=lambda d: d.created_at, reverse=True):
        if d.company_id == company_id and (d.active or include_inactive):
            groups.setdefault((d.plan_id, d.run_id), []).append(d)
    h = [
        page_header(
            name,
            crumbs=[("Portfolio", "/"), ("Operating performance", None)],
            eyebrow="<p class='eyebrow'>Operating performance / Plan versus actual</p>",
            subtitle="From approved initiatives to measurable operating outcomes.",
            symbol="activity",
            actions="<a class='button secondary' href='/'>Portfolio overview</a>",
        )
    ]
    if not groups:
        h.append(
            "<section class='panel empty-state'><h2>No approved KPIs for this company</h2><p>Approve a measurable plan to establish its baseline, day-100 targets and monitoring cadence. No realized results are implied.</p></section>"
        )
    for index, ((plan_id, run_id), definitions) in enumerate(groups.items()):
        if index:
            h.append(
                f"<details class='disclosure'><summary>Earlier plan · {_e(definitions[0].start_date)} · Run {_e(run_id[:8])}</summary>"
            )
        measured = {d.kpi_id: [o for o in by.get(d.kpi_id, []) if covers_plan_period(d, o)] for d in definitions}
        latest = [m[-1] for m in measured.values() if m]
        off = sum(o.status == "off_track" for o in latest)
        plan_label = (
            "Selected approved plan"
            if include_inactive
            else ("Most recently activated plan" if index == 0 else "Earlier plan")
        )
        h.append(
            f"<section class='scorecard'><div class='block-head'><div><p class='eyebrow'>{plan_label} · {_e(currency or 'Currency metrics use source units')}</p><h2>Operating scorecard</h2><p class='metric-note'>Start {_e(definitions[0].start_date)} · Plan <code>{_e(plan_id[:8])}</code> · Run <code>{_e(run_id[:8])}</code></p></div><a class='button secondary' href='/runs/{_e(run_id)}/review'>View approved plan &rarr;</a></div><div class='summary-strip'>"
        )
        h.append(
            _card(
                "Measures in this plan", str(len(definitions)), "Each KPI remains tied to its own approved run", "hash"
            )
        )
        h.append(_card("On track", str(len(latest) - off), "Latest post-plan reading versus its dated target", "check"))
        h.append(_card("Requires attention", str(off), "Latest post-plan readings outside policy tolerance", "alert"))
        h.append(
            _card(
                "Awaiting measurement",
                str(len(definitions) - len(latest)),
                "No reading yet for a period after the plan started",
                "calendar",
            )
        )
        h.append("</div><div class='stack records'>")
        for d in definitions:
            h.append(_kpi_card(d, by.get(d.kpi_id, [])))
        h.append("</div></section>")
        if index:
            h.append("</details>")
    if len(groups) > 1:
        h.append(
            "<p class='metric-note'>Multiple approved diagnostic runs exist. Their targets and observations are shown separately; repeated runs are not aggregated as additional business impact.</p>"
        )
    return page(f"{name} · Operating performance", "".join(h))
