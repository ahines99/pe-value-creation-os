# Data retention and deletion (PVC-144)

**Status:** engineering proposal. Retention periods are placeholders for the fund's legal and compliance team to confirm before general availability.

| Data class | Where | Retention | Deleted by offboarding |
|---|---|---|---|
| Source evidence originals (files, API payloads) | Evidence store (S3, Object Lock governance mode) | Life of the engagement + 90 days | Yes (`pvc offboard`, all object versions) |
| Derived analysis (findings, opportunities, value cases, priorities, plans, KPIs, notifications) | PostgreSQL | Life of the engagement + 90 days | Yes |
| Workflow runs and approvals | PostgreSQL | Life of the engagement + 90 days | Yes |
| Audit events | PostgreSQL `audit_events` (append-only) | 7 years (placeholder) | **No** — retained for accountability; contains ids and hashes, not source values |
| Application logs | CloudWatch | 90 days | Expire |
| Traces and metrics | Tracing backend / Prometheus | 30 days / 13 months | Expire |
| Database backups | RDS automated backups and snapshots | 35 days (production) | Expire; restore drills never restore an offboarded company into service |

## Offboarding procedure
1. The operating partner confirms the end of the engagement in writing (ticket id).
2. An operator scoped to that company runs `pvc audit-export --company <id> --out <file>` and hands the export to compliance.
3. The operator runs the offboarding. It writes `company_offboarding_started`, then deletes every evidence object version first and the database rows (all company-scoped tables) second, then writes `company_offboarded` with counts. If a step fails, it writes `company_offboarding_failed` and stops. Deletion is idempotent, so fix the cause and run it again.
   - **Deployed environments:** run the operator-only `offboard` task, whose role alone may delete evidence versions under Object Lock. The CD role cannot run it:
     ```bash
     aws ecs run-task --cluster pvc-<env> --task-definition pvc-<env>-offboard --launch-type FARGATE        --network-configuration "awsvpcConfiguration={subnets=[<app subnet ids>],securityGroups=[<pvc-<env>-offboard sg>],assignPublicIp=DISABLED}"        --overrides '{"containerOverrides":[{"name":"app","command":["pvc","offboard","--company","<id>","--confirm"],"environment":[{"name":"PVC_OPERATOR","value":"<your name>"},{"name":"PVC_OPERATOR_COMPANIES","value":"<id>"}]}]}'
     ```
     Check the task's log in `/ecs/pvc-<env>/offboard` for the counts.
   - **Local:** `PVC_OPERATOR_COMPANIES=<id> pvc offboard --company <id> --confirm`.
4. Remove the company from `PVC_WORKER_COMPANIES` and from identity-provider claims.
5. Record the offboarding (company, date, ticket) where the operations team keeps them. A database restore to an earlier point brings the company back, and this list is how it gets offboarded again (see [runbooks/database-restore.md](runbooks/database-restore.md)).

Verified by `tests/test_ops.py::test_offboarding_deletes_data_but_retains_audit` (in-memory), `tests/test_repository_contract.py::test_kpis_notifications_and_deletion` (in-memory and PostgreSQL), and `tests/test_audit_fixes.py::test_offboarding_deletes_evidence_first_and_audits_failures` (ordering and failure audit).

Object Lock in governance mode lets the deletion role bypass retention with `BypassGovernanceRetention`. Compliance mode would block offboarding deletion and must not be used for this bucket.

## Required reconciliation before deployment

The table above is the proposed business policy. Terraform currently proposes production evidence Object Lock of 2555 days and CloudWatch retention of 365 days; staging uses 30 days. These differ from engagement-plus-90-day evidence and 90-day application-log proposals above. Governance-mode deletion authority does not make the policies equivalent. Legal/compliance and operations must choose and record one approved set, update the environment variables/IaC, and validate expiration/deletion behavior before apply with real company data. Backup expiry and audit retention require the same approval.

| Reviewer | Role | Date | Approved periods and legal basis | Configuration / validation evidence |
|---|---|---|---|---|
| Pending | Legal/compliance | | | |
| Pending | Operations | | | |
