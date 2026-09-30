# Private actuals and reviewed counterfactuals

This increment compares accepted private monthly financials with an explicitly
authored estimate of results without intervention and the frozen plan. Its
release gate is separate from implementation; see the
[completion checklist](../../portfolio/remaining-work.md). Tests use fictional
records and people. They do not represent company permission, independent
finance review, a performed pilot or realized value creation.

## What the comparison means

The workflow retains three different quantities:

1. **Actual financial results:** accepted ledger-backed monthly financial snapshots
   with the purpose `observed_actuals`.
2. **Counterfactual:** a reviewed estimate of the same entity's financial results
   without the intervention, using historical monthly financial components plus
   explicit signed adjustments. Each adjustment needs a rationale and evidence
   reference/hash. Documentary assertions still require human scrutiny.
3. **Frozen forecast:** the incremental financial effects saved in the exact
   [reviewed baseline](reviewed-baselines.md). Later forecasts never move it implicitly.

For each financial component, `difference = actual - counterfactual`, and
`variance = difference - frozen incremental forecast`. The result reconciles
EBITDA, recurring operating contribution, operating accrual-to-cash differences
and the pre-tax cash proxy. Operating cash excludes the separately mapped
working-capital and capex flows; implementation expense is separate from
recurring operating expenses. It is not a normalized-earnings or free-cash-flow claim.

**All differences remain unattributed.** Entity-level changes do not prove that
the intervention caused them. Initiative-level operating evidence, alternative
explanations and attribution decisions remain separate unfinished work.

## Author, review, then observe

A scoped human operator with write permission creates a versioned counterfactual
stream bound to the exact currently supported baseline. Every requested month
needs all six components, including explicit known zeros. Each component names
a historical anchor month in the baseline's exact accepted financial snapshot.
No missing month or component is silently treated as zero. The measurement
window must fall within the frozen forecast.

The proposal records whether it is prospective or retrospective. A prospective
proposal must be authored **and accepted before its first measurement month**.
An estimate or reacceptance after that point requires an explicitly retrospective
version. The original prospective receipt remains unchanged. The application
checks recorded timing; it does not establish the analyst's actual independence
from information outside the system.

A company-scoped human finance reviewer records an exact-version accept, reject,
request-changes or withdrawal decision. Acceptance requires assessments of
perimeter/definitions, anchors/adjustments, alternative explanations and timing/
comparison limits. Named processing permission, approval scope and the configured
approval client are required. Withdrawal can remove support after processing
revocation without reopening source bytes or recalculating the comparison.

A human finance reviewer with write permission then records an observation against
the current accepted counterfactual and an accepted actuals snapshot. The original
baseline source and actuals source both require current processing permission.
Separate grants can cover their distinct periods without replacing the original
baseline's policy. Entity, case, currency, data origin and accounting/cash
definitions must agree. Only completed calendar months are compared; a closed
subset of a longer counterfactual is permitted when all sources cover that subset.
No partial-month day-100 actual or annualized realized result is inferred.

## Hand-worked fictional example

The test begins with January historical components and authors an October
counterfactual: revenue 1,000; operating expense -300; implementation expense 0;
operating cash 650; working-capital cash 40; capex cash -100. The adjustments
represent assumed organic growth and removal of a historical one-off expense
and its settlement. They are authored test assumptions, not discovered company facts.

| October measure, USD native units | Actual | Without intervention | Difference, all unattributed | Frozen incremental forecast | Variance |
|---|---:|---:|---:|---:|---:|
| Mapped EBITDA | 730.00 | 700.00 | 30.00 | -28.50 | 58.50 |
| Pre-tax cash proxy | 610.00 | 590.00 | 20.00 | -50.00 | 70.00 |

The frozen forecast retains the original capacity gate, implementation cost and
cash timing. A positive difference in this example does not authorize an
intervention or establish a causal value claim.

## Corrections and current support

Corrections append versions with exact predecessor hashes. Counterfactual
corrections retain their baseline and period window; observation corrections
retain their baseline, counterfactual stream and comparison window. A replacement
baseline needs a new stream. Stale heads and conflicting idempotent requests fail.

Current-use operations reproduce calculations and recheck both processing scopes,
baseline support, counterfactual head/review and actual source acceptance.
Withdrawal, supersession, changed exact review bindings or revoked processing
prevents current use. Reacceptance never silently reactivates an observation
bound to an older review. Historical records remain available to scoped human
readers, including saved private amounts, and same-author exact idempotent replay
returns only the original receipt. Neither operation implies current permission.

## API and storage

All routes have the prefix `/companies/{company_id}`.

| Method / suffix | Purpose |
|---|---|
| `POST /private-counterfactuals/cases/{case_key}/streams/{key}` | Append a `CounterfactualRequest` |
| `GET /private-counterfactuals/cases/{case_key}/streams/{key}` | Historical proposal versions |
| `POST /private-counterfactuals/revisions/{revision_id}/reviews` | Append a `CounterfactualReviewRequest` |
| `GET /private-counterfactuals/revisions/{revision_id}/reviews` | Historical finance decisions |
| `GET /private-counterfactuals/revisions/{revision_id}/usable` | Reproduce and return a currently supported accepted version |
| `POST /private-observations/cases/{case_key}/streams/{key}` | Append a `PrivateObservationRequest` |
| `GET /private-observations/cases/{case_key}/streams/{key}` | Historical observation versions |
| `GET /private-observations/observations/{observation_id}/usable` | Reproduce and check current comparison support |

Writes require explicit bearer authentication before a bounded 1 MiB body is
parsed. Invalid private bodies return generic errors; responses are non-cacheable.
Models and services cannot use these private human workflows. There are no MCP
or public-export routes. The server supplies the processing environment; a
withdrawal does not need it because withdrawal cannot grant processing or support.

Migration `0014` adds three append-only tables with forced company row-level
security, exact source/review/baseline foreign keys and unique version chains.
Company locks serialize writes with revocation and review changes. Receipts and
minimal audit references commit atomically. Populated downgrades are blocked even
for a migration owner without company scope. Whole-company offboarding removes
the new records along with their source chain.

## Remaining pilot work

The subsequent [private execution increment](execution.md) adds bounded human
authorization, delivery segments and task acceptance, released in PR #49. The next
[private attribution increment](attribution.md) adds signed allocations, delivery-to-claim
checks, residuals and separate finance review, with a separate release gate.
Operating-source and delivery-cost reconciliation, private executive memo
composition and a usable pilot review interface remain open, as do per-source
retention expiry, legal holds and backup/copy disposal. The
[pilot entry gates](../pilot-plan.md), sponsor, real authorized records, reviewer
participation and actual execution/measurement are still required. Software
validation does not close those requirements.
