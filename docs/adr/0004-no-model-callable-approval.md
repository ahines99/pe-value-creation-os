# ADR 0004: No model-callable approval

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-007

## Context
Plans produced by the workflow lead to management actions (price changes, headcount, contract changes). A model that can both propose and approve removes the human boundary the product promises.

## Decision
The MCP surface exposes `request_approval` only. Decisions are recorded exclusively through the authenticated human approval API (`POST /runs/{run_id}/approvals`), which requires a human principal. A test asserts no MCP tool can write an approval decision.

## Consequences
- An approval is always attributable to a person.
- Clients that want in-chat approval must hand off to the approval UI; this is intentional friction.
