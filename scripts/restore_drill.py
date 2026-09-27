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
import secrets
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
from pe_value_os.db.migrate import bootstrap_roles, current, scram_sha256_verifier, upgrade  # noqa: E402
from pe_value_os.observability import configure_logging  # noqa: E402
from pe_value_os.policy import get_policy  # noqa: E402
from pe_value_os.workflows import primary  # noqa: E402
from pe_value_os.workflows.steps import RunContext  # noqa: E402

COMPANIES = ["acme-healthy", "beacon-pricing", "cedar-churn", "delta-broken"]


def create_test_role(admin: str) -> tuple[str, str]:
    """An isolated login inherits runtime grants; existing cluster passwords never change."""
    import psycopg
    from psycopg import sql

    bootstrap_roles(admin)  # idempotent group creation, no password reset
    role, password = "pvc_test_" + uuid.uuid4().hex, secrets.token_urlsafe(32)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("create role {} login inherit password {} in role pvc_app").format(
                sql.Identifier(role), sql.Literal(scram_sha256_verifier(password))
            )
        )
    return role, password


def drop_test_role(admin: str, role: str) -> None:
    import psycopg
    from psycopg import sql

    if not role.startswith("pvc_test_"):
        raise ValueError("refusing to drop a non-test role")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("drop role {}").format(sql.Identifier(role)))


def db_url(admin: str, db: str, user: str | None = None, pw: str | None = None) -> str:
    p = urlsplit(admin)
    netloc = (
        p.netloc
        if not user
        else f"{user}:{pw}@{p.netloc.split('@')[-1]}"
        if pw
        else f"{user}@{p.netloc.split('@')[-1]}"
    )
    return urlunsplit((p.scheme, netloc, f"/{db}", p.query, p.fragment))


def tool(name: str) -> str:
    base = os.environ.get("PVC_PG_BIN")
    found = shutil.which(name, path=base) if base else shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found; set PVC_PG_BIN")
    return found


def counts(url: str) -> dict[str, int]:
    import psycopg
    from psycopg import sql

    with psycopg.connect(url) as conn:
        tables = conn.execute("select tablename from pg_tables where schemaname='public' order by tablename")
        return {
            t: conn.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(t))).fetchone()[0]
            for (t,) in tables.fetchall()
        }


def seed_monitoring(url: str) -> None:
    """Populate the operational tables so restore checks never pass on empty tables."""
    import psycopg

    with psycopg.connect(url) as conn:
        for cid in ("beacon-pricing", "cedar-churn"):
            plan, run = conn.execute("select plan_id,run_id from plans where company_id=%s limit 1", (cid,)).fetchone()
            kid, oid = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                "insert into kpi_definitions(kpi_id,company_id,plan_id,run_id,metric,description,baseline,"
                "day_100_target,run_rate_target,direction,cadence_days,source,start_date) "
                "values(%s,%s,%s,%s,'total_arr','restore probe',100,110,120,'increase',30,'fixture',current_date)",
                (kid, cid, plan, run),
            )
            conn.execute(
                "insert into kpi_observations(observation_id,kpi_id,company_id,observed_at,value,target,status,variance) "
                "values(%s,%s,%s,now(),90,110,'off_track',-20)",
                (oid, kid, cid),
            )
            conn.execute(
                "insert into kpi_alerts(alert_id,kpi_id,company_id,observation_id,rule,detail) "
                "values(%s,%s,%s,%s,'threshold','restore probe')",
                (uuid.uuid4(), kid, cid, oid),
            )
            conn.execute(
                "insert into notifications(notification_id,company_id,channel,subject,body) "
                "values(%s,%s,'outbox','restore probe','synthetic only')",
                (uuid.uuid4(), cid),
            )


def verify_rls(admin: str, runtime: str) -> list[str]:
    """Every tenant table: forced RLS, exact scoped reads, rejected foreign INSERT/UPDATE/DELETE.

    All mutations run in rolled-back transactions. Also prove same-tenant UPDATE grants,
    append-only audit grants, and an actual same-tenant INSERT/DELETE round trip.
    """
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb

    checked = []
    with psycopg.connect(admin) as owner, psycopg.connect(runtime, autocommit=True) as app:
        role = app.execute("select rolsuper,rolbypassrls from pg_roles where rolname=current_user").fetchone()
        assert role == (False, False), "runtime role bypasses RLS"
        tables = owner.execute(
            "select relname,relrowsecurity,relforcerowsecurity from pg_class "
            "where relnamespace='public'::regnamespace and relkind='r' and relname <> 'alembic_version'"
        ).fetchall()
        for name, enabled, forced in tables:
            assert enabled and forced, f"{name}: RLS missing"
            table = sql.Identifier(name)
            columns = [
                r[0]
                for r in owner.execute(
                    "select column_name from information_schema.columns where table_schema='public' and table_name=%s "
                    "order by ordinal_position",
                    (name,),
                )
            ]
            # Both child link tables inherit their parent company's visibility.
            if "company_id" in columns:
                where = sql.SQL("company_id=%s")
            else:
                parent, key = (
                    ("findings", "finding_id") if name == "finding_evidence" else ("opportunities", "opportunity_id")
                )
                where = sql.SQL("{} in (select {} from {} where company_id=%s)").format(
                    sql.Identifier(key), sql.Identifier(key), sql.Identifier(parent)
                )
            expected = owner.execute(
                sql.SQL("select count(*) from {} where ").format(table) + where, ("beacon-pricing",)
            ).fetchone()[0]
            assert expected > 0, f"{name}: fixture coverage missing"
            app.execute("select set_config('pvc.companies','beacon-pricing',false)")
            actual = app.execute(sql.SQL("select count(*) from {}").format(table)).fetchone()[0]
            assert actual == expected, f"{name}: scoped reads differ"
            sample = owner.execute(sql.SQL("select to_jsonb(t) from {} t limit 1").format(table)).fetchone()[0]
            app.execute("select set_config('pvc.companies','no-such-company',false)")
            assert app.execute(sql.SQL("select count(*) from {}").format(table)).fetchone()[0] == 0
            try:
                with app.transaction():
                    app.execute(
                        sql.SQL("insert into {} select * from jsonb_populate_record(null::{},%s)").format(table, table),
                        (Jsonb(sample),),
                    )
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError(f"{name}: foreign INSERT permitted")
            col = sql.Identifier(columns[0])
            for statement in (
                sql.SQL("delete from {}").format(table),
                sql.SQL("update {} set {}={}").format(table, col, col),
            ):
                try:
                    with app.transaction(force_rollback=True):
                        assert app.execute(statement).rowcount == 0, f"{name}: foreign mutation permitted"
                except psycopg.errors.InsufficientPrivilege:
                    assert name == "audit_events", f"{name}: runtime write grant missing"
            app.execute("select set_config('pvc.companies','beacon-pricing',false)")
            try:
                with app.transaction(force_rollback=True):
                    changed = app.execute(sql.SQL("update {} set {}={}").format(table, col, col)).rowcount
                    assert name != "audit_events" and changed == expected, f"{name}: own UPDATE failed"
            except psycopg.errors.InsufficientPrivilege:
                assert name == "audit_events"
            checked.append(name)
        with app.transaction(force_rollback=True):
            app.execute("select set_config('pvc.companies','restore-probe',true)")
            app.execute("insert into companies(company_id,name) values('restore-probe','synthetic')")
            assert app.execute("delete from companies where company_id='restore-probe'").rowcount == 1
    return sorted(checked)


def main() -> int:
    import psycopg

    configure_logging(stream=io.StringIO())
    admin = os.environ["PVC_ADMIN_DATABASE_URL"]
    src, dst = f"pvc_drill_src_{uuid.uuid4().hex[:6]}", f"pvc_drill_dst_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{src}"')
        c.execute(f'create database "{dst}"')
    tmp = Path(tempfile.mkdtemp())
    role = None
    try:
        src_admin = db_url(admin, src)
        role, password = create_test_role(src_admin)
        upgrade(src_admin)
        repo = PostgresRepository(db_url(admin, src, role, password), FileSystemEvidenceStore(tmp / "ev"))
        ctx = RunContext(repo=repo, adapter=FixtureAdapter(), policy=get_policy())
        for cid in COMPANIES:
            with security.principal_scope(security.system_principal(cid)):
                rec, _ = primary.start(ctx, cid, "drill")
                anyio.run(lambda rid=rec.run_id: primary.execute(ctx, rid, backoff_s=0))
        repo.close()
        seed_monitoring(src_admin)
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
        checked = verify_rls(dst_admin, db_url(admin, dst, role, password))
        size_kb = dump.stat().st_size // 1024
        line = (
            f"| {datetime.now(UTC):%Y-%m-%d %H:%M} UTC | local PostgreSQL 18 | {sum(before.values())} rows, "
            f"{size_kb} KB dump | {t_dump:.2f} s | {t_restore:.2f} s | all {len(before)} table counts match; "
            f"read/write RLS verified on {len(checked)} tables | pass |"
        )
        log = ROOT / "docs" / "runbooks" / "restore-drill-log.md"
        if not log.exists():
            log.write_text(
                "# Restore drill log (PVC-142)\n\n| When | Environment | Data | Dump | Restore | "
                "Checks | Result |\n|---|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        with log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(line)
        return 0
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            for db in (src, dst):
                c.execute(f'drop database if exists "{db}" with (force)')
        shutil.rmtree(tmp, ignore_errors=True)
        if role:
            drop_test_role(admin, role)


if __name__ == "__main__":
    raise SystemExit(main())
