"""One-off database bootstrap for a managed PostgreSQL instance (PVC-132).

Runs as the `bootstrap` ECS task (infra/terraform/modules/pvc/compute.tf) with the RDS master credentials:

1. `pvc db bootstrap-roles`: creates pvc_migrator, pvc_app and pvc_readonly (src/pe_value_os/db/roles.sql)
   and sets their passwords from PVC_APP_DB_PASSWORD / PVC_RO_DB_PASSWORD / PVC_MIGRATOR_DB_PASSWORD.
2. Lets pvc_migrator create objects in schema `public`. On PostgreSQL 15+ `public` is owned by the database
   owner (the RDS master user) and nobody else may create in it, so migrations would fail without this grant.
   pvc_migrator then owns every table it creates, which keeps pvc_app subject to row-level security.

Idempotent: safe to re-run, for example after rotating a role password in Secrets Manager.
The admin URL carries no password; libpq reads it from PGPASSWORD (injected from the RDS-managed secret).
"""

from __future__ import annotations

import os
import sys

from pe_value_os.db import migrate


def main() -> int:
    admin_url = os.environ["PVC_ADMIN_DATABASE_URL"]
    passwords = {
        role: os.environ[var]
        for role, var in (
            ("pvc_app", "PVC_APP_DB_PASSWORD"),
            ("pvc_readonly", "PVC_RO_DB_PASSWORD"),
            ("pvc_migrator", "PVC_MIGRATOR_DB_PASSWORD"),
        )
        if os.environ.get(var)
    }
    migrate.bootstrap_roles(admin_url, passwords)

    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("grant usage, create on schema public to pvc_migrator")
    print(f"bootstrap: roles ready, passwords set for {sorted(passwords)}; pvc_migrator may create in public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
