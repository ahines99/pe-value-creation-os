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
3. The operator runs `pvc offboard --company <id> --confirm`. The command writes `company_offboarding_started`, deletes database rows (all company-scoped tables) and every evidence object version, then writes `company_offboarded` with counts.
4. Remove the company from `PVC_WORKER_COMPANIES` and from identity-provider claims.

Verified by `tests/test_ops.py::test_offboarding_deletes_data_but_retains_audit` (in-memory) and `tests/test_repository_contract.py::test_kpis_notifications_and_deletion` (in-memory and PostgreSQL).

Object Lock in governance mode lets the deletion role bypass retention with `BypassGovernanceRetention`. Compliance mode would block offboarding deletion and must not be used for this bucket.
