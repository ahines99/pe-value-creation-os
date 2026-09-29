"""Render public application captures in an isolated Playwright test container.

Usage: python scripts/check_portfolio_browser.py /site /artifacts
Requires Playwright with Chromium. Does not access a user's desktop or live session.
"""

from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    site = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    pages = {
        "landing": "/index.html",
        "workspace": "/portfolio/examples/workspace.html",
        "memo": "/portfolio/examples/beacon-pricing.html",
        "gaps": "/portfolio/examples/delta-broken.html",
        "performance": "/portfolio/examples/beacon-kpis.html",
        "evidence": "/portfolio/examples/3413f120-7216-53d2-a489-ea9bad040e76.html",
        "public-baseline": "/portfolio/progress-baseline.html",
        "underwriting": "/portfolio/underwriting.html",
        "operating-plan": "/portfolio/operating-plan.html",
        "case-history": "/portfolio/case-history.html",
        "realization": "/portfolio/realization.html",
        "execution": "/portfolio/execution.html",
        "operating-sources": "/portfolio/operating-sources.html",
        "source-review": "/portfolio/source-review.html",
        "decision-memo": "/portfolio/decision-memo.html",
        "historical-valuation": "/portfolio/historical-valuation.html",
        "disclosure-history": "/portfolio/disclosure-history.html",
        "exit-review": "/portfolio/exit-review.html",
        "lineage-review": "/portfolio/lineage-review.html",
    }
    findings: list[dict[str, object]] = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        for width in (1440, 768, 375):
            context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
            context.route(
                "**/*", lambda route: route.continue_() if route.request.url.startswith(base) else route.abort()
            )
            for name, path in pages.items():
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                response = page.goto(base + path)
                assert response and response.status == 200, path
                page.wait_for_load_state("networkidle")
                dimensions = page.evaluate(
                    "({viewport:innerWidth, width:document.documentElement.scrollWidth, "
                    "height:document.documentElement.scrollHeight})"
                )
                assert dimensions["width"] <= width, (name, width, dimensions)
                assert not errors, (name, errors)
                page.keyboard.press("Tab")
                focused = page.locator(":focus")
                assert focused.count() == 1 and "Skip to content" in focused.inner_text(), name
                page.keyboard.press("Enter")
                assert page.locator("main").evaluate(
                    "e => e.contains(document.activeElement) || e === document.activeElement"
                ), name
                page.goto(base + path)
                if width in (1440, 375):
                    page.screenshot(path=str(output / f"{name}-{width}.png"))
                disclosures = page.locator("details")
                for index in range(disclosures.count()):
                    item = disclosures.nth(index)
                    if item.is_visible() and not item.evaluate("e => e.open"):
                        summary = item.locator(":scope > summary")
                        summary.focus()
                        page.keyboard.press("Enter")
                        assert item.evaluate("e => e.open"), (name, index)
                expanded = page.evaluate("document.documentElement.scrollWidth")
                assert expanded <= width, (name, width, "expanded overflow", expanded)
                if name == "memo" and width == 1440:
                    page.locator("#evidence").screenshot(path=str(output / "memo-evidence-detail.png"))
                if name == "execution":
                    assert (
                        "Completed, accepted and permitted are different states"
                        in page.locator("#decision").inner_text()
                    )
                    assert "whole-month support" in page.locator("#challenge").inner_text()
                    assert "Withdraw unsupported vendor acceptance" in page.locator("#challenge").inner_text()
                    assert "delivery support invalidated" in page.locator("#claims").inner_text()
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert sum(t["acceptance_valid"] for t in payload["execution"]["final"]["tasks"]) == 6
                    assert [c["delivery_support_valid"] for c in payload["execution"]["final"]["claim_links"]] == [
                        True,
                        True,
                        False,
                    ]
                    assert payload["submitted_periods"] == 5 and payload["actual_company_realized_value"] is None
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#challenge").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"execution-challenges-{width}.png"))
                if name == "realization":
                    assert "Cash improvement is not earnings delivery" in page.locator("#decision").inner_text()
                    assert "-16,000" in page.locator("#comparison").inner_text()
                    assert "118,000" in page.locator("#comparison").inner_text()
                    assert "nov-close-v2" in page.locator("#correction").inner_text()
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert payload["submitted_periods"] == payload["eligible_periods"] == 3
                    assert (
                        payload["aggregate_recorded_periods"]["attributed_difference"]["incremental_ebitda"] == "-32000"
                    )
                    assert payload["actual_company_realized_value"] is None and payload["human_review_count"] == 0
                    assert payload["transitions"][2]["before_new_claims"] == "unassigned"
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#comparison").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"realization-comparison-{width}.png"))
                if name == "source-review":
                    assert "-163,165.00" in page.locator(".metrics-grid").inner_text()
                    assert "-181,890.00" in page.locator(".metrics-grid").inner_text()
                    assert "Simulated request changes" in page.locator("#revisions").inner_text()
                    assert "50" in page.locator("#learning").inner_text()
                    assert "61,000.00" in page.locator("#preserved").inner_text()
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert len(payload["revisions"]) == 5 and payload["human_review_count"] == 0
                    assert payload["actual_company_realized_value"] is None
                    for key in (
                        "original_forecast",
                        "close_forecast",
                        "measured_difference",
                        "attributed_difference",
                        "unassigned_residual",
                    ):
                        assert (
                            payload["source_review"]["before_aggregate_recorded_periods"][key]
                            == payload["aggregate_recorded_periods"][key]
                        )
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#revisions").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"source-review-revisions-{width}.png"))
                if name == "operating-sources":
                    assert "-18,314.50" in page.locator(".metrics-grid").inner_text()
                    assert "-38,532.00" in page.locator(".metrics-grid").inner_text()
                    assert "Notice deadline missed" in page.locator("#contracts").inner_text()
                    assert "fictional records" in page.locator(".hero").inner_text()
                    payload = page.request.get(base + "/portfolio/operating-sources.json").json()
                    assert payload["classification"] == "constructed_operating_records"
                    assert payload["actual_company_realized_value"] is None
                    assert not payload["missing_service_months"]
                    scenario = next(s for s in payload["scenarios"] if s["scenario_id"] == "base")
                    assert scenario["year_one"]["incremental_ebitda"] == "-18314.50"
                    assert scenario["total"]["working_capital_cash"] == "0.00"
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#contracts").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"operating-contracts-{width}.png"))
                if name == "case-history":
                    assert "Freeze the reviewed hypothetical close" in page.locator("#close-baseline").inner_text()
                    assert "simulation" in page.locator("#close-baseline").inner_text()
                    assert "218,977" in page.locator("#close-baseline").inner_text()
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert payload["close_baseline"]["usable_for_comparison"]
                    assert payload["close_baseline"]["frozen_forecast"]["year_one"]["incremental_ebitda"] == "218976.65"
                    assert payload["human_review_count"] == 0 and payload["comparison"]["actuals"] is None
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#close-baseline").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"close-baseline-{width}.png"))
                if name == "decision-memo":
                    assert "Task order cannot substitute" in page.locator("#evidence-update").inner_text()
                    assert "every tested sequence" in page.locator(".hero").inner_text()
                    assert "Original preference — reopened" in page.locator("#choices").inner_text()
                    assert "-98.385" in page.locator("#historical-valuation").inner_text()
                    assert "Service first" in page.locator("#choices").inner_text()
                    assert "No operating intervention is authorized" in page.locator("#next-decision").inner_text()
                    assert "583.6" in page.locator("#choices").inner_text()
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert payload["execution_authorized"] is False
                    assert payload["preference_status"] == "reopen_source_constrained_preference"
                    assert payload["source_review"]["all_base_year_one_nonpositive"]
                    assert len(payload["source_review"]["options"]) == 3
                    if width in (1440, 375):
                        page.locator("#evidence-update .earnings-waterfall").screenshot(
                            path=str(output / f"memo-waterfall-{width}.png")
                        )
                    assert payload["actual_realized_value"] is None
                    assert payload["historical_valuation"]["current_equity_value"] is None
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#choices").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"decision-choices-{width}.png"))
                if name == "historical-valuation":
                    matrix = page.locator("#historical-valuation").inner_text()
                    assert "-98.385" in matrix and "1,410.000" in matrix and "1,400.349" in matrix
                    assert (
                        "Zero-valued claims are explicit unverified assumptions"
                        in page.locator("#assumptions").inner_text()
                    )
                    download = page.locator("a[download]")
                    assert download.count() == 1
                    payload = page.request.get(base + "/portfolio/" + download.get_attribute("href")).json()
                    assert payload["current_equity_value"] is None and payload["per_share_value"] is None
                    assert len(payload["balances"]["facts"]) == 13 and not payload["blocked_by"]
                    assert all(c["status"] == "matched" for c in payload["reconciliations"])
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#historical-valuation").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"equity-matrix-{width}.png"))
                if name == "disclosure-history":
                    assert "1.195" in page.locator("#allocation").inner_text()
                    assert "withheld missing publication evidence" in page.locator("#timing").inner_text()
                    assert "not a realized investment return" in page.locator("#judgment").inner_text()
                    payload = page.request.get(base + "/portfolio/disclosure-history.json").json()
                    assert payload["point_in_time_claim"] == "withheld"
                    assert len(payload["comparison"]) == 9
                    assert payload["cutoffs"][2]["acceptance_selection"]["selected"]["status"] == "preliminary"
                    assert payload["cutoffs"][3]["acceptance_selection"]["selected"]["status"] == "final"
                    assert all(row["publication_selection"]["selected"] is None for row in payload["cutoffs"])
                if name == "exit-review":
                    assert "Unavailable" in page.locator(".hero-aside").inner_text()
                    assert "304.202" in page.locator("#matrix").inner_text()
                    assert "-8,500.00" in page.locator("#operating").inner_text()
                    assert "interaction" in page.locator("#bridge").inner_text().lower()
                    payload = page.request.get(base + "/portfolio/exit-review.json").json()
                    assert len(payload["revisions"]) == 6
                    latest = json.loads(payload["revisions"][-1]["financial_result_json"])
                    assert len(latest["exit_review"]["rows"]) == 12
                    assert latest["exit_review"]["transaction_proceeds"] is None
                    assert payload["source_review"]["exit_checkpoint"]["preserved_accounting_and_claims"]
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#bridge").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"exit-bridge-{width}.png"))
                if name == "lineage-review":
                    assert "Ten revisions" in page.locator("#history").inner_text()
                    assert "pricing-spring" in page.locator("#lineage").inner_text()
                    assert "4.00%" in page.locator("#kpis").inner_text()
                    assert "18,000.00" in page.locator("#authority").inner_text()
                    payload = page.request.get(base + "/portfolio/lineage-review.json").json()
                    assert len(payload["revisions"]) == 10 and payload["human_review_count"] == 0
                    assert payload["initiative_comparability"]["historical_child_allocations"] is None
                    latest = json.loads(payload["revisions"][-1]["financial_result_json"])
                    assert len(latest["lineage_review"]["kpis"]["definitions"]) == 7
                    assert len(latest["lineage_review"]["kpis"]["observations"]) == 15
                    assert latest["exit_review"]["transaction_proceeds"] is None
                    if width in (1440, 375):
                        page.locator("#kpis").evaluate("e => e.scrollIntoView({block:'start'})")
                        page.screenshot(path=str(output / f"lineage-kpis-{width}.png"))
                if name == "public-baseline":
                    assert "stricter cohort" in page.locator("#peers").inner_text().lower()
                    assert "Withheld" in page.locator("#peers").inner_text()
                    assert "SS&C Technologies" in page.locator("#peers").inner_text()
                    assert "Organic growth remains unavailable" in page.locator("#growth").inner_text()
                    assert "Reject" in page.locator("#research-decisions").inner_text()
                    if width in (1440, 375):
                        page.locator("main").focus()
                        page.locator("#growth").screenshot(path=str(output / f"public-growth-{width}.png"))
                        page.locator("#peers > details").evaluate("e => e.open = false")
                        page.locator("main").focus()
                        page.locator("#peers").scroll_into_view_if_needed()
                        page.screenshot(path=str(output / f"public-peers-{width}.png"))
                findings.append(
                    {
                        "page": name,
                        "viewport": width,
                        "document_width": dimensions["width"],
                        "keyboard": "pass",
                        "disclosures": "pass",
                    }
                )
                page.close()
            context.close()
        version = browser.version
        browser.close()
    server.shutdown()
    (output / "browser-checks.json").write_text(
        json.dumps({"browser": "Chromium", "version": version, "checks": findings}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: {len(findings)} page/viewport checks, keyboard navigation and disclosure expansion.")


if __name__ == "__main__":
    main()
