from __future__ import annotations

import os
import uuid

# Tests run in dev mode: the MCP server and approval API refuse to start without auth outside dev.
os.environ.setdefault("PVC_ENV", "dev")
from urllib.parse import urlsplit, urlunsplit

import pytest

from pe_value_os import security
from pe_value_os.adapters import repositories
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.repositories import InMemoryRepository

PG_ADMIN_URL = os.environ.get("PVC_TEST_DATABASE_URL")
APP_PASSWORD = "pvc_app_test_pw"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _with_db(url: str, db: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc
    if user:
        host = netloc.split("@", 1)[-1]
        netloc = f"{user}:{password}@{host}" if password else f"{user}@{host}"
    return urlunsplit((parts.scheme, netloc, f"/{db}", parts.query, parts.fragment))


@pytest.fixture(scope="session")
def pg_database():
    """A fresh migrated database for the session. Returns (admin_url, app_url)."""
    if not PG_ADMIN_URL:
        pytest.skip("PVC_TEST_DATABASE_URL not set")
    import psycopg

    from pe_value_os.db.migrate import bootstrap_roles, scram_sha256_verifier, upgrade

    name = f"pvc_test_{uuid.uuid4().hex[:8]}"
    login = f"{name}_app"
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'create database "{name}"')
    admin_url = _with_db(PG_ADMIN_URL, name)
    try:
        bootstrap_roles(admin_url)
        upgrade(admin_url)
        with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
            conn.execute(
                psycopg.sql.SQL("create role {} login password {} in role pvc_app").format(
                    psycopg.sql.Identifier(login), psycopg.sql.Literal(scram_sha256_verifier(APP_PASSWORD))
                )
            )
        yield admin_url, _with_db(PG_ADMIN_URL, name, login, APP_PASSWORD)
    finally:
        with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
            conn.execute(psycopg.sql.SQL("drop database {} with (force)").format(psycopg.sql.Identifier(name)))
            conn.execute(psycopg.sql.SQL("drop role if exists {}").format(psycopg.sql.Identifier(login)))


TABLES = (
    "audit_events, notifications, kpi_alerts, kpi_observations, kpi_definitions, approvals, plans, "
    "priority_scores, value_cases, opportunity_evidence, opportunities, finding_evidence, findings, evidence, "
    "workflow_runs, companies"
)


@pytest.fixture
def pg_repo(pg_database, tmp_path):
    import psycopg

    from pe_value_os.adapters.postgres import PostgresRepository

    admin_url, app_url = pg_database
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"truncate {TABLES} cascade")
    repo = PostgresRepository(app_url, FileSystemEvidenceStore(tmp_path / "evidence"), max_size=4)
    yield repo
    repo.close()


@pytest.fixture(params=["memory", "postgres"])
def repo(request, tmp_path):
    if request.param == "memory":
        r = InMemoryRepository(FileSystemEvidenceStore(tmp_path / "evidence"))
        yield r
    else:
        yield request.getfixturevalue("pg_repo")


@pytest.fixture
def as_companies():
    """Context-manager factory: `with as_companies("a", "b"): ...`"""

    def _scope(*companies: str, subject: str = "test"):
        return security.principal_scope(security.Principal(subject=subject, companies=frozenset(companies)))

    return _scope


@pytest.fixture(autouse=True)
def _reset_repository_singleton():
    yield
    repositories.set_repository(None)
