"""Migration helpers (PVC-030). `python -m pe_value_os.db.migrate_check` runs the CI round trip."""

from __future__ import annotations

import os
from pathlib import Path

MIGRATIONS = Path(__file__).with_name("migrations")
ROLES_SQL = Path(__file__).with_name("roles.sql")


def sqlalchemy_url(url: str | None = None) -> str:
    raw = url or os.environ.get("PVC_MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("Set PVC_MIGRATION_DATABASE_URL or DATABASE_URL")
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix) :]
    return raw


def _config(url: str | None):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(url).replace("%", "%%"))
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    from alembic import command

    command.upgrade(_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    from alembic import command

    command.downgrade(_config(url), revision)


def current(url: str | None = None) -> str | None:
    from sqlalchemy import create_engine, text

    engine = create_engine(sqlalchemy_url(url))
    try:
        with engine.connect() as conn:
            try:
                return conn.execute(text("select version_num from alembic_version")).scalar()
            except Exception:
                return None
    finally:
        engine.dispose()


def bootstrap_roles(admin_url: str, passwords: dict[str, str] | None = None) -> None:
    """Create the three roles if missing and (optionally) set their passwords."""
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(ROLES_SQL.read_text(encoding="utf-8"))
        for role, pw in (passwords or {}).items():
            conn.execute(sql.SQL("alter role {} with password {}").format(sql.Identifier(role), sql.Literal(pw)))
