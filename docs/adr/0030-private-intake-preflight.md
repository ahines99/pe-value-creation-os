# ADR 0030: separate private intake preflight from admission

Date: September 29, 2026. Status: implemented increment; private intake and pilot
readiness remain incomplete.

## Context

The constructed operating case, source, execution and actuals contracts explicitly
reject real private records. Changing their classification literals would bypass
the very boundary that makes the public portfolio reproducible and publishable.
An authorized pilot needs a distinct route with scope, reconciliation, review,
corrections and retention. A sponsor is not available, so only fictional records
are suitable for the current engineering rehearsal.

## Decision

Add `diligence.private_intake` and `pvc pilot-intake-check` as a read-only,
operator-scoped preflight. It binds a normalized monthly ledger to an explicit
policy and export manifest; checks exact bytes, scope, processing dates, account
mapping and independent control totals; and writes a private review receipt.
Any defect quarantines the whole batch. No row is partly accepted.

The policy carries reference hashes rather than claiming to authenticate an
agreement or reviewer. Every receipt explicitly keeps permission verification,
finance review, admission and operating authority false. The successful state is
`ready_for_finance_review`, not `approved`. No public/private class conversion,
repository ingestion, model call or operational action is introduced.

The CLI uses explicit local operator company scope without reading a configured
source adapter. The underlying function additionally enforces human/operator and
OAuth read scope where applicable. This does not provide deployed authentication.

Outputs remain under `var/permissioned-pilot`, reject escapes/symlink redirects,
and cannot overwrite inputs or existing receipts. The public portfolio never
consumes this directory. Reference fingerprints establish identity, not truth or
external permission. Existing source and case contracts are preserved.

## Validation and next increment

`tests/test_private_intake.py` uses hand-worked debit/credit and cash controls,
row and manifest corruption, missing zeros, duplicate JSON keys, permission and
expiry boundaries, Decimal cancellation, private-path checks and CLI redaction.
Existing public-source rejection tests continue to protect their export boundary.

Persistent authorization/revocation, source custody, quarantine/correction
history, human finance acceptance, private-case integration and retention/deletion
remain required. Exclusive local receipt creation is not an immutable database
history or a tamper-proof approval. The next increment must bind these controls
before any real records are admitted; a preflight pass cannot stand in for them.
