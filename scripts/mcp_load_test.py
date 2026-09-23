"""MCP load test (PVC-143): concurrent MCP sessions over Streamable HTTP against a PostgreSQL-backed server.

Starts the MCP server (uvicorn, dev auth) on a throwaway database, then runs S concurrent client sessions. Each
session initializes, then loops through a realistic mix of read tools and interactive-run calls for K rounds.
Checks the availability SLO (no 5xx; tool error rate) and reports tool-call latency percentiles.

    PVC_ADMIN_DATABASE_URL=postgresql://postgres@localhost:54329/postgres python scripts/mcp_load_test.py --sessions 20 --rounds 5
"""

from __future__ import annotations

import argparse
import io
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from restore_drill import db_url  # noqa: E402

from pe_value_os.db.migrate import bootstrap_roles, upgrade  # noqa: E402
from pe_value_os.observability import configure_logging  # noqa: E402

COMPANIES = ["acme-healthy", "beacon-pricing", "cedar-churn"]
TOOL_P95_TARGET_S = 2.0  # engineering placeholder, see docs/slo.md


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _session(url: str, n: int, rounds: int, latencies: list[float], errors: list[str]) -> None:
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    cid = COMPANIES[n % len(COMPANIES)]
    async with (
        httpx2.AsyncClient(timeout=60) as http,
        streamable_http_client(url, http_client=http) as (read, write),
        ClientSession(read, write) as s,
    ):
        await s.initialize()
        for _ in range(rounds):
            calls = [
                ("get_company_profile", {"company_id": cid}),
                ("check_data_sufficiency", {"company_id": cid, "analysis": "pricing"}),
                ("compute_saas_metrics", {"company_id": cid}),
                ("price_waterfall", {"company_id": cid}),
                ("start_diagnostic_run", {"company_id": cid, "mode": "interactive"}),
            ]
            for name, args in calls:
                t0 = time.perf_counter()
                try:
                    r = await s.call_tool(name, args)
                    if r.is_error:
                        errors.append(f"{name}: {r.content[0].text if r.content else ''}"[:200])
                    elif name == "start_diagnostic_run":
                        t1 = time.perf_counter()
                        st = await s.call_tool("get_run_status", {"run_id": r.structured_content["run_id"]})
                        latencies.append(time.perf_counter() - t1)
                        if st.is_error:
                            errors.append("get_run_status failed")
                except Exception as exc:  # transport errors count against availability
                    errors.append(f"{name}: {type(exc).__name__}: {exc}"[:200])
                latencies.append(time.perf_counter() - t0)


def main() -> int:
    import httpx
    import psycopg

    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    configure_logging(stream=io.StringIO())
    admin = os.environ["PVC_ADMIN_DATABASE_URL"]
    db = f"pvc_mcpload_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{db}"')
    tmp = Path(tempfile.mkdtemp(prefix="pvcml"))
    port = _free_port()
    server = None
    try:
        bootstrap_roles(db_url(admin, db), {"pvc_app": "load_pw"})
        upgrade(db_url(admin, db))
        env = {
            **os.environ,
            "PVC_ENV": "dev",
            "PVC_ALLOWED_COMPANIES": ",".join(COMPANIES),
            "DATABASE_URL": db_url(admin, db, "pvc_app", "load_pw"),
            "PVC_EVIDENCE_DIR": str(tmp / "ev"),
            "PVC_LOG_LEVEL": "WARNING",
        }
        env.pop("PVC_MCP_RESOURCE_URL", None)
        # Companies must be onboarded before runs can be created (as `pvc run` would do).
        seed = (
            "from pe_value_os import security\n"
            "from pe_value_os.app import build_context\n"
            f"for c in {COMPANIES!r}:\n"
            "    ctx = build_context()\n"
            "    with security.principal_scope(security.system_principal(c)):\n"
            "        ctx.repo.upsert_company(ctx.adapter.load(c).profile)\n"
        )
        subprocess.run([sys.executable, "-c", seed], env=env, check=True)
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "pe_value_os.mcp_server:app",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            env=env,
        )
        url = f"http://127.0.0.1:{port}/mcp"
        for _ in range(200):
            try:
                httpx.get(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        latencies: list[float] = []
        errors: list[str] = []

        async def run_all() -> None:
            async with anyio.create_task_group() as tg:
                for n in range(args.sessions):
                    tg.start_soon(_session, url, n, args.rounds, latencies, errors)

        t0 = time.perf_counter()
        anyio.run(run_all)
        wall = time.perf_counter() - t0
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'drop database if exists "{db}" with (force)')

    calls = len(latencies)
    q = statistics.quantiles(latencies, n=20)
    p95 = q[18]
    error_rate = len(errors) / calls if calls else 1.0
    line = (
        f"| {datetime.now(UTC):%Y-%m-%d %H:%M} UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) "
        f"| {args.sessions} concurrent sessions, {calls} tool calls | {calls / wall:.1f} calls/s "
        f"| tool p50 {statistics.median(latencies) * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms "
        f"| errors {len(errors)} ({error_rate:.2%}); p95 target {TOOL_P95_TARGET_S:.0f} s |"
    )
    with (ROOT / "docs" / "load_test.md").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)
    for e in errors[:5]:
        print("  error:", e)
    assert error_rate <= 0.005, f"availability SLO breached: {error_rate:.2%} of tool calls failed"
    assert p95 <= TOOL_P95_TARGET_S, f"tool p95 {p95:.2f}s exceeds {TOOL_P95_TARGET_S}s"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
