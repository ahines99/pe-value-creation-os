# ADR 0002: Explicit state machine for workflows (no Temporal/Prefect yet)

- **Status:** accepted (revisited in ADR 0006, PVC-047)
- **Date:** 2026-09-23
- **Ticket:** PVC-007

## Context
The primary workflow is eight steps with one parallel fan-out and one human approval pause. It needs checkpointing, resume, idempotent reruns, bounded retries, and timeouts.

## Decision
Implement a small runner (`pe_value_os.workflows.base.run_steps`) that checkpoints `RunState` to PostgreSQL after every step and skips completed steps on resume.

## Consequences
- No extra infrastructure; the database is already the system of record.
- We own retry/timeout semantics and must test them (PVC-044, PVC-046).
- Revisit when we need durable timers across many runs, distributed workers, or long-running activities measured in hours.
