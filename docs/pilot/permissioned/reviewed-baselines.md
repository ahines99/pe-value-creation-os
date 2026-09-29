# Human-reviewed private comparison baselines

This increment adds exact-version finance and operating reviews to
[private capacity plans](capacity-plans.md), followed by an immutable comparison
baseline. Its CI/publication gate is recorded separately in the
[completion checklist](../../portfolio/remaining-work.md). All validation uses
fictional identities and records; no actual company review, independent finance
endorsement, operating intervention or performed pilot is represented.

## Review the exact proposal

Review decisions bind a saved capacity revision ID and content hash. That plan
already binds its underwriting revision, financial snapshot, accepted source and
processing permission. A reviewer cannot approve a moving case identifier or
silently accept a different source or forecast version.

Finance and operating reviews have separate append-only histories. Every decision
records its role, authenticated human actor, server timestamp, rationale, evidence
reference/hash and predecessor hash. The available decisions are `accept`,
`reject`, `request_changes` and `withdraw`.

| Review | Required role, in addition to `operator` | Acceptance assessment |
|---|---|---|
| Finance | `finance_reviewer` | Accounting/controls, assumptions/eligibility, cash/cost timing and valuation limitations |
| Operating | `operating_reviewer` | Owners/capacity, dependencies/constraints, measurement/stop conditions and an explicit planning-capacity confirmation |

Reviewers need company scope, `pvc.read`, `pvc.approve` and the configured approval
client. New acceptance, rejection or change requests also require current named
processing permission and the current usable plan/source. Models and services
cannot make these decisions. Assessments and documentary references remain human
assertions; the application does not independently authenticate their commercial
or accounting content.

An operating acceptance cannot pass with blocked selected work. A finance reviewer
may accept the accuracy of an adverse or infeasible forecast, or request changes;
that decision does not establish operating feasibility. Accepted reviews do not
rewrite the original proposal's unreviewed/uncommitted flags. The review receipts
are separate evidence of the later decisions.

## Withdraw support without reopening private processing

A matching company-scoped human reviewer can withdraw a currently accepted
decision even after its plan is superseded or processing permission is revoked.
Withdrawal appends a decision to that role's exact review history and does not
read private source bytes or recalculate forecasts. It therefore does not require
an active processing grant or configured processing environment. It still requires
human reviewer authority, approval scope/client, exact hashes and bearer-based
write authentication. This exception only removes support; it cannot accept or
reactivate a plan.

Reacceptance requires current source/plan authority and a new review. It never
reactivates a baseline bound to an older review. A subsequent explicit baseline
designation is needed. Concurrent withdrawal and freezing are serialized by the
same company lock: withdrawal first prevents freezing; freezing first preserves
the designation but the subsequent withdrawal makes its support invalid.

## Freeze a comparison baseline

A named human processing operator with the `approver` role, approval scope and
configured client selects a downside, base or upside scenario from a current,
capacity-tested plan. Freezing requires:

1. The exact current plan and its currently usable accepted source chain.
2. The current accepted finance and operating reviews for that exact plan.
3. Two distinct reviewer identities. A person holding both roles cannot satisfy
   the two-reviewer requirement alone; this does not by itself prove institutional
   independence or expertise.
4. No blocked selected work and an exact previous baseline hash, if replacing a
   designation.

The baseline saves the scheduled scenario with entity, currency, native unit
scale, underwriting/financial identifiers, review identities/hashes, provenance,
author and timestamp. It is labeled `comparison_only`. Negative economics are
preserved. Neither a review nor baseline designation grants authority to change
pricing, staffing, contracts or any other operating activity.

Later forecasts and plans do not automatically move this baseline. The original
forecast remains intact when a reviewer withdraws support, a source is corrected
or an explicit replacement is designated. The original public constructed
baseline contract remains separate and unchanged.

## Inspect current support separately from history

Historical records remain accessible to scoped human readers without claiming
current processing permission. The baseline status operation additionally checks
fresh processing permission, reproduces the original stored financial/underwriting/
capacity chain, and compares the frozen numbers with that exact saved plan.

| Situation | Status behavior |
|---|---|
| New forecast or plan; original source and reviews still supported | Original current baseline remains the comparison anchor |
| Plan review withdrawn or replaced | Frozen numbers remain; review support and comparison usability become false |
| Source superseded, source finance acceptance withdrawn, or its exact finance/grant binding changed | Frozen numbers remain; source support and comparison usability become false when processing is still permitted |
| Processing revoked, expired, wrong environment or caller no longer permitted | Status/reproduction is denied; historical metadata retrieval is a distinct operation |
| New baseline explicitly designated | Earlier designation remains historical; only the new designation is current |
| Frozen amount, currency or source binding tampered with, even if rehashed | Reproduction fails rather than publishing a support status |

Historical retrieval includes saved private amounts. Revocation does not erase
those records or copies; retention/offboarding is a separate operation. If the
processing policy itself changes so that old records are no longer permitted for
reproduction, the status operation is denied. Keeping an original baseline and
new observation periods available may require separate active grants covering
their respective authorized scopes.

## API and storage

All routes have the prefix `/companies/{company_id}`.

| Method / suffix | Contract |
|---|---|
| `POST /private-capacity/revisions/{revision_id}/reviews/{review_kind}` | `PlanReviewRequest`; path and body review kinds must agree |
| `GET /private-capacity/revisions/{revision_id}/reviews` | Both role histories, explicitly historical |
| `POST /private-baselines/cases/{case_key}` | `BaselineRequest`; explicit scenario, plan/review hashes and predecessor |
| `GET /private-baselines/cases/{case_key}` | Historical baseline designations |
| `GET /private-baselines/designations/{baseline_id}/status` | Original-source reproduction and current comparison support |

Writes require explicit bearer authentication before reading a bounded 1 MiB
body, return generic validation errors and use the server's processing environment
where processing is required. All responses are non-cacheable. Idempotent retries
return the original historical receipt only for the same request and author;
conflicting retries or stale role/baseline heads fail with 409. There are no MCP
or public-export routes for these private contracts.

Migration `0013` adds immutable review and baseline tables with forced company
RLS, exact plan/case/review/predecessor foreign keys, unique stream heads and
insert/select-only runtime permissions. Writes and audit events are atomic.
Populated downgrades are blocked, including review-only history and migration
owners without a company scope. Whole-company offboarding removes both tables'
company records with their source chain while retaining minimal audit events.

## Remaining pilot work

Private actual observations, reviewed counterfactuals, attribution, intervention
authorization and delivery evidence, executive memo composition and a usable
pilot review flow still require integration. These mechanisms also need an actual
sponsor, authorized company records and participating reviewers before they can
represent a performed pilot. Retention operations and the
[pilot entry gates](../pilot-plan.md) remain outstanding.
