# ADR 0027: Explicit benefit-pool allocation and mutually exclusive choices

Status: implemented; release checks accompany the pull request. September 28, 2026.

## Decision and scope

Underwriting schema 2 requires an authored interaction policy. Distinct initiatives
may reference the same economic pool. A partition assigns each member a fixed
population share, with a total no greater than one. An exclusive rule allows at
most one selected member to use the full pool. The policy records its rationale,
owner, invalidating evidence and constructed evidence references. It is a research
assumption, not a probability, observed segmentation or operating authorization.

Legacy schema 1 still rejects overlapping pools and retains its serialized defaults,
calculation versions and hashes. Existing signed source, exit and lineage revisions
remain readable without rewriting them. No database migration is required.

## Economic and operating behavior

Population shares apply before pricing rates, churn, variable expense, service
hours, spend actions and vendor caps. Excluded, unassigned and blocked shares
are not redistributed. Service partitions must use the same complete reference
population and spend envelope. Monetary components round once per pool/month
(and source record in the source adapter), then preserve cents across members,
daily accruals and dated settlement. Invoice acceleration retains an equal dated
reversal and creates no EBITDA.

Costs use the existing dated ledger once. Exclusion removes only explicitly
avoidable costs; retained commitments remain. An optional cost-ownership explanation
reconciles to every original posting, including any shared remainder and excluded
owners. It does not change case totals or allocate historical financial claims.

Only selected tasks and required enablers consume capacity. A prerequisite owned
by an excluded initiative requires an explicit resolution. Excluded tasks remain
visible. A selected but blocked initiative retains its costs. A hypothetical
selection override is labeled separately from the unchanged recorded policy.

## Source records and lifecycle

Source-book schema 3 assigns every exact complete record to one declared economic
pool. A pool manifest distinguishes absent records from unknown pools. The
adapter then applies the recorded within-pool shares. QA effort, vendor spend and
minimum commitments share the same budget; they cannot be copied in full to each
member. Missing months, unsupported rights/releases and missed notice or collection
windows still block credit. Records replace reference exposure rather than adding
a second forecast to it.

The source-backed case payload accepts the typed allocation case. Immutable
snapshots preserve selection, rules, financials, excluded work and source decisions.
Subsequent decisions cannot discard the policy or source basis. Frozen accounting,
claims, evidence and earlier review receipts retain their original identities.
The realization view discloses the changed forecast scope and withholds inferred
attribution. Source-bounded benefits remain excluded from unreviewed maintainable
exit earnings.

Physical initiative splits/merges remain a distinct contract with disjoint source
ownership and KPI populations. The application rejects automatic conversion from
alternative pool shares to physical split/merge ancestry. Composing overlapping
allocation policies with historical KPI lineage requires an additional explicit
mapping design; this increment does not infer one.

Subsequent implementation: [ADR 0028](0028-allocated-kpi-lineage.md) adds an explicit
allocated-population lineage contract without converting the physical schema 4
history or changing this six-revision example.

## Reviewable example

The separate [six-revision allocation review](../portfolio/allocation-review.html)
uses the existing constructed reference populations and unchanged resource budgets.
Both pricing work packages cannot fit: the original modeled close selects the 60%
share and defers the 40% alternative. A later saved revision explicitly chooses one
competing pricing policy across the full eligible cohort. A source correction
removes unsupported vendor savings. Final base year-one EBITDA is **-163,165** and
cash is **-181,890**; no favorable outcome is manufactured.

The [allocation memo](../portfolio/allocation-memo.html) recomputes sequence choices
against that exact saved history. The existing ten-revision disjoint-lineage case
is preserved as a separate example. Neither exercise is a Progress engagement.

## Verification and remaining work

Worked/adversarial suites cover population budgets, cent conservation, shared costs,
cash reversals, blocked gates, source assignment, unchanged accounting, saved
revisions in memory/PostgreSQL, tenant boundaries and human approval restrictions.
The installed CLI regenerates the exhibits. The allocation consistency checker
reproduces all six financial snapshots, source decisions, accounting, memo and five
rendered pages. Browser checks cover desktop, tablet and phone widths, keyboard
navigation and disclosures. CI logs identify the exact tested commit and counts.

Independent financial/commercial challenge, actual company population definitions,
operator capacity, sponsor authorization and a performed pilot remain outstanding.
Passing software checks does not establish any of those outcomes.
