# Private financial attribution — implementation in progress

The calculation and review contracts now connect signed proposed allocations to
an exact private observation, frozen baseline and execution history. Repository
persistence, API routes, transactional window reservations and their integration
tests are still required. This is not a released or usable private pilot workflow.
No actual company records, finance decisions or intervention outcomes are represented.

Local validation passed 25 new calculation/review-contract checks. The related
observation, execution and attribution suite passed 170 tests with PostgreSQL
enabled. The attribution tests currently exercise domain contracts using fictional
in-memory source histories; they do not establish attribution persistence or API
acceptance. Ruff, mypy and skill-contract lint also passed. Full CI and release
acceptance remain separate gates after integration.

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
Repository integration must also recheck current observation, source, processing,
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

## Remaining integration and acceptance

1. Persist proposal and review sequences in both repositories, with exact source
   foreign keys, forced company row-level security and insert/select-only runtime
   permissions. Add populated-downgrade protection and whole-company offboarding.
2. Serialize new writes, source/authority changes and review decisions. Require
   current processing for substantive work; permit an authorized human to withdraw
   support without reopening source records. Preserve same-author historical retries.
3. On acceptance, reserve the measurement window against other accepted latest
   proposal streams in the same case/baseline. Overlapping alternatives may exist
   as proposals, but cannot both become current claim ledgers. A stale-source
   accepted ledger retains its reservation until withdrawal or supersession.
   This does not establish portfolio-level ownership across separate cases.
4. Expose bounded, authenticated human API routes for history, proposal, review
   and current-use checks. Do not add a private MCP or public-export route.
5. Test source and review revocation, corrections, concurrent reservations,
   idempotency, transaction rollback, row-level security, migration and API error
   boundaries. Run the related observation/execution regression suites.
6. Connect accepted claims and residuals to the private executive memo/review UX,
   including explicit operating-source/cost-reconciliation exceptions. Release
   only after exact-build CI and publication acceptance.

The independent pilot entry gates, sponsor, authorized company data, actual
review participation and elapsed operating measurements remain outstanding.
