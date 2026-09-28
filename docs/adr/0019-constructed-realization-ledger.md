# ADR 0019: constructed accounting comparisons and explicit attribution

Status: implemented, September 28, 2026. Constructed exercise only.

A favorable financial difference is not automatically initiative impact. The
ledger therefore stores a monthly accounting comparison separately from the
explicit claims made against it. Both are immutable, company-scoped and bound
to a reviewed hypothetical-close baseline. Neither represents a performed pilot.

## Measurement contract

An `ObservationRequest` binds the baseline ID/content hash, authored observed
and no-intervention source books and their canonical hashes, the exact frozen
initiative set, scope rationale and expected prior snapshot. The two books must
have identical case, currency, complete calendar month and `(row_id, component)`
coverage. Native-currency whole cents are required. Missing rows are not zeros;
all six income/cash components must be represented explicitly, including known
zeros. The calendar must exist in the frozen forecast.

Revenue, operating expense excluding D&A/interest/tax, implementation expense,
operating cash, working-capital cash and capex cash remain signed. Each book
declares independent component totals plus an EBITDA control. Mismatches are
retained visibly as unreconciled; they cannot support attribution or aggregate
comparison totals. A correction preserves the prior snapshot and requires a
new ingestion key and exact predecessor. Application code does not update rows.

Financial differences reuse the existing Decimal earnings/cash identity. The
ledger exposes neutral component names; the shared engine's pricing-driver
aliases are not used as causal labels for observed revenue changes. Collections
can affect cash without EBITDA; costs and negative residuals are not clipped.

## Claims, authority and corrections

An `AttributionRequest` binds one observation ID/hash and the baseline's review
mode. Each allocation names a source row, initiative, signed whole-cent amount,
hashed constructed support, confidence, rationale and alternative explanation.
Across initiatives, claims on a row cannot exceed its signed source difference.
Zero differences cannot support nonzero claims. A cap prevents over-allocation;
it does not prove causality, validate work acceptance or assess counterfactual
quality. Claim totals may exceed the net measured result when adverse rows are
unassigned; the negative residual remains visible alongside them.

Simulation requires company write authority. Human claims additionally require
a human approver. All public replay claims are service-authored simulations.
Empty allocation batches explicitly withdraw/reset claims. A correction binds
the latest batch; an observation correction makes its old claims historical
and leaves the new snapshot unassigned until fresh claims are recorded.

Keys are unique per case and record type. An exact retry by the same author
returns the original record without another audit event. Reusing the key for
changed content or another author conflicts. Returning an old retry receipt
does not reactivate that record after a correction or review withdrawal.

## Storage and reporting

Migration 0006 adds `case_observations` and `case_attributions`. Composite foreign
keys bind company/case/source hashes; predecessor links retain baseline/month
or observation/mode identity. Unique initial records and predecessor links
prevent forks. Forced company RLS and select/insert-only application grants
protect the immutable history. Authorized whole-company retention includes the
new tables. Downgrade refuses populated history even for an unscoped table owner.

Repository writes lock the case and atomically append the record and audit.
Memory uses the same transaction contract. PostgreSQL report reads use one
statement for a coherent committed snapshot and need no UPDATE privilege; the
read-only database role is tested. All forecast values come from persisted
revision outputs, without calculator or scheduler replay during report reads.

The report exposes original/current revision IDs and hashes, frozen baseline,
latest monthly snapshots, source controls, active claims, residuals and full
correction history. Superseding the supporting baseline review invalidates
comparison totals. Reforecasting does not move the baseline. Aggregates compare
only the same recorded months; one unreconciled submitted month withholds the
aggregate. Missing months remain unavailable, and no monthly source is prorated
into a day-100 actual. `actual_company_realized_value` remains null.

Authenticated endpoints:

- `POST /cases/{case_id}/observations`
- `POST /cases/{case_id}/attributions`
- `GET /cases/{case_id}/realization/{baseline_id}`

Writes require explicit bearer credentials; session cookies do not authorize
JSON mutations. Out-of-scope identities cannot discover the case. Invalid
bindings return 422, stale predecessors/key collisions return 409, and exact
import retries return the existing receipt with the endpoint's 201 status.

## Public replay and remaining scope

`pvc realization-demo` imports an explicitly authored fixture into isolated
memory through the repository APIs. Four source snapshots cover October–December
2026: the first November posting is corrected by 2,000 and attribution is
reconsidered. Measured EBITDA is −16,000 and cash +118,000; claims total −32,000
and +112,000, leaving +16,000 and +6,000 unassigned. October collections add
180,000 cash and no EBITDA. March's modeled reversal has no recorded actual.

A separate authored reforecast reduces future base pricing capture to 50%.
Capacity delays those benefits beyond December, so the first three forecast
months correctly remain unchanged. The current scenario re-estimates the whole
horizon; it is not an actual-plus-remaining forecast. Early revenue claims in
the fixture have no work-acceptance evidence and are explicitly challenged.

This increment does not implement private operating-data ingestion, accepted
execution events, independent finance review, a validated counterfactual,
learning from actual outcomes, verified causality or realized exit proceeds.
Those remain in the operating-partner roadmap. The prepared permissioned pilot
package can use this as a measurement rehearsal, not as evidence of a pilot.
