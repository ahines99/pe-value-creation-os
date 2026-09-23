# Stuck or slow run

**Signals:** `PvcStuckRuns` (run in `running` for more than 30 minutes), `PvcStepLatencySlo`, `PvcApprovalOverdue`.

1. Identify the run from the dashboard "Stuck runs" tile, then `pvc status <run_id>` for `current_step`, `errors` and `updated_at`.
2. Check the worker is alive: ECS service `worker` running count; logs for `worker_tick`. If a worker died mid-run, its lock expires after 15 minutes and another worker resumes from the last checkpoint. Restarting the service is enough.
3. If the step is waiting on a source system, follow [adapter-outage.md](adapter-outage.md). Step timeouts retry transient errors twice, then fail the run cleanly.
4. If the run is `failed`, read the last error in `pvc status`. After fixing the cause, resume with `pvc resume <run_id> --reason "<ticket>"`. Completed steps are not re-executed.
5. For `PvcApprovalOverdue`, the worker has already escalated to the policy contact. Chase the approver. Nothing is auto-approved.
6. Record an incident if the delay was user-visible ([oncall.md](oncall.md)).
