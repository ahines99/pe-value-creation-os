# 0026: Explicit initiative and KPI lineage

Status: Implemented; exact-build release acceptance is recorded separately in
[PR #34](https://github.com/ahines99/pe-value-creation-os/pull/34) and its CI checks.

## Problem

An ownership team can split an initiative into cohorts or consolidate work later.
Keeping the old ID would hide a population change; replacing it without a mapping
would break comparisons to the frozen close. Copying a parent result to its children
would also manufacture historical measurements and potentially duplicate benefits.

## Decision

Case payload version 4 composes the existing source-backed or exit-review payload
with cumulative initiative/task lineage and an immutable KPI book. Prior version
1–3 payloads retain their serialized form and content hashes. Storage remains in
the existing signed revision JSON; no database migration is required.

An identity transition binds its exact parent revision, prior and revised inputs,
and authored date. Every retired initiative and work package maps to a complete
successor set. Retired IDs cannot be reused. A many-to-many change requires separate
split and merge revisions. Each predecessor's reference allocation sums to one.
An unchanged task ID retains its initiative ownership; a renamed initiative cannot
silently inherit the old task IDs without an explicit task transition.

Partitioned source books assign each contract, invoice and indivisible service/vendor
month exactly once, using the record hash. Every current driver owns records of its
economic mechanism. An identity transition preserves those records, unit economics,
timing and each cost ID/amount/payment date; evidence or assumption corrections need
separate revisions. Reference populations and spend are explicitly conserved.
Source forecasting runs each record only for its owner and posts costs once.

Family comparisons use all predecessor/successor identities. A cost shared solely
within one family rolls up to that family once; a cross-family cost stays shared.
Monthly, day-100 and year-one family totals reconcile to the full forecast. The raw
ledger retains its owners. Frozen accounting and attribution do not change: the
realization report adds only a frozen-to-current identity map, never child allocations.

Each current initiative has one current KPI definition with its complete, exact
source population, baseline, target and target date. Target revisions preserve
population and baseline; explicitly labeled scope corrections may change them.
All earlier definitions and readings remain immutable. A reading references its
exact definition and hashed constructed evidence. Corrections reference the latest
reading for that same definition and calendar month. New readings require a current
definition; correcting an old reading preserves its old target. Split/merge definitions
name the current predecessor definitions. Missing child readings withhold combined
ratios, which otherwise sum numerators and denominators rather than averaging ratios.

The constructed Progress replay introduces KPI history, splits renewal pricing into
one spring contract and four other contracts, revises a target and corrects a reading,
then merges pricing under a new ID before exit review. Ten signed revisions preserve
seven KPI definitions and fifteen readings. The executive memo maps original sequence
preferences through recorded task ancestry and reproduces the latest financial,
lineage and exit outputs before displaying alternatives.

## Scope and limits

This is an authored, deterministic rehearsal. It establishes no real operating
population, human approval, causal attribution or company result. Baseline accounting
and claims remain on frozen IDs. KPI ratios are not financial attribution. Management
concurrency and resource budgets are not increased in the demonstration; schedule
changes can affect benefits without changing source economics or cost commitments.

Service-month ownership is indivisible; arbitrary queue-level sharing and broader
benefit-pool allocation/exclusivity remain separate work. Current KPI aggregations
require all current populations for a metric in an observed month; they do not infer
temporal applicability or fill missing readings. Broader metric/unit conversions
and an external finance/practitioner review remain open.

## Verification

`test_source_partitions.py` exercises source completeness, wrong mechanism/owner/hash,
conserved forecasts/costs and adverse gate timing. `test_initiative_lineage.py` exercises
economic conservation, forged rehashed transitions, immutable histories, weighted
ratios, missing readings, correction rules, full exit/memo reproduction, in-memory and
PostgreSQL persistence, API round trips, tenant scope, human authority, audit rollback
and deletion. The public bundle checker reproduces the current ten-revision memo and
its rendered lineage exhibit; browser checks cover desktop, tablet and phone widths.
Exact passing-build counts belong in release evidence, not this design decision.
