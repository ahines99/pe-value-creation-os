"""Backup/restore drill (PVC-142).

Seeds a fresh database by running the real workflow for the fixture companies through the PostgreSQL
repository, dumps it with pg_dump (custom format), restores into another fresh database with pg_restore, then
verifies row counts, the migration revision and row-level security on the restored copy. Timings are appended
to docs/runbooks/restore-drill-log.md.

    PVC_ADMIN_DATABASE_URL=postgresql://postgres@localhost:54329/postgres PVC_PG_BIN=<dir with pg_dump> \
        python scripts/restore_drill.py
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pe_value_os import security  # noqa: E402
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore  # noqa: E402
from pe_value_os.adapters.fixtures import FixtureAdapter  # noqa: E402
from pe_value_os.adapters.postgres import PostgresRepository  # noqa: E402
from pe_value_os.db.migrate import bootstrap_roles, current, upgrade  # noqa: E402
from pe_value_os.observability import configure_logging  # noqa: E402
from pe_value_os.policy import get_policy  # noqa: E402
from pe_value_os.workflows import primary  # noqa: E402
from pe_value_os.workflows.steps import RunContext  # noqa: E402

TABLES = ["companies", "workflow_runs", "evidence", "findings", "opportunities", "value_cases", "plans", "approvals",
          "audit_events"]
COMPANIES = ["acme-healthy", "beacon-pricing", "cedar-churn", "delta-broken"]


def db_url(admin: str, db: str, user: str | None = None, pw: str | None = None) -> str:
    p = urlsplit(admin)
    netloc = p.netloc if not user else f"{user}:{pw}@{p.netloc.split('@')[-1]}" if pw else f"{user}@{p.netloc.split('@')[-1]}"
    return urlunsplit((p.scheme, netloc, f"/{db}", p.query, p.fragment))


def tool(name: str) -> str:
    base = os.environ.get("PVC_PG_BIN")
    found = shutil.which(name, path=base) if base else shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found; set PVC_PG_BIN")
    return found


def counts(url: str) -> dict[str, int]:
    import psycopg

    with psycopg.connect(url) as conn:
        return {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}  # type: ignore[index]


def main() -> int:
    import psycopg

    configure_logging(stream=io.StringIO())
    admin = os.environ["PVC_ADMIN_DATABASE_URL"]
    src, dst = f"pvc_drill_src_{uuid.uuid4().hex[:6]}", f"pvc_drill_dst_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{src}"')
        c.execute(f'create database "{dst}"')
    tmp = Path(tempfile.mkdtemp())
    try:
        src_admin = db_url(admin, src)
        bootstrap_roles(src_admin, {"pvc_app": "drill_pw"})
        upgrade(src_admin)
        repo = PostgresRepository(db_url(admin, src, "pvc_app", "drill_pw"), FileSystemEvidenceStore(tmp / "ev"))
        ctx = RunContext(repo=repo, adapter=FixtureAdapter(), policy=get_policy())
        for cid in COMPANIES:
            with security.principal_scope(security.system_principal(cid)):
                rec, _ = primary.start(ctx, cid, "drill")
                anyio.run(lambda rid=rec.run_id: primary.execute(ctx, rid, backoff_s=0))
        repo.close()
        before = counts(src_admin)

        dump = tmp / "pvc.dump"
        t0 = time.perf_counter()
        subprocess.run([tool("pg_dump"), "-Fc", "-f", str(dump), "--dbname", src_admin], check=True)
        t_dump = time.perf_counter() - t0
        dst_admin = db_url(admin, dst)
        t0 = time.perf_counter()
        subprocess.run([tool("pg_restore"), "--no-owner", "--dbname", dst_admin, str(dump)], check=True)
        t_restore = time.perf_counter() - t0
        after = counts(dst_admin)
        assert before == after, f"row counts differ: {before} vs {after}"
        assert current(dst_admin) == current(src_admin)
        with psycopg.connect(dst_admin, autocommit=True) as c:  # restored ownership: re-apply grants for pvc_app
            c.execute("grant usage on schema public to pvc_app")
            c.execute("grant select on all tables in schema public to pvc_app")
        with psycopg.connect(db_url(admin, dst, "pvc_app", "drill_pw")) as c:
            c.execute("select set_config('pvc.companies', 'beacon-pricing', false)")
            visible = {r[0] for r in c.execute("select distinct company_id from workflow_runs").fetchall()}
        assert visible == {"beacon-pricing"}, f"RLS not effective after restore: {visible}"
        size_kb = dump.stat().st_size // 1024
        line = (f"| {datetime.now(UTC):%Y-%m-%d %H:%M} UTC | local PostgreSQL 18 | {sum(before.values())} rows, "
                f"{size_kb} KB dump | {t_dump:.2f} s | {t_restore:.2f} s | counts match; RLS verified | pass |")
        log = ROOT / "docs" / "runbooks" / "restore-drill-log.md"
        if not log.exists():
            log.write_text("# Restore drill log (PVC-142)\n\n| When | Environment | Data | Dump | Restore | "
                           "Checks | Result |\n|---|---|---|---|---|---|---|\n", encoding="utf-8")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(line)
        return 0
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            for db in (src, dst):
                c.execute(f'drop database if exists "{db}" with (force)')
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
