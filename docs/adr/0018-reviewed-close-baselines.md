# ADR 0018: reviewed hypothetical-close comparison baselines

Status: implemented, September 28, 2026. Constructed exercise only.

A current forecast can change during an ownership exercise. It must not silently
replace the baseline used to assess later results. Case revisions already retain
their inputs and calculator outputs; a separate designation now chooses an exact
close-validation revision and one of its stored scenarios.

## Contract and authority

`CloseBaselineRequest` binds the revision ID/hash, accepted review ID, review mode,
scenario, rationale and expected preceding designation. The revision must be the
case's current close-validation head, have a capacity plan and contain no blocked
tasks. Review identity, company, case, revision, content hash and mode must all
match; superseded receipts are ineligible. These checks run in the same repository
transaction as the designation and audit event.

Simulation requires company write permission. Human designation additionally
requires human approver authority. The service-generated public walkthrough uses
simulation exclusively. Neither mode represents an acquisition, intervention
authorization or observed result; all current investment cases remain classified
as constructed operating exercises.

Designations have immutable content hashes and separate per-mode sequences.
Concurrent writes use the expected previous designation; only one can win. An
explicit replacement preserves the earlier record and its frozen scenario. Reads
never invoke the financial or scheduling engines. Reforecasting advances the case
head without moving the designation.

A read projection reports `current_designation`, `supporting_review_status` and
`usable_for_comparison` separately. Replacing a designation does not make its
original, still-supported historical comparison invalid. Superseding or withdrawing
its supporting review makes that comparison unusable, while retaining its record
and original forecast for audit. A new accepted receipt requires a new explicit
designation; it is never transferred automatically. Later actuals must bind a
specific baseline and inspect this validity state.

## Storage and API

Migration 0005 adds `case_close_baselines`, with composite foreign keys to exact
review/revision/mode identity, one initial designation per mode, unique replacement
links, forced company RLS and select/insert-only application grants. No update or
individual delete is available. Authorized whole-company retention cascades include
the new records and counts. Downgrade refuses to erase history, including when
forced RLS would otherwise hide it from a non-superuser table owner.

`POST /cases/{case_id}/close-baselines` requires explicit bearer credentials;
browser cookies cannot authorize the JSON mutation. `GET /cases/{case_id}` includes
designation projections alongside revisions, reviews and original/current outputs.
There is no model-callable approval tool. The migration is verified only in
disposable test databases; the user's running showcase and existing decisions are
not migrated or reset by this increment.

`pvc case-history-demo` now freezes the reviewed, capacity-tested hypothetical-close
base scenario and renders its financial anchor, exact review and content hash.
The public walkthrough still reports no observed actuals or actual human review.
An actuals/attribution ledger, execution evidence and full lifecycle demonstration
remain separate work; this is a prerequisite, not completion of the broader goal.

## Verification

Memory and restricted-role PostgreSQL tests exercise freeze/reforecast behavior,
review withdrawal, replacement chains, stale writers and concurrency, scope,
mode separation, tampering, audit rollback, retention, blocked capacity, API
authentication/CSRF boundaries, immutable database privileges and guarded downgrade.
The existing revision, legacy-plan and migration checks remain in place. Browser
acceptance checks the new designation exhibit at all three portfolio viewports.
