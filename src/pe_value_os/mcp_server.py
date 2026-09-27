"""MCP server (PVC-050..059, PVC-091).

One MCPServer process; tools are registered per capability boundary (ADR 0001). Streamable HTTP requires
OAuth bearer tokens outside dev. Run locally with `uvicorn pe_value_os.mcp_server:app`.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

from . import __version__, security
from .auth import auth_settings_from_env, verifier_from_env
from .observability import RequestMetricsMiddleware, configure_telemetry
from .policy import get_policy
from .tools._runtime import StrictArguments, company_data, get_ctx, governed
from .tools.benchmark import register_benchmark
from .tools.source_tools import (
    register_crm,
    register_portco_financials,
    register_product_analytics,
    register_support,
)
from .tools.value_tools import register_pricing, register_value_model, register_workflow

INSTRUCTIONS = (
    "Governed capabilities for PE portfolio value-creation diagnostics. Read project://policies first. Every "
    "company tool is scoped to the companies in your token. Numbers come from tools, never from prose. Value "
    "claims must cite evidence ids. Approval decisions are made by humans in the approval API, not by tools."
)


class Health(BaseModel):
    status: str
    version: str


def build_server() -> MCPServer:
    mcp = MCPServer(
        "PE Portfolio Value Creation Operating System",
        instructions=INSTRUCTIONS,
        version=__version__,
        token_verifier=verifier_from_env(),
        auth=auth_settings_from_env(),
        middleware=[StrictArguments()],
    )

    @mcp.tool()
    @governed("healthcheck")
    def healthcheck() -> Health:
        """Return service health."""
        return Health(status="ok", version=__version__)

    register_portco_financials(mcp)
    register_crm(mcp)
    register_product_analytics(mcp)
    register_support(mcp)
    register_pricing(mcp)
    register_benchmark(mcp)
    register_value_model(mcp)
    register_workflow(mcp)

    @mcp.resource("project://policies", mime_type="text/plain")
    def policies() -> str:
        """Operating rules, freshness window and screening thresholds (versioned)."""
        return get_policy().describe()

    @mcp.resource("company://{company_id}/data-inventory", mime_type="application/json")
    def data_inventory(company_id: str) -> str:
        """Datasets available for a company: rows, invalid rows, as-of dates and evidence ids."""
        data = company_data(company_id)
        return json.dumps(
            {"company_id": company_id, "reference_date": data.reference_date.isoformat(), "datasets": data.inventory()},
            indent=2,
        )

    @mcp.resource("run://{run_id}/summary", mime_type="application/json")
    def run_summary(run_id: str) -> str:
        """Status, findings, opportunities with value cases, and plan totals for a run."""
        ctx = get_ctx()
        rec = ctx.repo.get_run(run_id)
        security.require(rec.company_id)
        vcs = {v.opportunity_id: v for v in ctx.repo.list_value_cases(run_id)}
        plan = ctx.repo.latest_plan(run_id)
        out: dict[str, Any] = {
            "run_id": run_id,
            "company_id": rec.company_id,
            "status": rec.status.value,
            "findings": [
                f.model_dump(
                    mode="json",
                    include={"finding_id", "finding_type", "title", "statement", "confidence", "evidence_ids"},
                )
                for f in ctx.repo.list_findings(run_id)
            ],
            "opportunities": [
                {
                    **o.model_dump(
                        mode="json", include={"opportunity_id", "lever", "title", "confidence", "evidence_ids"}
                    ),
                    "value_case": vcs[o.opportunity_id].model_dump(mode="json") if o.opportunity_id in vcs else None,
                }
                for o in ctx.repo.list_opportunities(run_id)
            ],
            "plan": {
                "plan_id": plan.plan_id,
                "status": plan.status,
                "total_run_rate_ebitda_base": plan.plan.get("total_run_rate_ebitda_base"),
            }
            if plan
            else None,
        }
        return json.dumps(out, indent=2)

    @mcp.prompt()
    def review_run(run_id: str) -> str:
        """User-controlled review prompt for a workflow run."""
        return (
            f"Review workflow run {run_id}. Read run://{run_id}/summary and project://policies. Separate facts, "
            "assumptions and recommendations. For every number, name the tool result it came from. List any value "
            "claim without evidence, any stale evidence, and any suspicious_content finding. Do not approve; "
            "approval happens in the approval API."
        )

    return mcp


def transport_security_from_env() -> TransportSecuritySettings | None:
    """DNS-rebinding protection for the public hostname.

    The SDK default only accepts localhost Host headers. Behind the load balancer the Host header is the public
    hostname from PVC_MCP_RESOURCE_URL, plus any extra hosts in PVC_MCP_ALLOWED_HOSTS (comma-separated).
    Returns None in local dev (no resource URL), keeping the SDK's localhost-only default.
    """
    hosts = [h.strip() for h in os.environ.get("PVC_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    resource = os.environ.get("PVC_MCP_RESOURCE_URL")
    if resource:
        hosts.append(urlsplit(resource).netloc)
    if not hosts:
        return None
    origins = [f"https://{h}" for h in hosts] + [f"http://{h}" for h in hosts if h.startswith(("127.", "localhost"))]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=sorted(set(hosts)), allowed_origins=sorted(set(origins))
    )


def create_http_app(server: MCPServer | None = None) -> Any:
    """Streamable HTTP ASGI app with transport security and request metrics."""
    from .readiness import ReadinessMiddleware

    s = server or mcp
    return RequestMetricsMiddleware(
        ReadinessMiddleware(s.streamable_http_app(transport_security=transport_security_from_env()), get_ctx),
        service="mcp",
    )


configure_telemetry("pvc-mcp")
mcp = build_server()
app = create_http_app(mcp)
