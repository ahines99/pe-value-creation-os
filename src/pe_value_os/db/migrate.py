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


def scram_sha256_verifier(password: str, *, salt: bytes | None = None, iterations: int = 4096) -> str:
    """PostgreSQL SCRAM-SHA-256 verifier for a password (RFC 5802/7677), computed client-side.

    `ALTER ROLE ... PASSWORD '<verifier>'` stores it as-is, so the plaintext never reaches the server and never
    appears in server logs (RDS logs DDL statements, including ALTER ROLE, under log_statement=ddl).
    """
    import base64
    import hashlib
    import hmac
    import os
    import unicodedata

    salt = salt or os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", unicodedata.normalize("NFKC", password).encode(), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def bootstrap_roles(admin_url: str, passwords: dict[str, str] | None = None) -> None:
    """Create the three roles if missing and (optionally) set their passwords, sent as SCRAM verifiers."""
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(ROLES_SQL.read_text(encoding="utf-8"))
        for role, pw in (passwords or {}).items():
            conn.execute(
                sql.SQL("alter role {} with password {}").format(
                    sql.Identifier(role), sql.Literal(scram_sha256_verifier(pw))
                )
            )
