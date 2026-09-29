# ADR 0028: Shared-pool initiative and KPI history

Status: implemented; exact release checks accompany the pull request. September 28, 2026.

## Decision

Case payload schema 5 composes the native allocation case and source-book schema 3
with explicit initiative/task lineage and scoped KPI definitions. Schema 4 retains
its disjoint source ownership contract. Earlier signed payloads and calculation
versions are unchanged; neither history is automatically converted to the other.

Every current KPI definition binds the complete exact source records for its pool,
the pool mode and its population share. A target change preserves that scope and
baseline. A different share, mode or source population requires a scope correction.
Previous definitions and readings remain append-only. New successor definitions
identify the current predecessor definitions; no observation is inherited by a child.

Only selected current definitions aggregate. Shared records must bind the same
pool, mode and evidence hash, with a combined share no greater than one. Observed
numerators and denominators are already scoped measurements: sum them directly,
never multiply them by shares again. Missing current readings withhold a ratio;
newly merged definitions explicitly remain unmeasured.

## Conserved quantities and deliberate limits

An identity-only transition preserves source records and pool assignments, complete
reference populations, unit economics, dates, cost commitments and selection.
Partition shares move through the declared lineage edges. Fixed cost explanations
follow the same edges and retain the unassigned remainder. Resource budgets,
concurrency and total effort per resource remain unchanged; unrelated tasks cannot
change. The example explicitly distributes task effort and lets the scheduler
determine resulting gates. This is not evidence that actual effort is proportional.

Policy changes and evidence corrections are separate revisions. Merging selected
and deferred predecessors is rejected. Exclusive alternatives support identity
renaming; splitting one exclusive candidate into a simultaneously selected group
requires a future explicit grouped-alternative contract. The application does not
invent separate pools or duplicate source records to bypass these rules.

Monthly monetary allocation retains the existing deterministic cent convention.
Daily cumulative rounding is performed within each member, so an identity split
can change a partial-period amount by a cent even when the complete monthly pool
is conserved. Scheduling can also change recognition dates. Family comparisons
reconcile to the actual saved ledger; they do not promise unchanged daily economics.
This increment does not change the calculator or rewrite historical financials.

## Reviewable demonstration and checks

Run `pvc allocation-demo --include-lineage` with the same four allocation inputs
and a separate output prefix. The [twelve-revision exercise](../portfolio/allocation-lineage-review.html)
retains the six-step allocation decision, registers full-pool readings, changes
scope to a selected 60% partition, splits it into 24% and 36%, withholds an incomplete
ratio, corrects a reading while preserving its old target, and merges the work.
The completed scoped pricing ratio is 17,000 / 500,000 = 3.40%; the subsequent
merged initiative requires a new reading. Source records, frozen accounting and
financial claims remain intact. The [memo](../portfolio/allocation-lineage-memo.html)
reproduces the saved current forecast and maps original sequencing alternatives
through task ancestry. An adverse forecast remains adverse.

Lineage report version 2, realization version 4 and memo version 7 identify the
composition. Tests cover the worked ratio, missing observations, immutable history,
rehashed semantic tampering, signed legacy round trips, in-memory/PostgreSQL
storage, stale writes, audit rollback, tenant boundaries, API serialization and
the restriction on service principals approving human decisions. The extended
allocation consistency checker reproduces all twelve financial snapshots, current
sources, accounting, memo and rendered output. Browser tests exercise three widths.

All observations, allocation decisions and reviews in this exercise are constructed.
There is no sponsor, independent practitioner acceptance, actual intervention,
realized company value or performed pilot. Those remain separate goal criteria.
