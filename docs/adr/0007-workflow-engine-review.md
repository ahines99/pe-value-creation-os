# ADR 0007: Keep the explicit state machine (review of ADR 0002)

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-047

## Context
ADR 0002 chose a small checkpointing runner. By R0.5 the system needs: per-step timeouts and transient-only retries
(PVC-044), resume after crash and after human decisions (PVC-041/061), parallel diagnostics (PVC-042), approval
escalation timers (PVC-064), and scheduled KPI refresh (PVC-121).

## Assessment
| Need | Current mechanism | Gap |
|---|---|---|
| Retries, timeouts | `Runner._attempt` with `anyio.fail_after` and bounded backoff | none |
| Durable resume | state checkpoint per step in PostgreSQL; `claim_runnable` with `FOR UPDATE SKIP LOCKED` | none |
| Timers | worker tick (approval expiry, KPI cadence) | minute-level precision only; acceptable |
| Distributed workers | row locks with stale-lock takeover (15 min) | adequate for tens of runs per hour |
| Long activities (hours) | none needed; runs complete in seconds | none |

## Decision
Keep the explicit state machine. Revisit if any of these occur: runs longer than the lock takeover window, more
than one worker pool per region, sub-minute timer requirements, or cross-service sagas.

## Consequences
No new infrastructure. Load test (PVC-143) must confirm claim/lock behaviour under concurrency.
