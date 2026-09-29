# Accepted private ledgers as financial inputs

This increment calculates and stores versioned monthly financial inputs from the
[private source-custody workflow](intake-records.md). Each snapshot binds an exact
intake, finance acceptance, processing grant, accounting-definition attestation
and source hash. PR #44 passed CI/publication acceptance as recorded in the
[completion checklist](../../portfolio/remaining-work.md).

Testing uses fictional records and identities. No company financial statements,
independent finance review, operational pilot or realized savings are represented.

## Sequence and authority

1. Complete the processing grant, source intake and finance acceptance. The source
   must be the latest version of its dataset, match its independent controls and
   remain within its processing permission.
2. A named processing subject with `operator` and `finance_reviewer` roles submits
   a financial snapshot request. Token-based requests need `pvc.read`, `pvc.write`
   and `pvc.approve`, and must use the configured approval client. Ordinary
   operators, data owners without finance rights, models and services cannot sign
   an accounting definition through this operation.
3. The reviewer records the accounting basis and evidence reference/hash, and
   attests to the earnings/cash component definitions and use within the granted
   purpose. This is an explicit human assertion, not independent legal or
   accounting verification by software. If the intended use exceeds the policy,
   obtain a revised data-owner grant and corresponding source/review versions.
4. The repository locks the company and reloads the source, current grant and
   current finance decision. It requires the three exact hashes in the request,
   reproduces preflight from stored bytes, calculates financial amounts and stores
   the snapshot with its audit event in one transaction.
5. Later private analysis must call the current-usability operation while holding
   the same transaction as its own write. A historical snapshot or a previously
   successful HTTP response alone cannot establish continuing authority.

Requests label the input `baseline_candidate` or `observed_actuals`. These labels
describe intended use, not a frozen comparison basis or causal result. Case keys
identify private financial history streams; they are separate from the existing
constructed investment-case store. Revisions retain company, case key, entity,
currency and data origin. A fictional stream cannot silently become a real-company
stream. Different reporting periods can coexist as separately identified snapshots.

## Financial identities

Account codes, explicit signs and native-currency amounts come from the accepted
source policy. No values are taken from caller-supplied forecast totals.

| Output | Calculation and boundary |
|---|---|
| Mapped EBITDA | Revenue + signed operating expense + signed implementation expense; reviewed operating components must exclude interest, tax and depreciation/amortization |
| Recurring operating contribution | Mapped EBITDA less signed implementation expense; does not establish maintainable earnings |
| Operating accrual-to-cash difference | Operating cash component less mapped EBITDA; separate from working-capital and capex components |
| Pre-tax cash proxy | Operating cash + working-capital cash + capex cash; these must be disjoint populations |

The finance reviewer must establish that implementation cash settlements are
included in the operating cash component on their actual payment dates and that
working-capital flows are not already included in that component. A statutory
CFO figure that already includes working capital cannot be reused alongside an
additional working-capital component. Arithmetic reconciliation alone does not
prove this classification; the review evidence must support it.

The calculator reuses neutral Decimal earnings/cash identities, without creating
a constructed `SourceBook` or routing private data through the public underwriting
evaluator. It preserves complete monthly periods and returns separate period
totals. Credits, losses and cash outflows remain signed. Fixed local precision
prevents a caller's Decimal context from changing the result. These balances are
not incremental benefits: no counterfactual, initiative attribution, debt/cash
transaction bridge, market multiple or investment return is inferred.

The fictional one-month test contains revenue 980, operating expense −300 and
implementation expense −50, producing mapped EBITDA 630. Operating cash 600,
working-capital cash 40 and capex cash −100 produce the separate cash proxy 540.
This worked example is a software fixture, not a company result.

## API and version history

All routes start with `/companies/{company_id}/private-financials`.

| Method / suffix | Behavior |
|---|---|
| `POST /cases/{case_key}` | `FinancialSnapshotRequest`; creates an immutable private snapshot |
| `GET /cases/{case_key}` | Scoped-human historical records; explicitly does not assert current usability |
| `GET /snapshots/{snapshot_id}/usable` | Rechecks live authority, current source/finance/grant bindings and numerical reproduction before returning the snapshot |

The write request includes a unique `idempotency_key`, the current financial
stream predecessor hash (null initially), intake ID/hash, finance-review hash,
grant hash, purpose, reviewed definition and rationale. The server supplies the
author, timestamp, calculated results and environment from
`PVC_PROCESSING_ENVIRONMENT_ID`. Writes require explicit bearer credentials,
authenticate before reading the bounded 1 MiB body, and return generic validation
errors. Responses are private and non-cacheable.

A correction appends a version; it does not overwrite or sum prior snapshots.
Retries return the original historical receipt only for the same request and
author. Conflicting retries or stale financial heads fail with HTTP 409.
Superseded intake, withdrawn finance acceptance, changed review/grant heads,
expired or revoked processing permission, and wrong processing environments
prevent current use. Reacceptance or reauthorization requires a new snapshot
binding the new decision hashes. Historical records remain available to scoped
human readers; revocation is not retroactive deletion of derived data or copies.

## Storage and remaining integration

Migration `0010` adds an append-only table with company/grant/intake/finance/parent
bindings, forced row-level security and insert/select-only runtime permissions.
Audit failure rolls back the snapshot. A populated downgrade is blocked, even
when the migration owner has no active company scope. Whole-company offboarding
removes snapshots with their sources while retaining minimal audit events.

The snapshot is a reusable financial input. The next [private underwriting
increment](underwriting.md) adds explicit scenarios and source-bound forecast
revisions, with its own release gate. Capacity-plan association, explicitly
reviewed frozen baseline designation,
same-scope counterfactual observations, attribution and executive memo composition
still need integration. Merely subtracting two snapshot balances is not evidence
of intervention impact. Source retention operations, actual company approvals,
staging acceptance and the [pilot entry gates](../pilot-plan.md) remain open.

There is no public export or MCP route for this private contract. The existing
public Progress facts and constructed lifecycle remain separate and unchanged.
