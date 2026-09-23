# On-call and incident process (PVC-148)

**Status:** process defined. The rotation needs named people before general availability.

## Rotation
- Weekly primary and secondary engineering on-call, with a Monday handover that reviews open incidents.
- `severity=page` alerts page the primary (availability fast burn, stuck runs, scope-denial spikes). `severity=ticket` alerts are triaged the next business day.

| Week | Primary | Secondary |
|---|---|---|
| _to be staffed_ | | |

## Severities
| Sev | Definition | Response |
|---|---|---|
| 1 | Suspected cross-company exposure, data loss, or both services down | Page immediately; security lead joins; updates every 30 minutes |
| 2 | One service down, SLO fast burn, or approvals blocked | Page; updates hourly |
| 3 | Degraded: slow steps, adapter outage for one company | Ticket; next business day |

## Incident template
```text
Title / Sev / Start time / Detected by
Impact: companies, runs, users affected
Timeline:
Actions taken (with audit event ids):
Resolution:
Follow-up tickets:
```

## Post-incident review
A blameless review within 5 working days for Sev 1 and 2: timeline, contributing factors, what detection missed, and at least one new regression test or alert.
