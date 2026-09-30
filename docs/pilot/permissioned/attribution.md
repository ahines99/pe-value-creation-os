# Private financial attribution and finance review

The calculation and review contracts now connect signed proposed allocations to
an exact private observation, frozen baseline and execution history. Both repositories
and bounded human API routes persist proposals and separate finance decisions,
with transactional window reservations. PR #50 passed all ten CI jobs and its
seven changed published files matched the merge. This does not establish pilot readiness.
No actual company records, finance decisions or intervention outcomes are represented.

Validation covers calculation contracts, memory/PostgreSQL persistence, finance
review, concurrency, rollback, scoped access, migration and API behavior. Exact
release-specific results belong in the [acceptance map](../../portfolio/progress-acceptance.md).

## What a proposal means

An [observation](observations.md) retains the original actual-minus-counterfactual
difference and frozen-plan variance. An attribution proposal separately assigns
part of that difference to registered initiatives, with mechanism, alternative
explanations and an evidence reference/hash/attestation for each assignment.
The proposal does not edit the observation or turn the authored counterfactual
into an independently established causal estimate.

Each allocation has one initiative, complete calendar month and accounting
component. It must be nonzero, retain the component difference's sign and remain
within that difference together with the other allocations. Opposing allocations
cannot net against one another to hide overclaims. Empty proposals are valid:
the entire difference then remains residual. Signed losses and costs can be
allocated before benefit delivery, with their accounting evidence and limits.

The result keeps earnings and cash separate and reports the difference, proposed
attribution and residual at component, monthly and period-total levels. Proposed
attribution plus residual must equal the accounting difference. Reported delivery
costs remain a distinct operating assertion; this calculation does not authenticate
supporting documents or reconcile individual delivery-cost reports to invoices.
Company-specific operating-source mapping and cost reconciliation remain necessary.

For example, fictional accounting differences of 30 EBITDA and 20 cash can support
a proposal allocating 60 revenue, minus 50 implementation expense, and 30 operating
cash. Proposed EBITDA is 10 and proposed cash is 30; residual EBITDA is 20 and
residual cash is minus 10. The negative cash residual stays visible.

## Positive claims require operating support

A positive allocation must identify the exact accepted benefit-gate task for its
selected initiative. The [execution history](execution.md) must still support
every current delivery segment and prerequisite acceptance. Gate acceptance must
precede the first day of the measurement month; acceptance partway through a
month does not support a full-month claim or an inferred day-100 result.

A recorded human authorization must cover that gate and the entire measurement
month. A hold, stop, withdrawal or replacement before the month ends removes
support from the former authorization. A later stop, after the measured month,
does not erase valid historical work. Correcting or withdrawing the supporting
gate acceptance does remove current support, while preserving the original
proposal and its evidence for historical reproduction.

## Review and correction contracts

The proposal records an execution head and reproduces from that original history
prefix. Current-use checking separately evaluates later history, so an unrelated
later event need not invalidate an otherwise supported historical measurement.
Both repositories also recheck current observation, source, processing,
counterfactual and baseline support under the company lock.

Finance review is a separate append-only sequence by a human other than the
proposal author. Acceptance requires accounting reconciliation, mechanism and
delivery assessment, alternative explanations, double-counting/residual assessment
and attribution limits. Withdrawal requires a preceding acceptance. Reacceptance
is a new decision, not a rewrite of the old receipt. Neither proposal nor review
asserts that causal impact has been proven.

Proposal corrections must retain company, case, baseline, measurement stream and
period window. They can bind a corrected observation and preserve the original
proposal. Every request identifies the expected preceding version. Stored review
decisions also identify the execution head reviewed.

## Persistence and authorization

Migration `0016` adds proposal and review sequences with exact observation,
baseline, execution-head and predecessor foreign keys. Both tables have forced
company row-level security and insert/select-only runtime permissions. Populated
downgrades are blocked, including for a migration owner without company scope.
Whole-company offboarding removes the records with their underlying source chain.

Company locks serialize new writes, source/authority changes and review decisions.
Receipts and minimal audit references commit atomically. Substantive work requires
current processing permission. A finance reviewer can withdraw support after
revocation without reopening source records. Same-author exact retries return
their historical receipts without restoring any permission or current support.

Acceptance reserves the measurement window against other accepted latest proposal
streams in the same case/baseline. Overlapping alternatives may exist as proposals,
but cannot both become current claim ledgers. A stale-source accepted ledger keeps
its reservation until withdrawal or supersession. Empty, residual-only proposals
do not reserve a window. This does not establish portfolio-level ownership across
separate cases or baselines.

## Human API

All routes have prefix `/companies/{company_id}/private-attributions`.

| Method and suffix | Purpose |
|---|---|
| `POST /cases/{case_key}/streams/{key}` | Append an operator-authored `AttributionRequest` |
| `GET /cases/{case_key}/streams/{key}` | Historical proposal versions |
| `POST /revisions/{revision_id}/reviews` | Append an `AttributionReviewRequest` by an authorized finance reviewer |
| `GET /revisions/{revision_id}/reviews` | Historical finance decisions |
| `GET /revisions/{revision_id}/usable` | Reproduce the original proposal and review evidence, then check current source, delivery and finance support |

Writes require explicit bearer authentication and role checks before parsing a
bounded 1 MiB body. Responses are non-cacheable; validation errors omit private
input details. Model and service identities cannot use these human workflows.
The server supplies the processing environment; withdrawal does not require it.
There is no private MCP, public-export or source-system writeback route.

The immutable proposal continues to say `finance_reviewed: false`; the separate
review and current-use response identify whether that exact proposal has current
support. Historical retrieval alone does not establish acceptance or permission.

## Remaining pilot work

The [private finance review workspace](review-workspace.md) now has an implemented
executive page and exact-version decision form, released and verified in PR #51.
An integrated private executive memo, remaining pilot screens, operating-source
and delivery-cost reconciliation remain unfinished. So do per-source expiry,
legal holds and backup/copy disposal.

The independent pilot entry gates, sponsor, authorized company data, actual
review participation and elapsed operating measurements remain outstanding.
