# ADR 0020: constructed execution receipts and delivery-to-claim links

Status: implemented, September 28, 2026. Constructed operating exercise only.

A schedule proposes work; it does not establish that a named operator performed
it or that a reviewer accepted the result. The execution ledger adds separate
assignment, steering, delivery, acceptance and claim-link receipts against an
exact frozen hypothetical-close baseline. Original plan dates remain unchanged.

## Separate records and authority

Each `ExecutionRequest` carries the baseline ID/hash, human/simulation mode,
exercise effective date, typed payload, hashed constructed evidence, rationale,
ingestion key and exact previous receipt. Every kind has its own stable stream:
resource assignment, initiative steering, task delivery, task acceptance, or one
attribution-row/initiative link. Streams retain history and monotonic effective
dates; a canonical composite stream hash avoids delimiter collisions.

- Assignment nominates one operator and sponsor for a registered plan resource.
  Withdrawal makes the resource unassigned. Human identities are declared by a
  scoped approver and must match the reporting operator's authenticated subject;
  opaque identity-provider subjects are supported. Simulated identities carry a
  `simulated:` prefix and never stand in for actual participation.
- Steering records proceed, hold or stop for an initiative. Proceed requires a
  recorded operator/sponsor assignment. An authorized later proceed can resume
  activity; old holds remain in the dated history.
- Delivery records in-progress, blocked or completed work, its assignment,
  reported start/completion and evidence. The assignment must cover the whole
  work interval. A completion report can exist before acceptance and cannot
  activate a KPI. Recorded completion dates are operator representations; they
  do not independently validate quality, effort or actual capacity consumption.
- Acceptance binds the exact delivery ID/hash and, for acceptance, every exact
  prerequisite receipt. Work must be complete; prerequisite acceptance must
  precede the dependent work start. Review can accept, reject, request changes or
  withdraw. Technical review is distinct from steering: an accepted gate may be
  held. Human acceptance requires an approver other than the submitting operator.
- A claim link binds one positive financial allocation, its exact attribution
  batch/hash and its own initiative's benefit-gate acceptance. Explicit link
  withdrawal retains the original binding and does not remove the financial
  claim. A new link can explicitly replace the withdrawn one.

Simulation requires company write permission. Human delivery requires the named
human operator; other human events require approver authority. Human and
simulation streams cannot mix, even across receipts in the same company. These
contracts currently accept constructed evidence only. Human exercise receipts
still do not authorize a live company intervention or establish a real pilot.

## Validity and time

Latest delivery/acceptance corrections determine current evidence validity.
Correcting a submission invalidates acceptance of its old version. Withdrawing
a prerequisite review invalidates dependent acceptance and claim support. New
acceptance must explicitly bind the new prerequisite receipt; no silent transfer
occurs. Invalidated baseline research support also makes execution support
unusable. All old records and the original financial observations remain.

Assignments and steering use their dated history. Reassigning an operator after
completed work does not erase that work's valid historical assignment. A task
cannot claim the same assignment across a withdrawal or handoff. A March hold
does not remove February proceed authority; a hold at any point in February
prevents whole-month support even if activity resumes later that month.

A positive monthly allocation needs gate acceptance **before** the month starts
and uninterrupted proceed authority through the month. No monthly observation
is prorated to make a partial month qualify. Costs/adverse allocations stay in
the financial ledger regardless of readiness and are not promoted by positive
benefit links. Delivery support never validates the counterfactual or causality.

The report requires an explicit exercise review date. It applies latest evidence
corrections and dated authority history, exposes recorded receipts and omits
future observation periods from claim coverage. This is not a historical
knowledge-cutoff reconstruction. Effective dates are declared exercise dates;
actual recording timestamps are preserved separately. Events in different
streams can be reported out of effective-date order. Point-in-time learning
and historical replay remain separate roadmap work.

## Persistence and interfaces

Migration 0007 adds `case_execution_events`, with forced company RLS and
select/insert-only application grants. Composite foreign keys bind exact baseline
hash and mode, predecessor stream, supporting receipt/hash and attribution batch.
Application validation additionally checks prerequisite sets and domain meaning.
Unique initial receipts and predecessor links prevent forks. Company-retention
cascades/counts include the records; populated-history downgrade refuses erasure,
including when the table owner cannot see rows through forced RLS.

Both repositories serialize writes per case and atomically append the receipt
and audit event. Exact retries by the same author return the old receipt without
new credit or audit entries. Changed content/author under the same key conflicts.
An old retry never reactivates superseded support. PostgreSQL reads assemble the
case, financial history and execution receipts in one coherent SELECT snapshot;
the read-only database role needs no write lock or UPDATE privilege.

- `POST /cases/{case_id}/execution-events` requires an explicit bearer credential.
- `GET /cases/{case_id}/execution/{baseline_id}?as_of=YYYY-MM-DD` reports
  assignments, planned/reported dates, current acceptance validity, steering,
  claim links, all active allocation coverage and preserved receipt history.

Cookie-only JSON mutation is rejected. Scope violations conceal case existence;
bad bindings return 422 and stale predecessors/idempotency collisions return 409.
Exact retries retain the endpoint's 201 status and return the existing receipt.

## Public demonstration and limits

`pvc execution-demo` reuses the realization replay through repository APIs, adds
authored January/February source books, and records the execution exercise in
isolated memory. It does not migrate or reset the live showcase.

The service gate is reported complete on December 30 but receives a request for
changes. Its corrected completion/acceptance on January 3 misses January
whole-month eligibility. February can qualify. A March hold preserves February
authority, but a subsequent withdrawn vendor review invalidates the February
support link. Two pricing links retain delivery support; none establishes
causality. Three intentionally rejected attempts leave no receipt/audit mutation;
the authored replay manifest separately records those expected challenges.

At the final exercise review, six of seven work packages retain acceptance. Five
recorded months show measured EBITDA difference 61,000 and pre-tax cash 185,000,
financial claims 18,000 and 166,000, and residuals 43,000 and 19,000. These financial
figures do not change when delivery support is withdrawn. All identities and
decisions are simulated; actual company execution and realized value remain null.

The increment does not complete richer source-level operating schedules, actual
hours/capacity verification, private-data ingestion, independent quality review,
KPI/initiative split lineage, exit/learning records, point-in-time replay, or the
sponsored pilot. The pilot package now uses this as an execution rehearsal.
