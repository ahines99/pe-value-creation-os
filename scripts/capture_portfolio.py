"""Generate read-only portfolio HTML from isolated, synthetic application workflows.

No live database, user token or provider is used. These are HTML captures, not screenshots.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import anyio
from fastapi.testclient import TestClient

from pe_value_os import kpi, security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.api import app as api
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/portfolio/examples"
COMPANIES = ("beacon-pricing", "delta-broken")


def main() -> None:
    os.environ["PVC_ENV"] = "dev"
    os.environ["PVC_SOURCE_ADAPTER"] = "fixtures"
    os.environ["PVC_API_CLIENT_IDS"] = "approval-ui"
    os.environ["PVC_MODEL_MODE"] = "rules"
    claims = {
        "sub": "human:automated-static-capture",
        "pvc_companies": list(COMPANIES),
        "pvc_roles": ["approver"],
        "pvc_principal_type": "human",
        "scope": "pvc.read pvc.approve",
        "azp": "approval-ui",
    }
    os.environ["PVC_DEV_TOKENS"] = json.dumps({"capture-only": claims})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pvc-capture-") as temporary:
        ctx = RunContext(
            repo=InMemoryRepository(FileSystemEvidenceStore(Path(temporary))),
            adapter=FixtureAdapter(),
            policy=get_policy(),
        )
        api.set_ctx(ctx)
        api.reset_auth()
        routes: dict[str, str] = {"/": "workspace.html"}
        pages: dict[str, str] = {}
        runs: dict[str, str] = {}
        for company in COMPANIES:
            with security.principal_scope(security.system_principal(company)):
                run, _ = primary.start(ctx, company, "human:automated-static-capture")
                anyio.run(primary.execute, ctx, run.run_id)
                runs[company] = run.run_id
                routes[f"/runs/{run.run_id}/review"] = f"{company}.html"
                scorecard = "beacon-kpis.html" if company == "beacon-pricing" else "delta-kpis.html"
                routes[f"/companies/{company}/kpis?run_id={run.run_id}"] = scorecard
                routes[f"/companies/{company}/kpis"] = scorecard
        with TestClient(api.app, headers={"Authorization": "Bearer capture-only"}) as client:
            for run_id in runs.values():
                route = f"/runs/{run_id}/review"
                response = client.get(route)
                response.raise_for_status()
                pages[route] = response.text
                for evidence_route in set(re.findall(r"href=['\"](/evidence/[^'\"]+)", response.text)):
                    evidence_id = evidence_route.split("/")[2]
                    routes[evidence_route] = f"{evidence_id}.html"
                    preview = client.get(evidence_route)
                    preview.raise_for_status()
                    pages[evidence_route] = preview.text
                    original_route = f"/evidence/{evidence_id}"
                    original = client.get(original_route)
                    original.raise_for_status()
                    routes[original_route] = f"{evidence_id}.txt"
                    (OUTPUT / routes[original_route]).write_bytes(original.content)
            run_id = runs["beacon-pricing"]
            decision = client.post(
                f"/runs/{run_id}/approvals",
                json={
                    "decision": "approved",
                    "rationale": "Automated synthetic capture; no real initiative authorized.",
                },
            )
            decision.raise_for_status()
            with security.principal_scope(security.system_principal("beacon-pricing")):
                anyio.run(lambda: primary.resume(ctx, run_id, "system:static-capture"))
                kpi.refresh_company(ctx.repo, ctx.adapter, "beacon-pricing", ctx.policy)
            for route in list(routes):
                if route == "/" or route.startswith("/companies/"):
                    response = client.get(route)
                    response.raise_for_status()
                    pages[route] = response.text
        for route, html in pages.items():
            html = re.sub(r"<input[^>]*name=['\"]csrf['\"][^>]*>", "", html)
            html = re.sub(r"<form\b[^>]*>", "<fieldset disabled><legend>Read-only decision controls</legend>", html)
            html = html.replace("</form>", "</fieldset>")

            def local_link(match: re.Match[str]) -> str:
                target = match.group(2)
                path, separator, fragment = target.partition("#")
                if path not in routes:
                    raise ValueError(f"Uncaptured application link: {target}")
                return f"href={match.group(1)}{routes[path]}{separator}{fragment}{match.group(1)}"

            html = re.sub(r"href=(['\"])(/[^'\"]*)\1", local_link, html)
            banner = (
                "<aside class='notice' aria-label='Capture provenance'>"
                "<strong>Read-only application capture.</strong> Fictional fixtures; automated demonstration. "
                "The memo shows the proposed review; the scorecard uses fixture observations after an automated approval. "
                "These are modeled values, not realized results. "
                "<a href='../../index.html'>Portfolio overview</a> &middot; "
                "<a href='workspace.html'>Workspace</a></aside>"
            )
            main = "id='main-content' tabindex='-1'>"
            assert html.count(main) == 1
            html = html.replace(main, main + banner, 1)
            # The static copy sits two folders below the site root, beside docs/assets/fonts.
            html = html.replace('url("/assets/fonts/', 'url("../../assets/fonts/')
            assert "name='csrf'" not in html and "<form" not in html
            (OUTPUT / routes[route]).write_text(html, encoding="utf-8")
        api.set_ctx(None)
        api.reset_auth()
    print(f"Captured {len(set(routes.values()))} synthetic application and evidence artifacts.")


if __name__ == "__main__":
    main()
