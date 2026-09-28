# ADR 0013: immutable research cases and exact-version reviews

Status: implemented for constructed research cases. This is an additive foundation
for the lifecycle demonstration, not a completed realization ledger or pilot.

## Identity and storage

Migration 0004 adds `investment_cases`, `case_revisions` and `case_reviews`. It
preserves the existing diagnostic plans, approval records and KPI semantics. Both
memory and PostgreSQL repositories implement the same case operations.

A case belongs to a registered company scope and retains its case ID and currency.
Its first revision must be underwriting. The original revision pointer remains
fixed; it identifies the original authored forecast, not an approved investment.
The current pointer advances by one revision at a time. Every append requires
the exact expected parent. The database locks the case row, checks the parent,
inserts the revision, advances the head and writes its audit event in one
transaction. Two writers against one parent produce one success and one conflict.

Revisions contain the existing typed underwriting input, an optional exact-bound
operating plan, the question under review, counterevidence and unresolved items.
The comparison calendar, reference company and initiative identities stay stable.
Splits/mergers are rejected until an explicit lineage mapping is implemented.
The effective date is distinct from actual recorded time; exercise dates do not
assert an actual transaction or historical information availability.

Each revision stores the resulting financial and schedule JSON as immutable text
alongside the input. A hash covers the entire normalized record, including actor,
parent, reason, dates and stored results. Loading verifies the hash. Future
calculator versions cannot silently recompute and replace the original output.
Frozen nested input records and immutable JSON strings prevent accidental mutable
references from changing a returned in-memory revision.

## Review and authority

Research review is separate from existing operating-plan approval. It cannot
activate KPIs, authorize interventions, mark a company acquired or certify value.
Every receipt binds the exact stored revision ID and hash. Acceptance, request
for changes and rejection require the current revision. A reviewer may withdraw
their own earlier receipt after a newer revision exists.

Actual reviews require a human principal, the approver role, `pvc.approve` scope
and the existing approval-client allowlist checks when token scopes apply.
Constructed simulation receipts require `pvc.write`; their service/model actor
and simulation mode remain visible. They never become human receipts. Actor and
recording time come from authenticated context, not request JSON.

A reviewer has one initial receipt per revision and mode. Correction/withdrawal
appends a new receipt referencing the latest receipt by that same reviewer on
that same revision and mode. A correction cannot overwrite another person's
judgment or turn a simulation into an actual human act. All prior receipts remain.
Duplicate initial receipts and branching corrections return conflicts.

## Database and retention boundaries

All three tables use forced company RLS. Composite foreign keys bind company,
case, parent revision, exact review hash and correction chain. Runtime roles have
no UPDATE or DELETE privileges on revision/review rows. Only case head columns
can update; a trigger requires a new linked revision and preserves the original.
Schema owners and superusers remain outside the runtime privilege boundary.

Authorized whole-company offboarding still deletes company data. The existing
company deletion cascades through the new records, with deletion counts included.
This is an explicit retention exception to append-only history, not a general
revision-edit API. Audit records follow the existing retention design.

Downgrade refuses to erase populated case history. Before any rollback of a
database with cases, use an authorized backup/restore plan; do not offboard a
company merely to bypass the guard. Empty case tables can downgrade without
changing legacy runs or approved plans. The live local showcase is not migrated
by the public demonstration command.

## API and replay

The existing authenticated API exposes:

| Route | Behavior |
|---|---|
| `POST /cases` | Register a constructed case in an existing company scope |
| `GET /cases/{case_id}` | Read original/current revisions, receipt history and modeled comparison |
| `POST /cases/{case_id}/revisions` | Append with `expected_parent_revision_id` and a typed draft |
| `POST /case-revisions/{revision_id}/reviews` | Add an exact-hash actual or simulated receipt |

JSON writes require an explicit bearer credential; session cookies cannot cause
state changes through these routes. Conflict returns 409, invalid contracts 422,
and invisible records 404. The human approval audience/client boundary is reused.
No new case-review tool is exposed on the model's MCP surface.

`pvc case-history-demo` uses an isolated in-memory repository and the same
operations to render two constructed revisions with explicitly simulated service
reviews. PostgreSQL behavior is tested separately with the restricted runtime
role. Numeric replay is deterministic; receipt UUIDs and actual recording times
are new per replay. No human review or actual result is manufactured for publication.

## Verification and remaining work

Contract tests cover memory/PostgreSQL parity, immutable results, stale parent/hash,
two writers, correction/withdrawal, actor and scope constraints, source rejection,
audit rollback, cross-company references, runtime mutation denial, company deletion,
populated legacy upgrade and guarded rollback. API tests exercise bearer versus
cookie writes, actor injection, approval-client restrictions, model denial and
conflict responses. CLI/browser checks cover the public history walkthrough.

Still required: a sourced full commercial thesis and its typed evidence assessment,
explicit reviewed close-baseline designation, actual milestone/assignment evidence,
append-only actuals/attribution records, lessons and historical filing replay. The
current comparison reports `modeled_only` and actuals unavailable. Public/constructed
source contracts do not yet admit a real permissioned investment or company pilot.

The separate reviewed hypothetical-close designation is now implemented under
[ADR 0018](0018-reviewed-close-baselines.md). It preserves this revision contract
and does not introduce observed actuals or operating authorization.
