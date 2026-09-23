# Source adapter outage

**Signals:** `PvcAdapterFailures`; runs failing at `intake` with `SourceError`; `kpi_unavailable` audit events.

1. Identify the source and company from the step error (`pvc status <run_id>`) or worker logs (`kpi_refresh_failed`).
2. Transient failures (timeouts, 5xx, rate limits) retry automatically. Persistent failures need the source owner: an expired credential, a schema change, or a network path.
3. Schema change: the adapter conformance suite (`tests/test_adapters.py`) fails against a recorded sample of the new payload. Update the mapping, add the sample, release.
4. Stale data: sufficiency checks pause affected runs with `stale_dataset`. Resume with `--accept-gaps` only if the approver agrees the stale data is acceptable; that decision is audited.
5. After recovery, resume paused runs with `pvc resume <run_id>`.
