# ADR 0032: Private source custody and finance decisions

Status: Accepted for implementation; deployment and pilot acceptance are separate.

## Context

Preflight and a stored processing grant do not establish that an exact source was
received under still-current permission or that finance accepted it. Separate
file writes and database receipts can also leave orphaned private data after a
failed audit write. Source corrections must not inherit an earlier acceptance.

## Decision

Store bounded original ledger bytes in the same PostgreSQL row/transaction as an
immutable intake receipt. Serialize receipt writes, finance decisions and source
reads with grant/revocation writes using the company row lock. Apply the equivalent
lock and rollback behavior in memory. The API supplies the configured processing
environment; callers cannot select it.

Version each dataset as a replacement stream with exact predecessor hashes.
Persist quarantine and corrections. Record append-only human finance decisions
against exact intake hashes, requiring reproducible preflight before acceptance.
An accepted-source read also requires the current dataset and review heads and a
current grant. Historical retries return historical receipts without reactivating
permissions. No source receipt or finance decision authorizes business operations.

Expose separate authenticated private API routes with bounded bodies, generic
validation errors and no public/MCP export. Force company row-level security and
insert/select-only runtime table access. Preserve minimal audit history during
whole-company offboarding; refuse populated migration downgrades.

## Consequences

The 10 MiB source cap bounds transaction and database storage cost. Larger export
support will need an explicitly designed object-custody protocol rather than an
uncoordinated file write. Company-wide locking prioritizes consistent authority
over parallel intake throughput for this bounded pilot workflow.

This increment does not integrate private data into the constructed-only case
contracts or establish timed source deletion, legal holds, backup disposal,
external agreement validity or independent finance judgment. Those requirements
remain visible in the [private intake guide](../pilot/permissioned/intake-records.md)
and [completion checklist](../portfolio/remaining-work.md).
