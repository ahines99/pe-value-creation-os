# Database restore and drill (PVC-142)

Targets: **RPO 5 minutes** (RDS point-in-time recovery), **RTO 1 hour**.

## Production restore
1. Declare an incident. Stop the worker (desired count 0) so nothing writes during recovery.
2. Restore RDS to a new instance at the chosen point in time (console, or `aws rds restore-db-instance-to-point-in-time`).
3. Point the `DATABASE_URL` and `PVC_MIGRATION_DATABASE_URL` secrets at the new instance, confirm the migration revision (`pvc db check` against a scratch copy, or `select version_num from alembic_version`), then redeploy the services.
4. Evidence originals live in S3 with versioning and Object Lock and are unaffected by a database restore. Evidence ids are deterministic, so the next adapter load re-registers any rows created after the restore point.
5. Resume paused or interrupted runs with `pvc resume`.

## Drill
`scripts/restore_drill.py` seeds a database through the workflow, dumps it with `pg_dump -Fc`, restores it into a fresh database with `pg_restore`, verifies row counts and row-level security on the restored copy, and appends the timings to [restore-drill-log.md](restore-drill-log.md). The local drill has been run; a drill against RDS must be run once the production environment exists.
