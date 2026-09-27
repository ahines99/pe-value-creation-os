# Runbooks (PVC-141)

| Runbook | Alert or trigger |
|---|---|
| [stuck-run.md](stuck-run.md) | `PvcStuckRuns`, `PvcStepLatencySlo`, `PvcApprovalOverdue` |
| [service-errors.md](service-errors.md) | `PvcAvailabilityFastBurn`, `PvcAvailabilitySlowBurn` |
| [adapter-outage.md](adapter-outage.md) | `PvcAdapterFailures`, runs failing in `intake` |
| [model-outage.md](model-outage.md) | `PvcModelUnavailable`, runs paused with `model_unavailable` |
| [bad-calculation-release.md](bad-calculation-release.md) | A calculation defect found after release |
| [data-exposure.md](data-exposure.md) | `PvcScopeDenialsSpike`, any suspected cross-company exposure |
| [database-restore.md](database-restore.md) | Data loss or corruption; quarterly drill |
| [oncall.md](oncall.md) | Rotation, severities, incident template, post-incident review |

All commands assume an operator shell with `PVC_OPERATOR_COMPANIES` scoped to the affected company and `DATABASE_URL` pointing at the environment. Every operator action is audited.
