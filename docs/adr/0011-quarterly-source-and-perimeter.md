# ADR 0011: quarterly derivation and business-perimeter context

Status: accepted. Extends ADR 0009; does not complete peer/thesis research,
historical point-in-time replay or the executive decision memo.

## Source identity and period basis

The FY2026 Q2 income statement repeats May 31 dates under distinct three-month
and six-month headings. Extraction v2 requires reviewed header occurrences and
period-group text, searches headers rather than footnotes, and uses start/end/basis
in fact IDs. Source-document hashes still guard exact bytes. Issuer identity is
checked on an explicit cover page; each financial table retains its own reviewed
heading, unit, printed page, row and column checks. Quarter pages need not repeat
the issuer name in their table heading.

Existing annual v1 records and IDs remain unchanged. New quarterly bundles retain
their own source/mapping hashes and extraction version. The combined public input
is assembled from these reviewed bundles and rejects duplicate facts, mixed
entities/cutoffs and private source classes. A new source revision requires an
explicit selection; it cannot silently overwrite an existing fact.

## Reported facts versus calculated quarters

Cash-flow statements report three months in Q1 and six months in Q2. Q2 cash and
D&A are therefore separate derived components, never new `FinancialFact` records.
The algorithm requires exactly one matching cumulative period and one contiguous
prior period. It rejects mixed currencies/bases and preserves both source fact IDs.

Twelve income-statement comparisons must reproduce the independently reported
quarter. Relevant source-period reconciliations must also agree; a wrong cash-flow
net-income input cannot disappear merely because subtraction cancels its error.
Missing or inconsistent inputs block the calculation. A positive derived PP&E
purchase outflow or negative derived D&A requires review rather than silent use.

This provides cross-filing arithmetic checks, not an independent assurance that
accounting policies/perimeter never changed. It does not annualize interim results,
construct a trailing-year figure, infer unreported transactions or replace source
review. Comparative periods remain the vintages presented in the selected filings.

## Dependency-aware financial reconciliation

Analysis v2 withholds measures affected by a failed reconciliation. An intangible
amortization definition difference blocks EBITDA and operating income plus D&A;
it does not block CFO less reported PP&E purchases when that independent cash
calculation is supported. This replaces v1's unnecessarily broad period-wide gate.
The 2023/24 annual and 2025 comparative interim differences remain visible.

The same explicit definitions govern annual, reported Q1 and calculated Q2
earnings/cash. Debt amortization already included in interest is not added again.
No measure is labeled issuer-adjusted EBITDA or independently reviewed savings.

## Dated business-perimeter events

Add typed source-linked context events, with reported statements separate from
analytical implications. The source must be registered, public, same-entity and
filed by the case cutoff; an occurred event cannot postdate its filing. Event IDs
are unique. HTML escapes both fields and source locators.

The [September 22, 2026 8-K](https://investors.progress.com/node/28981/html), Item
2.01, is a material acquisition event after the selected financial periods. The
report flags this perimeter change prominently. Its consideration is not a synergy
estimate, and the event does not manufacture post-acquisition financial statements.
The source HTML remains local with a retrieval manifest; only reviewed factual
context, source identity and hashes enter the public repository.

## Verification

Tests exercise repeated headers in a real synthetic two-page PDF, cover identity,
full-period IDs, preservation of original annual records, reviewed mapping hashes,
worked quarter bridges, missing/revised inputs, sign/currency mismatches, source
statement inconsistencies, event cutoff/referral validation and report rendering.
Browser checks cover the expanded quarterly tables and source disclosures.
