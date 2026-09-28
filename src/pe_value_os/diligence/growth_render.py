"""Executive growth exhibit with inspectable evidence and separate analyst judgments."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from html import escape
from typing import Any

from ..research.render import table
from .growth import GrowthContext
from .models import FactBundle


def render_growth(bundle: FactBundle, report: dict[str, Any]) -> str:
    context = GrowthContext.model_validate(report["context"])
    bundle.require_public()
    context.revenue_mix.require_public()
    source = next(d for d in bundle.documents if d.document_id == context.document_id)
    million = Decimal(1000000)
    resolution = Decimal(str(report["display_resolution"]))

    def rounded(value: Any) -> str:
        # Quantize to the disclosed increment, including non-power-of-ten resolutions.
        number = Decimal(str(value))
        number = (number / resolution).quantize(Decimal(1), rounding=ROUND_HALF_UP) * resolution / million
        decimals = max(0, -int((resolution / million).normalize().as_tuple().exponent))
        return f"{number:,.{decimals}f}"

    def pct(value: Any) -> str:
        return "Unavailable" if value is None else f"{Decimal(str(value)) * 100:.1f}%"

    def refs(ids: tuple[str, ...]) -> str:
        return " · ".join(f"<a href='#growth-{escape(i, quote=True)}'>{escape(i)}</a>" for i in dict.fromkeys(ids))

    acquired = escape(context.acquired_business)
    body = (
        "<section class='panel' id='growth'><p class='eyebrow'>Commercial diligence / Acquisition and mix</p>"
        "<h2>Separate acquired revenue from the remaining change</h2>"
        f"<p>{escape(report['prior_period']['end'])} to {escape(report['current_period']['end'])} · "
        f"{escape(report['currency'])} millions · contribution and residual figures are approximate.</p>"
        "<div class='metrics-grid' style='grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))'>"
    )
    for label, value, note in (
        ("Reported revenue change", report["reported_change"], "Total change across the consolidated business"),
        (
            f"{context.acquired_business} contribution change",
            report["acquired_change"],
            "Difference in included revenue; not acquired-business growth",
        ),
        (
            f"Remaining change excluding {context.acquired_business}",
            report["residual_change"],
            "Includes FX, other acquisitions, mix and timing",
        ),
    ):
        body += f"<div class='metric-card'><span class='metric-label'>{escape(label)}</span><strong class='metric-value'>{rounded(value)}</strong><span class='metric-note'>{escape(note)}</span></div>"
    body += "</div>" + table(
        ["Bridge", "Prior year", "Current year", "Change", "Interpretation"],
        [
            [
                "Reported consolidated revenue",
                rounded(report["reported_prior"]),
                rounded(report["reported_current"]),
                rounded(report["reported_change"]),
                pct(report["reported_growth"]) + " calculated reported growth",
            ],
            [
                acquired + " included revenue",
                rounded(report["acquired_prior"]),
                rounded(report["acquired_current"]),
                rounded(report["acquired_change"]),
                "Rounded acquisition contribution disclosures",
            ],
            [
                "Revenue less that contribution",
                rounded(report["residual_prior"]),
                rounded(report["residual_current"]),
                rounded(report["residual_change"]),
                "Approximately " + pct(report["residual_growth"]) + "; not organic growth",
            ],
        ],
        "Central-value subtraction using disclosed rounded inputs. Each column reconciles before presentation rounding.",
    )
    body += (
        "<p><strong>Organic growth remains unavailable.</strong> The residual is a diligence signal, not a measure "
        "of organic performance or a savings pool. There is no exact dollar FX bridge from rounded constant-currency percentages.</p>"
        f"<p>{escape(report['precision_note'])} Source: {refs((context.prior.evidence_id, context.current.evidence_id))}.</p></section>"
    )
    mix_rows = []
    for period in report["revenue_mix"]:
        components = period["components"]
        mix_rows.append(
            [
                escape(str(period["end"])),
                *[
                    f"{Decimal(str(components[m]['amount'])) / million:,.3f} ({pct(components[m]['share'])})"
                    for m in (
                        "software_license_revenue",
                        "maintenance_revenue",
                        "saas_revenue",
                        "professional_services_revenue",
                    )
                ],
                f"{Decimal(str(period['total'])) / million:,.3f}",
            ]
        )
    body += (
        "<section class='panel' id='revenue-mix'><h2>Revenue models have different economics</h2>"
        + table(
            ["Year end", "Software licenses", "Maintenance", "SaaS", "Professional services", "Total"],
            mix_rows,
            "Reported revenue in millions; percentages calculated from each year's consolidated revenue. Components reconcile exactly at source precision.",
        )
        + "<p>SaaS revenue is a period flow, not ARR. Maintenance and license revenue cannot be converted into a subscription cohort or pricing headroom from this table. "
        "Use metric-specific peer definitions before comparing retention, growth or margins.</p><details><summary>Inspect revenue-disaggregation source rows</summary>"
        + table(
            ["Metric", "Period", "Source row", "Source"],
            [
                [
                    escape(f.metric),
                    escape(f.column_label),
                    escape(f.source_row),
                    f"<a href='{escape(str(source.url), quote=True)}#page={f.pdf_page}'>Page {escape(f.printed_page)}</a>",
                ]
                for f in context.revenue_mix.facts
            ],
            "A separate extraction and mapping hash preserve the original financial registry unchanged.",
        )
        + "</details></section>"
    )
    body += (
        "<section class='panel' id='research-decisions'><p class='eyebrow'>Research judgment / No operating approval</p>"
        "<h2>What the evidence changes</h2><p>These are authored research assessments. They do not approve an intervention, "
        "assign company staff or establish financial value.</p>"
    )
    for assessment in context.assessments:
        body += (
            f"<article><h3>{escape(assessment.question)}</h3><p><strong>{escape(assessment.disposition.capitalize())}</strong> · "
            f"{escape(assessment.rationale)}</p><p><strong>Mechanism and population:</strong> {escape(assessment.mechanism)} "
            f"{escape(assessment.population)}</p><p><strong>Supporting context:</strong> {refs(assessment.supporting_evidence_ids)}. "
            f"<strong>Counterevidence / limits:</strong> {refs(assessment.counterevidence_ids)}.</p>"
            f"<p><strong>Alternative explanations:</strong> {escape('; '.join(assessment.alternative_explanations))}.</p>"
            f"<p><strong>Evidence needed:</strong> {escape('; '.join(assessment.evidence_needed))}.</p>"
            f"<p><strong>Test that changes the decision:</strong> {escape(assessment.falsification_or_reopen_test)}</p>"
            f"<p class='muted'>Research author assessment · review by {assessment.review_by} · "
            f"ID {escape(assessment.assessment_id)}</p></article>"
        )
    body += "</section><section class='panel' id='growth-evidence'><h2>Disclosure evidence and limits</h2>"
    for item in context.disclosures:
        body += (
            f"<article id='growth-{escape(item.evidence_id, quote=True)}'><h3>{escape(item.locator)}</h3>"
            f"<p>{escape(item.reported_summary)}</p><p><strong>Analytical limit:</strong> {escape(item.analytical_limit)}</p>"
            f"<p><a href='{escape(str(source.url), quote=True)}#page={item.pdf_page}'>Filing page {item.pdf_page}</a> · "
            f"{escape(item.classification.replace('_', ' '))} · {escape(item.evidence_id)}</p></article>"
        )
    body += (
        f"<p class='muted'>Growth analysis {escape(report['analysis_version'])} · Context SHA-256 <code>{escape(report['context_sha256'])}</code>. "
        "Underlying disclosure values and reviewable research judgments are included in the companion JSON. "
        "Independent commercial review has not been performed.</p></section>"
    )
    return body
