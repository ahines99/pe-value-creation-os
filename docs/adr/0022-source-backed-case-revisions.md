# ADR 0022: Source-backed research revisions and structured lessons

Status: accepted for the constructed research lane.

## Problem

The operating-source forecast could challenge a case but was a separate exhibit.
Its constraints did not become a persisted case revision or participate in the
original / frozen-close / current-forecast comparison. A reviewer could not bind
a decision to that source challenge or retain a correction and its reasoning.

## Decision

Add an explicitly requested `schema_version: 2` payload to the existing immutable
case-revision ledger. Keep the v1 payload unchanged: adding default fields to v1
would change previously signed revision hashes. Old requests may still omit the
v1 version. v2 requires an operating plan, an exactly bound constructed source
book, a parent revision ID/hash, and structured authored lessons. It cannot be
the original revision, and a later v1 revision cannot silently discard its source
basis. Existing case identity, calendar and initiative-lineage constraints apply.

Each lesson binds the prior initiative's driver assumptions and exact current
source records. Store the prior assumption values and previous/current source-row
snapshots and hashes in the immutable financial result. Source-kind validation
prevents invoice evidence being attached as a vendor-service lesson. Hash binding
proves identity, not truth, causality or independent review of the narrative.

Use the shared source forecast and dated ledger, retaining the latest assumptions
and all scheduled costs. Persist monthly, day-100, yearly, funding and source
disposition results. Omit duplicate daily entries and reference forecasts from
the stored snapshot; exact inputs remain in the signed payload and reproduce the
daily ledger through `pvc operating-sources`. The calculation fingerprint binds
input hashes and calculator version; the revision hash also covers actual outputs.
Source-bounded terms do not establish maintainable exit value: valuation is
explicitly unavailable in v2 financial snapshots.

No new table or migration is required. Reuse the existing repository/API paths,
company-scoped forced RLS, append-only rows, compare-and-swap parent, atomic audit,
exact-hash research reviews and company retention deletion. A source-based close
can be explicitly frozen after its own qualifying review; adding a source revision
alone never changes an existing close baseline. Readers must understand v2 before
writers are enabled; older binaries cannot deserialize it. No live showcase data
is migrated or reset by generating the demonstration.

## Rehearsal

`pvc source-review-demo` combines the existing realization and delivery replays
with two additional source-backed revisions. Revision 3's 50% capture assumption
is retained; the original source exhibit used 65%, so its headline differs.
Revision 4 requests changes in simulation; revision 5 removes vendor-release
evidence and receives simulated acceptance of the corrected adverse model.
All contract, service and invoice records remain fictional.

The five-month accounting differences, signed claims, residuals, frozen close and
withdrawn delivery receipt stay unchanged. Source correction is authored, not an
automatic financial inference from work withdrawal. Exercise dates are distinct
from actual persistence timestamps. The forecast is a retrospective whole-horizon
re-estimate, not actuals plus remaining forecast or historical point-in-time replay.
No human, model or service review can turn it into company intervention authority.

## Verification and remaining limits

Memory and restricted-role PostgreSQL tests cover immutable outputs, old published
v1 hash compatibility, source/lesson/parent tampering, stale versions, audit rollback,
tenant scope, deletion, explicit source-based baseline designation, observations,
API round trips and forged/human authority rejection. The installed-package replay
and responsive browser checks exercise the same end-to-end narrative.

Private-data ingestion remains unsupported. Sponsor authorization, independent
accounting/commercial review, observed company outcomes, initiative splits,
point-in-time publication vintages and maintainable exit/proceeds modeling remain
separate work. The [pilot package](../pilot/permissioned/README.md) documents the
entry evidence; preparing it does not start a pilot.
