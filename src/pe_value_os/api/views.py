"""Server-rendered pages for plan review (PVC-062) and KPI plan-vs-actual (PVC-124).

Plain HTML and CSS, no JavaScript. Every dynamic value is HTML-escaped; document text is never rendered.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from ..domain.kpi_models import KpiDefinition, KpiObservation
from ..domain.models import Finding
from ..domain.project_models import Opportunity, ValueCase
from ..domain.runs import ApprovalRecord, PlanRecord, RunRecord

CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2f5d50;--warn:#9a5b00;--bad:#9b2c2c;
--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#a3a39d;--line:#34332f;--accent:#7fb8a4;
--warn:#e0a84a;--bad:#e27b7b;--card:#1e1e1c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;
margin:28px 0 8px}.muted{color:var(--muted)}table{width:100%;border-collapse:collapse;margin:8px 0;
font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);
vertical-align:top}th{font-weight:600;font-size:13px;color:var(--muted)}td.num{text-align:right}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:12px 0}
.warn{color:var(--warn)}.bad{color:var(--bad)}.pill{display:inline-block;padding:1px 8px;border-radius:10px;
border:1px solid var(--line);font-size:12px}form label{display:block;margin:6px 0}textarea{width:100%;
min-height:80px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px}
button{background:var(--accent);color:#fff;border:0;border-radius:6px;padding:8px 14px;font-weight:600;
margin-right:8px;cursor:pointer}button.secondary{background:transparent;color:var(--fg);border:1px solid var(--line)}
.scroll{overflow-x:auto}
"""


def _money(v: Any) -> str:
    try:
        return f"{Decimal(str(v)):,.0f}"
    except (InvalidOperation, ValueError):
        return escape(str(v))


def page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{CSS}</style>"
            f"</head><body><main>{body}</main></body></html>")


def review_page(run: RunRecord, plan: PlanRecord | None, opps: list[Opportunity], cases: dict[str, ValueCase],
                findings: list[Finding], approval: ApprovalRecord | None, csrf: str, can_decide: bool) -> str:
    h = [f"<h1>Plan review</h1><p class='muted'>Company <b>{escape(run.company_id)}</b> · run "
         f"<code>{escape(run.run_id)}</code> · status <span class='pill'>{escape(run.status.value)}</span></p>"]
    suspicious = [f for f in findings if f.finding_type.value == "suspicious_content"]
    if suspicious:
        h.append("<div class='card warn'><b>Suspicious content was found in source documents.</b> It was treated as "
                 "data and not followed. Review before approving:<ul>"
                 + "".join(f"<li>{escape(f.title)}: {escape(f.statement)}</li>" for f in suspicious) + "</ul></div>")
    if plan:
        p = plan.plan
        h.append(f"<div class='card'><b>Total base-case run-rate EBITDA:</b> {_money(p['total_run_rate_ebitda_base'])}"
                 f" &nbsp; <b>In-year:</b> {_money(p['total_in_year_ebitda_base'])} "
                 "<span class='muted'>(sum of deterministic value cases; in-year reflects start month and ramp)</span>"
                 "</div>")
        if p.get("narrative"):
            h.append(f"<p>{escape(p['narrative'])}</p>")
        for ws in p["workstreams"]:
            rows = "".join(
                f"<tr><td>{escape(i['title'])}</td><td>{escape(i['classification'])}</td>"
                f"<td class='num'>{_money(i['run_rate_ebitda_base'])}</td>"
                f"<td class='num'>{_money(i['in_year_ebitda_base'])}</td>"
                f"<td>{'<br>'.join(escape(r) for r in i['requires_approval_reasons'])}</td></tr>"
                for i in ws["initiatives"])
            kpis = "".join(
                f"<tr><td>{escape(k['description'])}</td><td class='num'>{escape(str(k['baseline']))}</td>"
                f"<td class='num'>{escape(str(k['day_100_target']))}</td>"
                f"<td class='num'>{escape(str(k['run_rate_target']))}</td><td>{escape(k['direction'])}</td></tr>"
                for k in ws["kpis"])
            h.append(f"<h2>{escape(ws['name'])} <span class='muted'>· owner {escape(ws['owner_role'])}</span></h2>"
                     "<div class='scroll'><table><tr><th>Initiative</th><th>Type</th><th>Run-rate EBITDA</th>"
                     f"<th>In-year</th><th>Requires approval</th></tr>{rows}</table></div>"
                     "<div class='scroll'><table><tr><th>KPI</th><th>Baseline</th><th>Day-100 target</th>"
                     f"<th>Run-rate target</th><th>Direction</th></tr>{kpis}</table></div>")
            if ws["dependencies"]:
                h.append("<p class='muted'>Dependencies: " + "; ".join(escape(d) for d in ws["dependencies"]) + "</p>")
        if p.get("excluded_opportunities"):
            h.append("<h2>Excluded</h2><ul>" + "".join(
                f"<li>{escape(x.get('title', ''))}: {escape(x.get('reason', ''))}</li>"
                for x in p["excluded_opportunities"]) + "</ul>")
    h.append("<h2>Value cases and evidence</h2><div class='scroll'><table><tr><th>Opportunity</th><th>Baseline</th>"
             "<th>Base rates</th><th>Flow-through</th><th>Low / base / high</th><th>Confidence</th><th>Evidence</th></tr>")
    for o in opps:
        vc = cases.get(o.opportunity_id)
        ev = " ".join(f"<a href='/evidence/{escape(e)}'>{escape(e[:8])}</a>" for e in o.evidence_ids)
        h.append(
            f"<tr><td>{escape(o.title)}<br><span class='muted'>{escape(o.rationale)}</span></td>"
            f"<td class='num'>{escape(o.baseline_metric)}<br>{_money(o.baseline_value)}</td>"
            f"<td class='num'>{escape(str(o.base.improvement_rate))} × {escape(str(o.base.realization_rate))}</td>"
            f"<td class='num'>{escape(str(o.ebitda_flow_through))}</td>"
            f"<td class='num'>{_money(vc.annual_ebitda_low) if vc else '-'} / {_money(vc.annual_ebitda_base) if vc else '-'}"
            f" / {_money(vc.annual_ebitda_high) if vc else '-'}</td><td>{escape(o.confidence.value)}</td><td>{ev}</td></tr>")
    h.append("</table></div>")
    gaps = [f for f in findings if f.finding_type.value == "data_gap"]
    if gaps:
        h.append("<h2>Data gaps</h2><ul>" + "".join(f"<li>{escape(f.title)}: {escape(f.statement)}</li>" for f in gaps)
                 + "</ul>")
    if approval and approval.decision is None and plan:
        if can_decide:
            boxes = "".join(
                f"<label><input type='checkbox' name='remove_initiatives' value='{escape(i['opportunity_id'])}'> "
                f"Remove: {escape(i['title'])}</label>" for ws in plan.plan["workstreams"] for i in ws["initiatives"])
            h.append(
                f"<h2>Decision</h2><form method='post' action='/runs/{escape(run.run_id)}/approvals/form' class='card'>"
                f"<input type='hidden' name='csrf' value='{escape(csrf)}'>{boxes}"
                "<label>Rationale (required to reject or request changes)<textarea name='rationale'></textarea></label>"
                "<button name='decision' value='approved'>Approve</button>"
                "<button class='secondary' name='decision' value='changes_requested'>Request changes</button>"
                "<button class='secondary' name='decision' value='rejected'>Reject</button></form>")
        else:
            h.append("<p class='muted'>You can view this plan but only a human approver can decide.</p>")
    elif approval and approval.decision is not None:
        h.append(f"<div class='card'>Decided <b>{escape(approval.decision.value)}</b> by {escape(approval.decided_by or '')}"
                 f" · {escape(approval.rationale or '')}</div>")
    return page("Plan review", "".join(h))


def kpi_page(company_id: str, defs: list[KpiDefinition], obs: list[KpiObservation]) -> str:
    by: dict[str, list[KpiObservation]] = {}
    for o in obs:
        by.setdefault(o.kpi_id, []).append(o)
    h = [f"<h1>KPIs · {escape(company_id)}</h1><p class='muted'>Plan versus actual from approved plans.</p>"]
    for d in defs:
        rows = "".join(
            f"<tr><td>{escape(o.observed_at.date().isoformat())}</td><td class='num'>{escape(str(o.value))}</td>"
            f"<td class='num'>{escape(str(o.target))}</td><td class='{'bad' if o.status == 'off_track' else ''}'>"
            f"{escape(o.status)}</td></tr>" for o in by.get(d.kpi_id, []))
        h.append(f"<h2>{escape(d.description)}</h2><p class='muted'>Baseline {escape(str(d.baseline))} · day-100 "
                 f"{escape(str(d.day_100_target))} · run-rate {escape(str(d.run_rate_target))} ({escape(d.direction)})"
                 "</p><div class='scroll'><table><tr><th>Observed</th><th>Actual</th><th>Target</th><th>Status</th></tr>"
                 f"{rows or '<tr><td colspan=4 class=muted>No observations yet</td></tr>'}</table></div>")
    if not defs:
        h.append("<p>No approved KPIs for this company.</p>")
    return page(f"KPIs {company_id}", "".join(h))
