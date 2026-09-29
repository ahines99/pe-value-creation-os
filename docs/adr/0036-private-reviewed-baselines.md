# ADR 0036: Human private-plan reviews and frozen comparison baselines

Status: Accepted for implementation; release and pilot acceptance are separate.

## Context

Private capacity proposals preserve source-bound financial timing but do not
establish human review or a fixed comparison anchor. A later forecast must not
silently replace the baseline, and withdrawing approval must remain possible
without processing a revoked source.

## Decision

Create separate immutable finance/operating review histories per exact capacity
revision, using the existing human approval-client boundary with distinct roles.
Require explicit role-specific assessments on acceptance. Require current named
processing permission for new substantive decisions; allow a scoped matching
reviewer to withdraw an accepted historical decision without source processing.
Disallow operating acceptance of blocked selected work.

Require two distinct current accepted reviewer identities and a human approver
to freeze a scenario from the current usable capacity plan. Store the exact
scheduled forecast, entity/currency, source identities and decision hashes.
Baseline designation is comparison authority only, not intervention permission.

Keep original proposals, decisions and baseline versions intact. Reproduce the
saved original source/financial/underwriting/plan chain under fresh permission for
baseline status. Report current source and review support separately. New forecasts
do not move the anchor; withdrawn/replaced reviews never silently reactivate an
old designation. An explicit replacement binds its predecessor.

Use company locking across decisions, freezing, withdrawal and source mutations;
store audit atomically. Add exact plan/case/review/parent foreign keys, forced
RLS, immutable runtime access, actor-bound idempotency, downgrade guards and
whole-company offboarding. Keep private routes separate from public exports/MCP.

## Consequences

Private plans can have accountable human review and preserved comparison versions
without becoming operating grants. Commercial truth and reviewer independence
remain external facts. The original proposal flags remain unchanged; later review
receipts carry the new authority. Historical records remain scoped-human-readable
after processing revocation, while source reproduction is denied until permitted.

Actuals/counterfactuals, attribution, private memo/review UX, intervention authority,
execution evidence and retention remain subsequent work. See the
[reviewed baseline guide](../pilot/permissioned/reviewed-baselines.md).
