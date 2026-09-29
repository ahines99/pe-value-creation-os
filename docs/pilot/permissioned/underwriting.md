# Private financial inputs to incremental underwriting

This increment adds private forecast revisions on top of the released
[financial snapshots](financial-snapshots.md). PR #45 passed CI/publication
acceptance as recorded in the [completion checklist](../../portfolio/remaining-work.md).
All test companies, documentary references, grants and reviewers are fictional.
No real company pilot, eligibility review or independent finance validation is
represented.

## From accepted balances to explicit assumptions

A named human operator with processing permission and `pvc.read`/`pvc.write`
submits a 24-month forecast. The request binds the exact financial snapshot ID
and hash, company, case, entity and currency. Its historical source must have
been accepted, remain current and be labeled `baseline_candidate`; an
`observed_actuals` snapshot cannot silently become the forecast's baseline.
The forecast starts after the last historical financial month.

Each assumption in each downside/base/upside scenario has exactly one basis:

| Basis | What the application establishes | What remains a human judgment |
|---|---|---|
| Financial component | Exact amount from a named month and component in the accepted snapshot, using identity or absolute-value mapping; currency units required | Whether that historical amount is a suitable forecast input or eligible economic population |
| Operator judgment | An explicit value, rationale, owner, invalidation condition and documentary references are recorded | Achievable uplift/capture/churn, removable costs, future timing, contract rights and similar operating assumptions |

Every initiative additionally records evidence references, eligibility rationale,
constraints and a falsification test. References retain locators and SHA-256
identities, but the forecast API does not upload or independently authenticate
those documents. They are review inputs, not additional accepted operating-source
records. Accepted aggregate revenue alone cannot prove which contracts permit a
price change. Neither a hash nor a successfully calculated scenario resolves this.

Private evidence never enters the public/constructed underwriting contract. The
public parser and renderers continue to reject this private schema. The two
contracts share structural checks and neutral ledger arithmetic, not source
classification or approvals.

## Economics and boundaries

The model supports disjoint pricing, service-cost and collections pools, explicit
implementation/recurring/capex costs, recognition/payment dates, settlement lags
and initiative selection. Overlapping pools are rejected; the public shared-pool
contract is not automatically applied to private records. That extension needs
its own explicit private source/population contract and review.

Pricing retains churn and variable-cost effects. Service savings are capped by
work removed, the stated cost action and addressable spend; freed hours alone
are not savings. Collection acceleration reverses on its counterfactual date
and creates no earnings. Excluded initiatives retain explicitly committed costs.

Outputs include monthly/day-100/year-one/year-two amounts, incremental EBITDA,
recurring contribution, pre-tax cash proxy, dated funding need/recovery, and
post-horizon cash settlements. Valuation is a sensitivity on year-two incremental
recurring contribution, not total company enterprise value, equity proceeds,
fair value or independently reviewed maintainable earnings. Adverse results
remain negative.

Values support at most 24 significant digits, 24 integer positions and 12 decimal
places. The private evaluator uses a fixed local Decimal precision of 128 for
intermediates and the existing cumulative daily cent-rounding convention. It
does not inherit a caller's low-precision Decimal context.

The fictional pricing test maps January revenue of 980, assumes 10% uplift and
50% capture with zero additional churn, and applies 20% variable costs. Monthly
incremental contribution is 39.20. An initial implementation expense/payment of
50 leaves first-year EBITDA of 420.40. A one-month settlement lag gives first-year
cash of 381.20 and 39.20 of cash after the 24-month horizon. Year-two contribution
of 470.40 at an assumed 8× multiple gives an incremental sensitivity of 3,763.20.
These are hand-checked test amounts, not observed results or a recommendation.

## API, persistence and current authority

All routes start with `/companies/{company_id}/private-underwriting`.

| Method / suffix | Contract |
|---|---|
| `POST /cases/{case_key}` | `UnderwritingRequest`: idempotency key, predecessor hash, typed inputs and rationale; server computes and saves the revision |
| `GET /cases/{case_key}` | Scoped-human historical records, explicitly without a current-use claim |
| `GET /revisions/{revision_id}/usable` | Requires the latest forecast revision and a currently usable exact financial snapshot, then reproduces the forecast |

Writes authenticate before consuming the bounded 1 MiB body, require explicit
bearer credentials, obtain the processing environment from server configuration,
and use generic validation errors. Responses are non-cacheable. There is no MCP
or public-export route. Models and services cannot create these revisions.

The repository holds the company lock across source-authority checks, calculation,
append and audit. Migration `0011` adds forced company row-level security,
financial/parent foreign keys, unique sequence/idempotency constraints and
insert/select-only runtime access. Failed audit rolls back the revision;
populated downgrades are blocked even without a migration-owner company scope.
Whole-company offboarding removes this history with its sources.

Replays return a historical receipt only for an identical request and author.
Conflicting requests or stale heads return 409. Corrections append versions;
scope, currency, entity and fictional/real origin cannot change within the stream.
Superseded source records, finance withdrawal, changed review/grant hashes,
revocation, expiry or a different processing environment prevent current use.
Historical records remain accessible to scoped human readers after revocation;
revocation does not delete derived records or copies.

## Remaining workflow

A successful calculation is neither finance/operating approval nor a frozen
comparison baseline. [Private capacity plans](capacity-plans.md), released in PR #46,
connect resource/dependency proposals to financial timing. The next
[reviewed-baseline increment](reviewed-baselines.md) adds exact-version decisions
and comparison designations, with a separate release gate. Private observations/
counterfactuals, attribution, intervention/delivery evidence and memo/review UX
remain subsequent integration work. The public constructed
versions of these capabilities already exist and are not reused by relabeling
private inputs. Source-retention operations and the actual
[pilot entry gates](../pilot-plan.md) also remain outstanding.
