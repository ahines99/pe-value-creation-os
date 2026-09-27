"""CI check: upgrade to head, downgrade to base, upgrade again (PVC-030)."""

from __future__ import annotations

import os
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

from .migrate import bootstrap_roles, current, downgrade, upgrade


def main() -> int:
    url = os.environ.get("PVC_TEST_DATABASE_URL")
    if not url:
        print("PVC_TEST_DATABASE_URL not set", file=sys.stderr)
        return 2
    import psycopg
    from psycopg import sql

    name = f"pvc_migration_check_{uuid.uuid4().hex}"
    parts = urlsplit(url)
    test_url = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    try:
        bootstrap_roles(test_url)
        upgrade(test_url)
        head = current(test_url)
        downgrade(test_url)
        assert current(test_url) is None, "downgrade to base left a revision behind"
        upgrade(test_url)
        assert current(test_url) == head
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))
    print(f"migrations round-trip ok (head={head})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
