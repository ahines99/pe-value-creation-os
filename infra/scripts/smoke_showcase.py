"""Exercise local browser-session HTTP contracts against scripts/showcase.py's synthetic stack.

This checks actual form/cookie/evidence/worker behavior, not rendered browser usability.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "var/local-showcase"


def main() -> None:
    token = json.loads((STATE / "settings.json").read_text())["token"]
    runs = json.loads((STATE / "runs.json").read_text())
    run_id = runs["beacon-pricing"]
    report: dict[str, object] = {"synthetic": True, "run_id": run_id, "checks": []}
    checks: list[str] = []
    with httpx.Client(base_url="http://localhost:18081", follow_redirects=True, timeout=30) as client:
        assert client.get(f"/runs/{run_id}/review").status_code == 401
        landing = client.get("/")
        assert landing.status_code == 200 and "Local showcase sign-in" in landing.text
        csrf = client.cookies["pvc_login_csrf"]
        assert client.post("/dev/login", data={"token": token, "csrf": "wrong"}).status_code == 403
        csrf = client.cookies["pvc_login_csrf"]
        signed_in = client.post("/dev/login", data={"token": token, "csrf": csrf})
        signed_in.raise_for_status()
        assert run_id in signed_in.text
        checks.append("development login, unauthenticated denial and login CSRF")
        review = client.get(f"/runs/{run_id}/review")
        review.raise_for_status()
        assert "name='decision'" in review.text, "Smoke acceptance requires a fresh, undecided synthetic run"
        evidence_urls = re.findall(r"href=['\"](/evidence/[^'\"]+)", review.text)
        assert evidence_urls, "Review has no navigable evidence"
        preview_url = evidence_urls[0]
        preview = client.get(preview_url)
        preview.raise_for_status()
        assert "Source preview" in preview.text and f"/runs/{run_id}/review#evidence" in preview.text
        source_path = urlsplit(preview_url).path.removesuffix("/review")
        evidence = client.get(source_path)
        evidence.raise_for_status()
        digest = hashlib.sha256(evidence.content).hexdigest()
        assert digest == evidence.headers["X-Content-Hash"], "Original evidence bytes do not match the stored hash"
        assert evidence.headers["Content-Type"].startswith("text/plain")
        report["evidence_sha256"] = digest
        checks.append("review, contextual evidence preview and hash-verified original evidence")
        assert (
            client.post(f"/runs/{run_id}/approvals/form", data={"decision": "approved", "csrf": "wrong"}).status_code
            == 403
        )
        decision = client.post(
            f"/runs/{run_id}/approvals/form",
            data={
                "decision": "approved",
                "csrf": client.cookies["pvc_csrf"],
                "rationale": "Automated synthetic HTTP acceptance; no real initiative authorized.",
            },
        )
        decision.raise_for_status()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            response = client.get(f"/runs/{run_id}")
            response.raise_for_status()
            if response.json()["status"] == "complete":
                break
            time.sleep(2)
        else:
            raise TimeoutError("Approved showcase run did not complete")
        checks.append("approval form CSRF, decision persistence and worker resume")
        kpis = client.get(f"/companies/beacon-pricing/kpis?run_id={run_id}")
        kpis.raise_for_status()
        assert "No approved KPIs" not in kpis.text and "Operating scorecard" in kpis.text
        assert "Day-100 target" in kpis.text and f"/runs/{run_id}/review" in kpis.text
        checks.append("approved run-specific KPI definitions and operating targets")
        delta = client.get(f"/runs/{runs['delta-broken']}")
        delta.raise_for_status()
        assert delta.json()["status"] == "needs_evidence"
        delta_review = client.get(f"/runs/{runs['delta-broken']}/review")
        delta_review.raise_for_status()
        assert "Evidence before commitment" in delta_review.text and "name='decision'" not in delta_review.text
        checks.append("controlled missing-evidence pause")
    report["checks"] = checks
    (STATE / "http-acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS:", "; ".join(checks))


if __name__ == "__main__":
    main()
