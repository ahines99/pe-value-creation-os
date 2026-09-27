"""Synthetic deployment acceptance: MCP + evidence storage + worker + human approval API.

Requires pre-onboarded beacon-pricing synthetic fixture and separate least-privilege
MCP/API tokens scoped only to that company. Rejects the synthetic plan, so no approved
initiatives are activated. Run only in a deployment with that fixture explicitly provisioned.
Never print bearer tokens or returned tenant data.
"""

from __future__ import annotations

import os
import time
import uuid

import anyio
import httpx
import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def smoke() -> None:
    company = os.environ["PVC_SMOKE_COMPANY"]
    if company != "beacon-pricing":
        raise ValueError("smoke company must be the dedicated beacon-pricing synthetic fixture")
    mcp_token = os.environ["PVC_SMOKE_MCP_TOKEN"]
    api_token = os.environ["PVC_SMOKE_API_TOKEN"]
    if not mcp_token or not api_token:
        raise ValueError("separate MCP and human approval API smoke tokens are required")
    api_url = os.environ["API_URL"].rstrip("/")
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {mcp_token}"}, timeout=30) as transport,
        streamable_http_client(os.environ["MCP_URL"], http_client=transport) as (read, write),
        ClientSession(read, write) as session,
        httpx.AsyncClient(base_url=api_url, headers={"Authorization": f"Bearer {api_token}"}, timeout=30) as api,
    ):
        await session.initialize()

        async def call(name: str, args: dict) -> dict:
            result = await session.call_tool(name, args)
            if result.is_error or not isinstance(result.structured_content, dict):
                raise RuntimeError(f"authenticated {name} failed")
            return result.structured_content

        profile = await call("get_company_profile", {"company_id": company})
        evidence_ids = profile.get("evidence_ids", [])
        if not evidence_ids:
            raise AssertionError("synthetic profile has no persisted evidence")
        evidence = await api.get(f"/evidence/{evidence_ids[0]}")
        evidence.raise_for_status()
        if not evidence.content:
            raise AssertionError("empty evidence retrieval")
        run = await call(
            "start_diagnostic_run",
            {
                "company_id": company,
                "mode": "automated",
                "idempotency_key": f"deployment-smoke-{uuid.uuid4()}",
            },
        )
        run_id = run["run_id"]

        async def wait_for(wanted: str) -> dict:
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                response = await api.get(f"/runs/{run_id}")
                response.raise_for_status()
                status = response.json()
                if status.get("company_id") != company:
                    raise AssertionError("smoke run company mismatch")
                if status["status"] == wanted:
                    return status
                if status["status"] in {"failed", "needs_evidence", "complete", "rejected"}:
                    raise AssertionError(f"unexpected smoke status {status['status']}")
                await anyio.sleep(2)
            raise TimeoutError(f"worker did not reach {wanted}")

        paused = await wait_for("awaiting_approval")
        if not paused.get("pause_reason", {}).get("approval_id"):
            raise AssertionError("worker did not persist an approval request")
        review = await api.get(f"/runs/{run_id}/review")
        review.raise_for_status()
        decision = await api.post(
            f"/runs/{run_id}/approvals",
            json={
                "decision": "rejected",
                "rationale": "Dedicated synthetic deployment smoke; no initiative authorized.",
            },
        )
        decision.raise_for_status()
        await wait_for("rejected")
        print("PASS authenticated MCP, persisted evidence, worker checkpoint, approval review/decision and resume")


if __name__ == "__main__":
    anyio.run(smoke)
