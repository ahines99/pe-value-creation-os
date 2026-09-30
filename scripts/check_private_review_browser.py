"""Visual/keyboard checks on ephemeral fictional review captures, without live accounts."""

from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    site, output = (Path(arg).resolve() for arg in sys.argv[1:])
    output.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (1440, 768, 375):
                for name in ("index", "pending", "accepted", "revoked"):
                    tab = browser.new_page(viewport={"width": width, "height": 1000})
                    tab.goto(f"http://127.0.0.1:{server.server_port}/{name}.html")
                    assert tab.locator("h1").count() == 1
                    assert tab.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (name, width)
                    tab.keyboard.press("Tab")
                    assert tab.evaluate("document.activeElement.classList.contains('skip-link')")
                    tab.keyboard.press("Enter")
                    if name != "index":
                        assert tab.get_by_text("Fictional private-workflow rehearsal", exact=True).count() >= 1
                        assert tab.get_by_role("button", name="Accept reviewed claims").count() == (
                            0 if name == "revoked" else 1
                        )
                        assert tab.get_by_role("button", name="Withdraw acceptance").count() == (
                            0 if name == "pending" else 1
                        )
                        assert tab.locator("label[for='rationale']").count() == 1
                        assert tab.locator("#rationale").get_attribute("required") is not None
                        tab.get_by_text("Monthly accounting components", exact=True).click()
                        region = tab.get_by_role("region", name="Monthly accounting bridge", exact=True)
                        assert region.is_visible() and region.get_attribute("tabindex") == "0"
                        tab.get_by_text("Monthly accounting components", exact=True).click()
                        tab.locator("#finance-decision").screenshot(path=str(output / f"{name}-{width}-decision.png"))
                    tab.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True)
                    tab.evaluate("window.scrollTo(0, 0)")
                    tab.screenshot(path=str(output / f"{name}-{width}-top.png"))
                    checks.append({"page": name, "width": width, "passed": True})
                    tab.close()
            browser.close()
    finally:
        server.shutdown()
    (output / "acceptance.json").write_text(
        json.dumps({"origin": "synthetic_test_fixture", "checks": checks}, indent=2), encoding="utf-8"
    )
    print(f"PASS: {len(checks)} private-review page/viewport checks")


if __name__ == "__main__":
    main()
