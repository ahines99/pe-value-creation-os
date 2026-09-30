# PE Value Creation OS - demo report

All companies are fictional fixtures. Every number comes from deterministic tools.

## 1. Success path: Beacon Scheduling Systems (pricing leak)
- Run `73b4f667` finished at **awaiting_approval** (step `human_approval`).
  - Deflect tier-1 support with AI self-service: base-case run-rate EBITDA 9,552 (low -31,020, high 61,716); 2 evidence items; calc `value-case/2`
  - Discount governance in mid-market: base-case run-rate EBITDA 215,006 (low 89,586, high 403,136); 6 evidence items; calc `value-case/2`
  - Enforce contracted renewal uplifts: base-case run-rate EBITDA 351,942 (low 180,483, high 649,738); 6 evidence items; calc `value-case/2`
  - Migrate legacy price-book customers: base-case run-rate EBITDA 380,650 (low 138,418, high 605,579); 6 evidence items; calc `value-case/2`
  - Improve sales and marketing efficiency: base-case run-rate EBITDA 191,160 (low 79,650, high 371,700); 2 evidence items; calc `value-case/2`
- 100-day plan: 3 workstreams, total base-case run-rate 1,148,309 (in-year 739,200).

## 2. Human approval through the approval API, worker resumes
- Unauthenticated approval attempt: HTTP 401.
- Approver decision recorded: HTTP 200, decided_by `human:demo-approver`.
- Worker tick resumed 1 run(s); run is **complete**; 5 KPIs activated; 5 KPI observations recorded (0 after the plan started; earlier readings are baselines).

## 3. Controlled pause: Delta Ledger Tools (broken data)
- Run paused at **needs_evidence** in `data_sufficiency`: 1 of 4 analyses have sufficient data; policy requires 2.
  - unit_economics: P&L is missing months: 2025-02-01, 2025-10-01, 2025-11-01
  - pricing: Invoices extract dated 2025-12-31 is 258 days old (limit 45)
  - pricing: Contracts dataset is missing
  - ai_opportunity: P&L is missing months: 2025-02-01, 2025-10-01, 2025-11-01
- 2 suspicious-content findings recorded (prompt-injection text treated as data, not followed).

## 4. Injected failure the run survives: pricing diagnostic fails for Cedar Field Analytics
- Run reached **awaiting_approval** with levers ['ai_automation', 'retention', 'sales_efficiency']; recorded gap: diagnostics.pricing: SourceError: injected fault at branch:pricing.

## 5. Injected failure that fails cleanly, then resumes
- First attempt: **failed** at `value_modeling` (value_modeling: SourceError: injected fault at step:value_modeling).
- After `pvc resume`: **awaiting_approval**; completed steps were not re-executed.
- Audit trail for this run: 20 events, e.g. run_awaiting_approval, run_requested, run_resumed, step_completed, step_failed, step_started.
