"""Dependency readiness, separate from liveness. Never returns source data or exception text.

The database probe verifies runtime privileges and forced RLS. Storage probes verify reachability;
authenticated deployment smoke tests additionally prove evidence writes, KMS and workflow completion.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from .adapters.evidence_store import FileSystemEvidenceStore, S3EvidenceStore
from .adapters.repositories import InMemoryRepository
from .observability import get_logger

TABLES = (
    "companies",
    "workflow_runs",
    "evidence",
    "findings",
    "finding_evidence",
    "opportunities",
    "opportunity_evidence",
    "value_cases",
    "priority_scores",
    "plans",
    "approvals",
    "audit_events",
    "kpi_definitions",
    "kpi_observations",
    "kpi_alerts",
    "notifications",
)


def _database(repo: Any) -> None:
    if isinstance(repo, InMemoryRepository):
        if os.environ.get("PVC_ENV", "prod") != "dev":
            raise RuntimeError("Persistent repository required")
        return
    with repo.pool.connection(timeout=2) as conn, conn.transaction():
        conn.execute("set local statement_timeout = '2s'")
        role = conn.execute("select rolsuper, rolbypassrls from pg_roles where rolname = current_user").fetchone()
        if not role or role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("Runtime role bypasses isolation")
        rows = conn.execute(
            """select c.relname, c.relrowsecurity, c.relforcerowsecurity,
                      has_table_privilege(c.oid, 'SELECT') as readable,
                      has_table_privilege(c.oid, 'INSERT') as writable,
                      has_table_privilege(c.oid, 'UPDATE') and
                      has_table_privilege(c.oid, 'DELETE') as mutable
               from pg_class c join pg_namespace n on n.oid = c.relnamespace
               where n.nspname = 'public' and c.relname = any(%s)""",
            (list(TABLES),),
        ).fetchall()
        if len(rows) != len(TABLES) or not all(
            r["relrowsecurity"]
            and r["relforcerowsecurity"]
            and r["readable"]
            and r["writable"]
            and (r["relname"] == "audit_events" or r["mutable"])
            for r in rows
        ):
            raise RuntimeError("Runtime schema or privileges incomplete")
        audit = conn.execute(
            """select has_table_privilege('audit_events', 'UPDATE') or
                      has_table_privilege('audit_events', 'DELETE') as mutable"""
        ).fetchone()
        if audit["mutable"]:
            raise RuntimeError("Audit table is mutable by runtime role")
        # Refer to required columns as well as tables: stale migrations must not look ready.
        conn.execute("select run_id, locked_by, locked_at, resume_requested_at from workflow_runs limit 0")
        conn.execute("select notification_id, delivered_at, status, locked_by, locked_at from notifications limit 0")


def _evidence(store: Any) -> None:
    if isinstance(store, FileSystemEvidenceStore):
        store.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=store.root) as probe:
            probe.write(b"pvc-readiness")
            probe.flush()
            probe.seek(0)
            if probe.read() != b"pvc-readiness":
                raise RuntimeError("Evidence probe mismatch")
    elif isinstance(store, S3EvidenceStore):
        # Match the least-privilege prefix condition; HeadBucket lacks the prefix and is correctly denied.
        store.client.list_objects_v2(Bucket=store.bucket, Prefix=f"{store.prefix}/__readiness__/", MaxKeys=1)
    else:
        raise RuntimeError("Unknown evidence backend")


def is_ready(ctx: Any) -> bool:
    try:
        _database(ctx.repo)
        _evidence(ctx.repo.evidence_store)
    except Exception as exc:
        get_logger(__name__).warning("readiness_failed", error_type=type(exc).__name__)
        return False
    return True


class ReadinessMiddleware:
    """Expose /readyz on the MCP ASGI app without changing MCP routing/lifespan."""

    def __init__(self, app: Any, context: Any):
        self.app, self.context = app, context

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path") == "/readyz" and scope.get("method") == "GET":
            import anyio
            from starlette.responses import JSONResponse

            def probe() -> bool:
                try:
                    return is_ready(self.context())
                except Exception:
                    return False

            ready = await anyio.to_thread.run_sync(probe)
            response = JSONResponse(
                {"status": "ready" if ready else "unready"},
                status_code=200 if ready else 503,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
