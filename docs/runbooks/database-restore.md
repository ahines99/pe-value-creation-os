# Database restore and drill (PVC-142)

Targets: **RPO 5 minutes** (RDS point-in-time recovery), **RTO 1 hour**.

Connection URLs are plain task environment values that Terraform builds from the instance's address (`compute.tf`, `database.tf`). They are not secrets. The procedure below keeps the address unchanged by giving the restored instance the original identifier, so no configuration has to change.

## Production restore

Use administrator credentials for the environment's account. `<env>` is `staging` or `production`; the instance identifier is `pvc-<env>`.

1. **Declare an incident.** Stop writes: set the `worker`, `mcp` and `api` services to 0 tasks (`aws ecs update-service --desired-count 0`).
2. **Read the settings to reuse.** In `infra/terraform/envs/<env>/`, run `terraform state show module.pvc.aws_db_instance.this`. Note `db_subnet_group_name`, `vpc_security_group_ids`, `parameter_group_name`, `ca_cert_identifier` and `multi_az`.
3. **Restore to a new instance** with those settings. The defaults would use the default security group and parameter group, and that would turn `rds.force_ssl` off.
   ```bash
   aws rds restore-db-instance-to-point-in-time \
     --source-db-instance-identifier pvc-<env> --target-db-instance-identifier pvc-<env>-restore \
     --restore-time <UTC timestamp> \
     --db-subnet-group-name <subnet group> --vpc-security-group-ids <db security group> \
     --db-parameter-group-name <parameter group> --ca-certificate-identifier <ca> \
     --multi-az --deletion-protection --copy-tags-to-snapshot --no-publicly-accessible
   aws rds wait db-instance-available --db-instance-identifier pvc-<env>-restore
   ```
   The restored instance keeps the source's KMS key.
4. **Verify the copy.** Connect as the master user (TLS required) and check the following:
   - `show rds.force_ssl` returns `on`.
   - `select version_num from alembic_version` shows the expected revision.
   - Row counts look right for the restore point.
5. **Swap identifiers**, so the original address now points at the restored instance:
   ```bash
   aws rds modify-db-instance --db-instance-identifier pvc-<env> --new-db-instance-identifier pvc-<env>-pre-restore --apply-immediately
   aws rds wait db-instance-available --db-instance-identifier pvc-<env>-pre-restore
   aws rds modify-db-instance --db-instance-identifier pvc-<env>-restore --new-db-instance-identifier pvc-<env> --apply-immediately
   aws rds wait db-instance-available --db-instance-identifier pvc-<env>
   ```
6. **Re-point Terraform state** at the restored instance. Then run a plan, which must not replace anything:
   ```bash
   terraform state rm module.pvc.aws_db_instance.this
   terraform import module.pvc.aws_db_instance.this pvc-<env>
   terraform plan   # expect in-place changes at most (for example tags); never "must be replaced"
   ```
7. **Re-apply offboarding.** A point-in-time restore brings back every company offboarded after the restore point. Their evidence objects are already gone from S3, so the restored rows would point at missing evidence. From the offboarding tickets (the database audit log was restored too), list the companies offboarded after the restore time, and run the `offboard` task again for each one (see [data_retention.md](../data_retention.md)).
8. **Restart.** Set the services back to their counts through Terraform (`terraform apply`), then resume paused or interrupted runs with `pvc resume`. Evidence ids are deterministic, so the next adapter load re-registers any evidence rows created after the restore point.
9. **Clean up.** After a day of normal operation, delete `pvc-<env>-pre-restore` with a final snapshot.

## Drill
`scripts/restore_drill.py` does the following:
- seeds a database through the workflow;
- dumps it with `pg_dump -Fc` and restores it into a fresh database with `pg_restore`;
- compares counts for every public table and the migration revision;
- seeds monitoring/notification data, verifies forced RLS and exact scoped reads on every tenant table including child evidence links;
- rejects foreign INSERT/UPDATE/DELETE, verifies own-company UPDATE, audit append-only grants and an own-company INSERT/DELETE round trip in rolled-back transactions;
- creates and removes a unique temporary runtime login; shared-role passwords never change;
- appends the timings to [restore-drill-log.md](restore-drill-log.md).

The local drill has been run. The drill against RDS, following the procedure above, must be run once the environment exists (PVC-142).

The 2026-09-27 rerun verified all 17 public table counts and read/write RLS on 16 tenant tables. This local database dump/restore does not prove AWS PITR timings, S3 recovery, or production RPO/RTO.
