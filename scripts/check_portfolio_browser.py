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
