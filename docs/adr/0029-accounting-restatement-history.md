# ADR 0029: Accounting restatement and intervening non-reliance

Status: released in PR #37 after all ten CI jobs passed. September 29, 2026.
Exact public-availability timing remains unverified; OP-16 remains open.

## Decision

Add a separate `public_accounting_restatement` contract and
`pvc restatement-history` command. Preserve the existing acquisition-allocation
history and its measurement-period classification unchanged. A real historical
accounting correction does not become a current Progress operating thesis.

The example compares the independently retrieved FY2005 10-K and its 10-K/A.
Each contains 17 mapped annual/closing-balance financial rows. The amendment's
reported/adjustment/restated columns must tie to both independent snapshots, and
the net-income correction components must reconcile. Each snapshot separately
checks operating income, pretax and net income, combined cash/investments,
cash-flow subtotals and opening-to-closing cash.

Public references, accessions, PDF hashes, retrieval times, source pages, column
labels, periods, units and source classifications are retained. Private sources,
duplicate metrics, inconsistent periods/entities, reused source identity and
unreconciled corrections are rejected. The original is not populated from the
amendment's retrospective 'as reported' column.

## Chronology and authority

Four ordered events remain distinct: original filing, issuer non-reliance release,
restatement announcement and independently mapped amended filing. Date-only
selection returns the original before the notice, no numeric snapshot during
non-reliance or on the announcement alone, and the amended snapshot at its
registered filing date. This is retrospective calendar reconstruction, not proof
of historical availability or an assurance that earlier numbers were reliable.

The August 29 release date is not replaced with its accompanying 8-K's August 30
signature date. The December 18 announcement says filings occurred after close;
the issuer filing index labels the amendment December 19. Both source roles and
dates are preserved. No arbitrary midnight, one-day lag or SEC acceptance time
is substituted for public availability.

Exact-publication selection requires timezone-aware, sourced availability times
for all four events. Missing notice timing also blocks it: knowing when two
statements appeared is insufficient if reliance may have been withdrawn between
them. Today's retrieval and SEC acceptance remain separate evidence. The real
example has no verified exact availability times, so OP-16's timing requirement
remains open. Synthetic times exercise selector behavior only in tests.

## Scope and financial interpretation

The demonstration includes the FY2005 net-income correction and a separate
auction-rate-security reclassification between cash equivalents and short-term
investments. It neither creates operating value nor changes the modern baseline,
constructed underwriting, frozen close, accounting claims or valuation models.
It does not reconstruct every contemporaneous release or all corrected years.

## Verification

`test_accounting_restatement.py` covers hand-worked changes, source preservation,
the non-reliance interval, no later-number leakage, missing publication evidence,
invalid source/period/classification/correction inputs, HTML escaping and exact
CLI/artifact reproduction. The browser suite adds the exhibit at three widths,
keyboard/disclosure behavior and matching downloaded states.

The source-review record is [the FY2005 research note](../research/operating-partner/06-accounting-restatement.md).
Tests and source inspection are internal engineering/research checks; neither
constitutes independent finance approval, issuer endorsement or a performed pilot.
