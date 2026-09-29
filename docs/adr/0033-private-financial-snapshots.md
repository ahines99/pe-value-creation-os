# ADR 0033: Private financial inputs from accepted ledger versions

Status: Accepted for implementation; release and pilot acceptance are separate.

## Context

Accepted private sources must support financial analysis without being mislabeled
as constructed records. Source acceptance alone also does not review a newly
introduced earnings/cash definition or preserve a source's continuing usability.

## Decision

Add an independent private financial-snapshot contract and repository/API stream.
Require a named human finance reviewer with processing and write scopes to sign
an explicit accounting-definition/evidence attestation. Under the company lock,
require exact current source, finance-review and grant hashes, reproduce source
preflight, and calculate monthly and total earnings/cash components from original
bytes. Reuse only the neutral Decimal identities of the existing calculator.

Preserve immutable snapshots, predecessor hashes, purpose, accounting basis and
origin. Do not silently move between company/entity/currency or fictional and real
origins. Keep historical retrieval separate from current-usability checks. Source
correction, authority withdrawal or changed review/grant heads requires a new
snapshot for current use, while original figures and audit events remain intact.

Store snapshots atomically with audit records using forced company row-level
security, source/review/grant foreign keys and insert/select-only runtime access.
Block populated downgrades and include snapshots in company offboarding.

## Consequences

Private input calculation is now independent of public/constructed schema labels.
The attestation records a human judgment; the application cannot independently
establish correct GL scope, legal processing rights or maintainable earnings.
The explicit six-component cash convention requires disjoint operating,
working-capital and capex populations to avoid double counting.

A baseline candidate is not a frozen intervention baseline. Private scenarios,
capacity planning, frozen baseline review, counterfactuals, attribution and memo
composition remain subsequent integration work. See the
[financial snapshot guide](../pilot/permissioned/financial-snapshots.md).
