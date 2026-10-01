"""Executive exhibit of a real acquisition disclosure revision and its time limits."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from ..research.render import table
from .exhibit_style import exhibit_page
from .vintages import AllocationHistory, analyze_vintages


def render_vintages(report: dict[str, Any], json_name: str) -> str:
    history = report["history"]
    net_change = next(Decimal(row["change"]) for row in report["comparison"] if row["metric"] == "net_assets")
    body = (
        "<section class='hero'><div><p class='eyebrow'>Progress Software / Public disclosure history</p>"
        "<h1>Preserve what the earlier filing said</h1>"
        "<p class='page-subtitle'>ShareFile: provisional allocation to final acquisition accounting.</p>"
        "<p>Compare two annual filings without replacing the original. This is a measurement-period adjustment, "
        "not evidence of an accounting-error restatement.</p></div>"
        "<aside class='hero-aside'><span class='metric-label'>Exact public-availability replay</span>"
        f"<strong class='metric-value'>{escape(report['point_in_time_claim'].replace('_', ' ').title())}</strong>"
        "<span class='metric-note'>Acceptance is recorded separately from publication.</span></aside></section>"
    )
    body += "<section class='panel' id='allocation'><h2>What changed in the allocation</h2>"
    body += table(
        ["Component", "Preliminary / USD millions", "Final / USD millions", "Change / USD millions"],
        [
            [escape(row["label"])] + [f"{Decimal(row[k]) / 1000000:,.3f}" for k in ("preliminary", "final", "change")]
            for row in report["comparison"]
        ],
        "Each allocation reconciles independently. Changes are final minus preliminary; liabilities retain their signs.",
    )
    body += (
        f"<p>{escape(history['revision_explanation'])} "
        f"<a href='{escape(history['explanation_url'], quote=True)}'>Issuer explanation</a> "
        f"({escape(history['explanation_locator'])}).</p></section>"
        "<section class='panel' id='judgment'><h2>What this changes in diligence</h2>"
        "<p><strong>Retain the original acquisition model and reopen its accounting assumptions.</strong> "
        "The revised customer-relationship allocation belongs in the amortization review; it is not a pricing gain. "
        "A goodwill revision supplies no operating EBITDA add-back. Acquisition-date working capital is not a "
        "collections outcome, and the allocation difference is not a realized investment return.</p>"
        f"<p>The total allocation changes by ${net_change / 1000000:,.3f} million. The issuer separately reports approximately $1.2 million "
        "paid in fiscal 2025. Their rounded agreement does not establish payment dates or a complete transaction cash bridge. "
        "Request the closing statement and settlement ledger before treating that difference as an exact cash schedule.</p>"
        "<p>This comparison adds historical context. It does not overwrite the public financial baseline, "
        "historical equity sensitivity or constructed operating forecasts.</p></section>"
        "<section class='panel' id='timing'><h2>Which filing can the selector use?</h2>"
        "<p>These are tests of the two registered SEC filings. Intermediate releases have not been surveyed. "
        "An acceptance cutoff can select an accepted filing; it cannot certify that an investor could read it at that instant.</p>"
    )
    rows = []
    for row in report["cutoffs"]:
        selection = row["acceptance_selection"]
        selected = selection.get("selected")
        rows.append(
            [
                escape(row["cutoff"]),
                escape(selected["vintage_id"] if selected else "None eligible"),
                escape(row["publication_selection"]["status"].replace("_", " ")),
            ]
        )
    body += table(
        ["Cutoff / explicit UTC offset", "Acceptance-only selection", "Public-availability selection"],
        rows,
        "Later accepted filings never enter an earlier selection. Unknown publication evidence produces no selected facts.",
    )
    body += (
        f"<p>The <a href='{escape(history['timestamp_policy_url'], quote=True)}'>SEC timestamp guidance</a> "
        "distinguishes acceptance from website availability. No arbitrary delay is added to manufacture publication time. "
        "The full point-in-time and accounting-error-restatement acceptance criteria remain open.</p></section>"
        "<section class='panel' id='evidence'><h2>Inspect both source versions</h2>"
    )
    for vintage in history["vintages"]:
        doc = vintage["document"]
        body += (
            f"<details><summary>{escape(vintage['vintage_id'])} / {escape(vintage['status'])}</summary>"
            f"<p><a href='{escape(doc['url'], quote=True)}#page={vintage['pdf_page']}'>Issuer PDF, page {vintage['pdf_page']}</a> "
            f"· printed page {escape(vintage['printed_page'])} · accession {escape(doc['accession'])}.</p>"
            f"<p>Accepted {escape(vintage['accepted']['timestamp'])}; "
            f"<a href='{escape(vintage['accepted']['source_url'], quote=True)}'>SEC acceptance record</a>. "
            f"Retrieved {escape(doc['retrieved_at'])}; retrieval is not historical publication.</p>"
            f"<p>PDF SHA-256: <code>{escape(doc['sha256'])}</code></p>"
            + table(
                ["Source label", "Reported / USD thousands", "Extracted row"],
                [[escape(r["label"]), escape(r["reported_amount"]), escape(r["source_row"])] for r in vintage["rows"]],
                "Source amounts retain their original scale and row text.",
            )
            + "</details>"
        )
    body += "<h3>Limits retained</h3><ul>" + "".join(f"<li>{escape(x)}</li>" for x in report["limitations"]) + "</ul>"
    body += (
        f"<p><a href='{escape(json_name, quote=True)}' download>Download both vintages and cutoff results</a> · "
        "<a href='decision-memo.html'>Executive memo</a> · <a href='progress-baseline.html'>Public baseline</a></p></section>"
    )
    return exhibit_page(
        title="Progress Software — disclosure revision",
        kind="Disclosure history",
        provenance="Public filings",
        nav=[
            ("#allocation", "Allocation"),
            ("#judgment", "Judgment"),
            ("#timing", "Timing"),
            ("#evidence", "Evidence"),
        ],
        nav_label="Disclosure sections",
        body=body,
    )


def build_vintage_report(source: Path, output: Path) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if source.resolve() in {html_path.resolve(), json_path.resolve()}:
        raise ValueError("vintage output must not overwrite its source")
    report = analyze_vintages(AllocationHistory.model_validate_json(source.read_bytes()))
    html = render_vintages(report, json_path.name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return html_path
