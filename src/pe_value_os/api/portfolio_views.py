"""Executive portfolio, sign-in and evidence-room pages over scoped repository data."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from decimal import Decimal
from html import escape
from typing import Any
from urllib.parse import quote

from ..domain.models import EvidenceRef
from ..domain.runs import ApprovalRecord, PlanRecord, RunRecord
from ..domain.source_models import CompanyProfile
from .presentation import label, money, page, status_badge


def login_page(csrf: str, *, error: str | None = None) -> str:
    error_html = f"<div id='login-error' class='alert warning' role='alert'>{escape(error)}</div>" if error else ""
    described_by = "login-help login-error" if error else "login-help"
    return page(
        "Private equity operating workspace",
        "<section class='hero'><div class='hero-copy'><p class='eyebrow'>Portfolio operations</p>"
        "<h1 class='page-title'>Turn an investment thesis<br>into an operating plan.</h1>"
        "<p class='page-subtitle'>A decision workspace for operating partners. Prioritize the value at stake, "
        "challenge the assumptions, and put accountable execution behind every initiative.</p>"
        "<div class='action-list'><p><strong>01 / Underwrite the opportunity</strong><br>"
        "Compare downside, base and upside cases with traceable assumptions.</p>"
        "<p><strong>02 / Make the decision</strong><br>Approve, challenge or reshape an evidence-backed 100-day plan.</p>"
        "<p><strong>03 / Track execution</strong><br>Connect the approved plan to measurable operating KPIs.</p></div></div>"
        "<div class='hero-aside panel'><p class='eyebrow'>Review access</p><h2>Open your workspace</h2>"
        "<p class='muted'>Local showcase sign-in. This demonstration uses fictional portfolio companies.</p>"
        f"{error_html}<form method='post' action='/dev/login' class='stack'>"
        f"<input type='hidden' name='csrf' value='{escape(csrf)}'>"
        "<label for='token'>Local approver token</label>"
        f"<input id='token' name='token' class='input-field' type='password' required autocomplete='off' "
        f"aria-describedby='{described_by}'>"
        "<button type='submit' class='button'>Open workspace <span aria-hidden='true'>&rarr;</span></button>"
        "<p id='login-help' class='form-help'>Use the token printed by setup, or copy only its value from "
        "<code>var/local-showcase/settings.json</code>, without quotes.</p></form>"
        "<div class='divider'></div><p class='form-help'>Approvals belong to a human reviewer. "
        "Production access uses your identity provider; this token is for the local demonstration.</p></div></section>",
        active="login",
    )


def _plan_data(plan: PlanRecord | None) -> dict[str, Any] | None:
    if plan is None or plan.status in {"rejected", "superseded"}:
        return None
    return plan.approved_plan if plan.approved_plan is not None else plan.plan


def home_page(
    runs: list[RunRecord],
    *,
    dev: bool,
    companies: dict[str, CompanyProfile] | None = None,
    plans: dict[str, PlanRecord] | None = None,
    gaps: dict[str, int] | None = None,
    decisions: dict[str, ApprovalRecord] | None = None,
) -> str:
    companies, plans, gaps = companies or {}, plans or {}, gaps or {}
    decisions = decisions or {}

    def current_status(run: RunRecord) -> str:
        rec = decisions.get(run.run_id)
        if run.status.value == "awaiting_approval" and rec and rec.decision:
            return {
                "approved": "approval_recorded",
                "rejected": "rejection_recorded",
                "changes_requested": "revisions_queued",
            }[rec.decision.value]
        return run.status.value

    ordered = sorted(runs, key=lambda run: (run.created_at, run.run_id), reverse=True)
    latest: dict[str, RunRecord] = {}
    for run in ordered:
        latest.setdefault(run.company_id, run)
    current = list(latest.values())
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"annual": Decimal(0), "year": Decimal(0)})
    eligible = [run for run in current if run.status.value not in {"failed", "rejected", "needs_evidence"}]
    for run in eligible:
        data = _plan_data(plans.get(run.run_id))
        if data is not None:
            company = companies.get(run.company_id)
            currency = company.currency if company else f"Unspecified ({run.company_id})"
            totals[currency]["annual"] += Decimal(str(data["total_run_rate_ebitda_base"]))
            totals[currency]["year"] += Decimal(str(data["total_in_year_ebitda_base"]))
    # A newer assessment does not retire an earlier plan's approval request, so it still needs a decision.
    earlier_pending = [
        run
        for run in ordered
        if latest[run.company_id].run_id != run.run_id and run.status.value == "awaiting_approval"
    ]
    pending = sum(current_status(run) == "awaiting_approval" for run in current) + len(earlier_pending)
    blocked = sum(run.status.value in {"needs_evidence", "failed"} for run in current)
    total_html = (
        "".join(
            f"<div class='metric-value' data-metric='portfolio-run-rate-ebitda' data-currency='{escape(currency)}' data-value='{values['annual']}' title='{escape(currency)} {money(values['annual'])}'>"
            f"<small>{escape(currency)}</small> {money(values['annual'], compact=True)}</div>"
            f"<p class='metric-note'>In-year {escape(currency)} {money(values['year'], compact=True)}</p>"
            for currency, values in sorted(totals.items())
        )
        or "<div class='metric-value'>&mdash;</div><p class='metric-note'>No sized current plan yet</p>"
    )
    h = [
        "<header class='page-header'><div><p class='eyebrow'>Operating partner workspace</p>"
        "<h1 class='page-title'>Portfolio value creation</h1>"
        "<p class='page-subtitle'>Where to focus. What to underwrite. What happens next.</p></div>"
        "<a class='button secondary' href='#decisions'>Open decision desk &darr;</a></header>",
        "<section class='metrics-grid' aria-label='Current portfolio overview'>",
        f"<div class='metric-card'><p class='metric-label'>Portfolio companies</p><div class='metric-value'>{len(current)}</div>"
        "<p class='metric-note'>One current assessment per company</p></div>",
        f"<div class='metric-card highlight'><p class='metric-label'>Modeled annual EBITDA opportunity</p>{total_html}</div>",
        f"<div class='metric-card'><p class='metric-label'>Decisions required</p><div class='metric-value'>{pending}</div>"
        "<p class='metric-note'>Plans awaiting human approval</p></div>",
        f"<div class='metric-card'><p class='metric-label'>Needs attention</p><div class='metric-value'>{blocked}</div>"
        "<p class='metric-note'>Evidence gaps or interrupted assessments</p></div></section>",
        "<p class='form-help'>Opportunity totals include only each company's latest eligible plan; approved edits are "
        "reflected. Cases are sized independently; totals are not adjusted for overlap between initiatives. "
        "Separate currencies are never combined. These are modeled opportunities, not realized returns.</p>",
        "<section id='portfolio' class='stack'><div class='section-heading'><div><p class='eyebrow'>Portfolio coverage</p>"
        "<h2>Company priorities</h2></div><span class='muted'>Current assessments</span></div><div class='two-column'>",
    ]
    for run in current:
        profile = companies.get(run.company_id)
        company_name = profile.name if profile else run.company_id.replace("-", " ").title()
        plan = plans.get(run.run_id)
        data = _plan_data(plan)
        currency = profile.currency if profile else "Source currency"
        initials = "".join(word[0] for word in company_name.split()[:2])
        h.append(
            f"<article class='company-card'><div class='card-top'><span class='company-monogram' aria-hidden='true'>"
            f"{escape(initials)}</span>{status_badge(current_status(run))}</div><h3>{escape(company_name)}</h3>"
            f"<p class='muted'>{escape(profile.business_model if profile else 'Assessment in progress')}</p>"
        )
        if profile and profile.deal_thesis:
            h.append(f"<p>{escape(profile.deal_thesis)}</p>")
        if data is not None and run.status.value not in {"failed", "rejected", "needs_evidence"}:
            initiatives = [item for ws in data.get("workstreams", []) for item in ws.get("initiatives", [])]
            lead = max(initiatives, key=lambda i: Decimal(str(i["run_rate_ebitda_base"])), default=None)
            h.append(
                f"<p class='metric-label'>{'Approved' if plan and plan.status == 'approved' else 'Proposed'} annual opportunity</p>"
                f"<div class='metric-value'>{escape(currency)} {money(data['total_run_rate_ebitda_base'], compact=True)}</div>"
                f"<p class='metric-note'>{len(initiatives)} initiatives across {len(data.get('workstreams', []))} workstreams</p>"
            )
            if lead:
                h.append(f"<p><span class='eyebrow'>Primary value lever</span><br>{escape(lead['title'])}</p>")
        else:
            message = {
                "needs_evidence": "Resolve the data gaps before underwriting a value case.",
                "failed": "Inspect the interruption and recovery record before proceeding.",
                "rejected": "The reviewer declined this plan. The decision remains in the audit record.",
            }.get(run.status.value, "The assessment is collecting and analyzing evidence. Refresh to see progress.")
            h.append(f"<div class='empty-state'><p>{escape(message)}</p></div>")
        if gaps.get(run.run_id):
            h.append(f"<p class='form-help'>{gaps[run.run_id]} documented evidence gaps to consider.</p>")
        h.append(
            f"<div class='card-actions'><a class='button' href='/runs/{escape(run.run_id)}/review'>"
            f"{'Review evidence gaps' if run.status.value == 'needs_evidence' else 'Open investment memo'} &rarr;</a>"
            f"<a class='text-link' href='/companies/{quote(run.company_id, safe='')}/kpis?run_id={quote(run.run_id, safe='')}'>"
            "View KPIs</a></div>"
            f"<p class='form-help'>Assessment {escape(run.created_at.strftime('%d %b %Y, %H:%M UTC'))}</p></article>"
        )
    if not current:
        h.append(
            "<div class='empty-state'><h3>Your portfolio starts here</h3><p>No assessments are available to "
            "this account. Start a diagnostic through your MCP client or run the local showcase setup.</p></div>"
        )
    h.append(
        "</div></section><section id='decisions' class='panel'><div class='section-heading'>"
        "<div><p class='eyebrow'>Decision desk</p><h2>Your next actions</h2></div></div><div class='action-list'>"
    )
    actions = [run for run in current if current_status(run) in {"awaiting_approval", "needs_evidence", "failed"}]
    actions += earlier_pending
    for run in actions:
        profile = companies.get(run.company_id)
        action = "Review and decide" if run.status.value == "awaiting_approval" else "Resolve assessment blockers"
        earlier = f" · Earlier assessment of {run.created_at:%d %b %Y}" if run in earlier_pending else ""
        h.append(
            f"<div class='initiative-row'><div><strong>{escape(profile.name if profile else run.company_id)}</strong>"
            f"<p class='muted'>{label(run.status.value)}{earlier}</p></div>"
            f"<a class='text-link' href='/runs/{escape(run.run_id)}/review'>{action}</a></div>"
        )
    if not actions:
        h.append(
            "<p class='muted'>No outstanding decisions in the current assessments. Review approved-plan KPIs "
            "to track the next operating milestone.</p>"
        )
    h.append("</div></section>")
    history = [run for run in ordered if latest[run.company_id].run_id != run.run_id]
    if history:
        h.append(
            f"<details class='disclosure'><summary>Assessment history <span class='muted'>{len(history)} prior runs</span></summary>"
            "<p class='form-help'>Prior assessments are preserved for comparison and audit. They are excluded from the current portfolio totals.</p>"
            "<div class='table-wrap' tabindex='0' role='region' aria-label='Prior company assessments'><table class='data-table'><caption class='sr-only'>Prior company assessments</caption>"
            "<thead><tr><th scope='col'>Company</th><th scope='col'>Created</th><th scope='col'>Status</th>"
            "<th scope='col'>Record</th></tr></thead><tbody>"
        )
        for run in history[:50]:
            h.append(
                f"<tr><th scope='row'>{escape(companies[run.company_id].name if run.company_id in companies else run.company_id)}</th>"
                f"<td>{escape(run.created_at.strftime('%d %b %Y, %H:%M'))}</td><td>{status_badge(run.status.value)}</td>"
                f"<td><a href='/runs/{escape(run.run_id)}/review'>View assessment <span class='sr-only'>{escape(run.run_id)}</span></a></td></tr>"
            )
        h.append("</tbody></table></div></details>")
    if dev:
        h.append(
            "<p class='form-help'>Local development workspace &middot; company-scoped data &middot; human decision control.</p>"
        )
    return page("Portfolio value creation", "".join(h), active="portfolio")


def evidence_page(ev: EvidenceRef, content: bytes, *, company_name: str, run_id: str | None = None) -> str:
    filename = ev.source_uri.replace("\\", "/").rsplit("/", 1)[-1].split("?", 1)[0] or "Source document"
    back = f"/runs/{quote(run_id, safe='')}/review#evidence" if run_id else "/"
    text = content[:24000].decode("utf-8", errors="replace")
    h = [
        f"<p class='breadcrumb'><a href='{back}'>&larr; {'Investment memo' if run_id else 'Portfolio'}</a></p>"
        "<header class='page-header'><div><p class='eyebrow'>Evidence room</p>"
        f"<h1 class='page-title'>{escape(filename)}</h1><p class='page-subtitle'>{escape(company_name)} &middot; "
        f"{label(ev.source_type)}</p></div><a class='button secondary' href='/evidence/{quote(ev.evidence_id, safe='')}'>"
        "Open original source &rarr;</a></header>",
        "<section class='panel'><div class='section-heading'><h2>Source preview</h2>"
        f"<span class='muted'>{len(content):,} bytes</span></div>"
        "<p class='form-help'>Source content is presented as evidence, not as instructions. Preview is bounded; use the original source for the complete record.</p>",
    ]
    if filename.lower().endswith(".csv"):
        rows = []
        try:
            reader = csv.reader(io.StringIO(text))
            for _, row in zip(range(13), reader, strict=False):
                rows.append(row[:10])
        except csv.Error:
            rows = []
        if rows:
            h.append(
                "<div class='table-wrap' tabindex='0' role='region' aria-label='Evidence data preview'><table class='data-table'><caption>First 12 data rows, up to 10 columns</caption><thead><tr>"
                + "".join(f"<th scope='col'>{escape(cell[:160])}</th>" for cell in rows[0])
                + "</tr></thead><tbody>"
            )
            for row in rows[1:]:
                h.append("<tr>" + "".join(f"<td>{escape(cell[:160])}</td>" for cell in row) + "</tr>")
            h.append("</tbody></table></div>")
        else:
            h.append(
                f"<pre class='source-preview' tabindex='0' aria-label='Evidence text preview'>{escape(text[:12000])}</pre>"
            )
    else:
        h.append(
            f"<pre class='source-preview' tabindex='0' aria-label='Evidence text preview'>{escape(text[:12000])}</pre>"
        )
    h.append(
        "</section><details class='disclosure'><summary>Provenance and verification details</summary>"
        f"<dl class='meta-list'><dt>Evidence identifier</dt><dd><code>{escape(ev.evidence_id)}</code></dd>"
        f"<dt>Retrieved</dt><dd>{escape(ev.retrieved_at.isoformat())}</dd>"
        f"<dt>Source as of</dt><dd>{escape(ev.as_of.isoformat()) if ev.as_of else 'Not supplied'}</dd>"
        f"<dt>Stored content fingerprint</dt><dd><code>{escape(ev.content_hash)}</code></dd></dl></details>"
    )
    return page("Evidence room", "".join(h), active="evidence")
