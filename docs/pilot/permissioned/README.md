# Permissioned operating pilot package

Status: prepared for sponsor discussion; **no sponsor, authorization or pilot is
in place**. Alex confirmed this on September 28, 2026 and requested preparation.
Codex owns technical preparation and all subsequent mapping, modeling, tests,
analysis and reporting. No external message has been sent.

Start with the shareable [sponsor brief](sponsor-brief.md). Use the
[kickoff worksheet](kickoff-worksheet.md) once a prospective sponsor is identified.
Both are discussion materials; neither represents authorization or participation.

### Who does what next

| Stage | Codex / project preparation | Alex | Sponsor / company |
|---|---|---|---|
| Now, without a sponsor | Maintain demonstration, brief, data specifications and review worksheets; continue public research and model validation | No immediate setup or data task | No participation assumed |
| Sponsor introduction | Tailor the agenda and scope proposal; prepare introduction text if requested | Introduce an authorized contact when available | Identify decision, finance/data owner and operator |
| Before private data | Implement and test the agreed private ingestion lane, access controls, mappings and retention workflow; assemble readiness evidence | Coordinate access to the authorized parties where needed | Authorize purpose, records, handling and reviewers; satisfy company-side entry gates |
| Diagnostic and intervention | Prepare reconciliations, alternatives, plan, review packets, dispute log and outcome analysis | Coordinate only where the company requires the project owner | Validate records, approve or reject actions, perform authorized operations and assess results |
| Closeout | Draft evidence-based findings and document data disposition | Decide whether to seek another pilot | Decide continuation and any publication permission |

The existing operating pilot plan specifies a **six-week diagnostic trial**.
The day-30/60/100 checkpoints below concern a **separately authorized intervention**,
with its clock starting at intervention kickoff. Neither stage promises observed
earnings or cash by a fixed date. Selecting a deterministic-only route would
require an explicit amendment to the existing model-enabled pilot plan; this
package does not silently change that requirement.

The public Progress case is a research reference, not the presumed pilot company.
A pilot needs an organization that actually controls the relevant operating and
accounting records and agrees to a bounded activity. University market-data
access does not grant access to a company's customer or management systems.

## Sponsor brief

**Purpose:** assess whether an evidence-linked decision workflow helps the sponsor
select and monitor one value-creation intervention. A negative or inconclusive
result is acceptable; there is no promised savings threshold.

**Proposed scope:** one company, one agreed lever, read-only source exports,
two reviewed diagnostics and one limited intervention/measurement cycle. Start
with renewal pricing, service operations or collections only if the corresponding
records and accountable operator are available. No automatic source-system writeback.

**Sponsor effort:** confirm scope and decision rights, identify a finance/data
owner and operator, review the baseline and proposed intervention, attend two
decision sessions, and review the resulting evidence. Codex prepares the materials,
performs data work and records disputes; managers make actual company decisions.

**Outputs:** source reconciliation and exclusions, baseline and assumptions,
selected/rejected/deferred hypotheses, explicit earnings/cash scenarios, dated
capacity-aware execution plan, variance/attribution report and go/no-go memo.

**Entry gates:** the existing [operating pilot plan](../pilot-plan.md) and its
staging, legal/model-data, domain and source-conformance requirements still apply.
This package does not waive them or start the pilot. Hosting or provider spending
requires a specific authorized plan if that delivery route is selected.

## Authorization and scoping record

Complete this record with actual parties before receiving private operating data.
It is an operational checklist for the parties' agreement, not a legal contract.

| Field | Required evidence | Current state |
|---|---|---|
| Organization / authorized sponsor | Named entity, role and authority to authorize the pilot | Not provided |
| Data owner and accounting reviewer | Named owners and contact route authorized by the sponsor | Not provided |
| Accountable operator | Named role/person accepting capacity and intervention responsibility | Not provided |
| Permitted purposes / fields / periods | Written scoped use, recipients, processing environment and prohibited uses | Not provided |
| Publication | Separate decision covering identifiers, figures, derived charts and review quotes | No permission for a company pilot publication |
| Retention and return/deletion | Agreed dates, legal hold process and deletion/return evidence | Not provided |
| Model processing | Approved data handling and provider terms, or explicit deterministic-only research scope pending pilot-plan amendment | Not decided; no private records may be sent to models by assumption |
| Intervention authority | Human decision rights, affected cohort, spending cap and rollback authority | Not provided |
| Success and stopping criteria | Predeclared measurement, quality limits and adverse-event response | Draft below; not management-approved |

## Minimal data request

Use stable pseudonymous IDs and omit names, emails and free-text ticket bodies
unless a selected hypothesis specifically requires and authorizes them. Request
only the selected lever's records. Codex supplies the mapping template and
validates the sample before a larger export. Do not email credentials or bulk
customer records to initiate a conversation.

| Data | Minimum fields | Purpose / reconciliation |
|---|---|---|
| Monthly P&L, 24 months where available | Period start/end, entity/perimeter, currency, account/code, amount, basis, adjustment/revision ID | Tie monthly totals to finance-approved statements; distinguish acquisitions/FX and recurring/one-time costs |
| Revenue/customer bridge | Pseudonymous account ID, product/channel, period, recognized revenue, recurring/one-time classification, currency | Reconcile scoped revenue to P&L and document omitted populations; do not equate billings with revenue |
| Pricing option | Account/contract IDs, renewal/effective/notice dates, contracted uplift/caps, units/list/net price, credits/concessions, eligibility and churn outcome | Establish enforceable and economically viable repricing cohorts; exclude ineligible contracts |
| Service option | Pseudonymous ticket/category, dates, handle/escalation/reopen counts, quality outcome, staffing/vendor cost and committed cost action | Separate safe containment, capacity freed, spend avoided and actual cost removed |
| Collections option | Invoice ID/account, issue/due/payment dates, currency, original/open/paid amounts, credits, dispute state and terms | Tie aged receivables to subledger/GL; isolate collectible balance and payment timing |
| Capacity and execution | Proposed resource/operator, weekly change hours, other commitments, dependencies, decision authority | Build an actually feasible first wave and identify unconfirmed assumptions |

Record for each export: source-system owner, extraction query/filter, cutoff,
covered/excluded population, unit/currency, revision rules, record count, content
hash and permitted destination. Missing data produces an explicit request or
unsized hypothesis, never fabricated rows to make the pilot pass.

## Bounded intervention design worksheet

1. Choose one mechanism and eligible cohort; name the management decision and
   contract/service/collection constraints that must be cleared.
2. Freeze baseline and primary KPI, measurement period, denominator, costs and
   exclusion rules before viewing outcomes. Specify a comparable untreated group
   or staged rollout where feasible; record limitations if no comparator exists.
3. Specify accountable operator, weekly capacity, milestone dates, implementation
   cash cap, approval threshold and rollback owner. Foundation work consumes
   capacity and cost even if it has no direct benefit.
4. Set adverse thresholds: customer retention/complaints, service quality/reopens,
   disputed balances or another lever-specific harm signal. A breach triggers
   human review/stop, not an automatic favorable reforecast.
5. Predeclare the financial bridge: period revenue/cost effect, implementation
   expense, capex and working-capital cash; do not call a KPI change EBITDA.
6. Fix steering cadence and dates after kickoff. At day 30 review evidence and
   eligibility; day 60 review intervention/quality evidence; day 100 review the
   result and unresolved attribution. These are review checkpoints, not a promise
   that cash or earnings will be observed within 100 days.

## Review worksheet and exit decision

| Review | Reviewer checks | Evidence Codex prepares |
|---|---|---|
| Source / baseline | Correct period, units, perimeter and reconciliation; material exclusions understood | Source manifest, exception log, normalized facts, immutable baseline fingerprint |
| Economics | Mechanism, assumptions, cost timing, overlaps, downside and cash treatment make sense | Driver model, hand-worked checks, sensitivity and alternative explanations |
| Execution | Capacity/owners/dependencies fit; intervention and stopping rules authorized | Dated plan, capacity conflicts and exact-version decision packet |
| Outcome | Actuals reconcile; counterfactual and residual explicit; no double attribution | Original/current/actual bridge, allocation ledger, confidence limitations and adverse cases |
| Exit | Continue, revise, stop or expand, with reasons and next owner | Two-run comparison, dispute closure log, data retention disposition and go/no-go draft |

Record reviewer identity/role, review date, exact artifact version, objections,
response and unresolved issues only after the review occurs. Codex cannot sign
for an operator, accountant or sponsor. A completed preparation package is not
evidence that these people participated or that the pilot succeeded.

The first sponsor discussion should resolve scope, ownership and access. Codex
can prepare an introduction message once a contact and permission to send it are
provided. No account purchase, deployment or outside contact is needed to use
this package for planning.

## Measurement rehearsal now available

The [constructed realization walkthrough](../../portfolio/realization.html) rehearses
complete-month source reconciliation, fixed-baseline comparison, explicit signed
claims, unassigned residuals and source corrections. It is suitable for showing
a prospective sponsor the questions and outputs. It does not contain a real
company ledger, validated counterfactual, accepted intervention or causal result.

The current ingestion contracts deliberately accept only constructed records.
Before a permissioned pilot uses private records, Codex must implement and test
the authorized private-data lane, agreed source mappings, retention controls and
permissioned work-acceptance evidence. Constructed delivery-to-claim links are
now demonstrated in the [execution review](../../portfolio/execution.html): late
acceptance blocks whole-month credit, and withdrawal invalidates support while
preserving source accounting. These are rehearsal receipts only. Do not relabel company records as constructed
to bypass this boundary. Sponsor participation and authorization remain absent.


The [operating source challenge](../../portfolio/operating-sources.html) now
demonstrates the minimum record checks for pricing, vendor-service and collections
work: scope reconciliation, notice/caps, bounded terms, evaluation and QA,
vendor minimums/release evidence, credits/payments/disputes and cash reversals.
Its base first-year result is adverse after all original costs. The source book
is a mapping/design example only; its classification explicitly rejects private
operating records. Codex will implement the authorized data lane against the
sponsor's actual scope rather than disguising private records as constructed.

## Sponsor demonstration and immediate ownership

Use the [integrated case review](../../portfolio/source-review.html) to show how
an evidence challenge becomes a saved forecast revision, how a reviewer requests
a correction, and how an adverse corrected model can be accepted without approving
an intervention. The frozen close, accounting sources and attribution claims
remain unchanged. All receipts in this demonstration are simulated.

Codex owns the technical preparation, source mapping templates, reconciliation,
model changes, test evidence, review materials and final reporting. No additional
input from Alex is required to continue those preparations. When a prospective
sponsor exists, Alex's necessary action is an introduction to someone authorized
to scope the pilot and identify a finance/data owner and accountable operator.
No contact has been made and no sponsor commitment is implied.

For a first meeting, open the integrated review and discuss three questions:
which single lever matters, who can validate its records and approve its action,
and what evidence would justify stopping. Complete the scoping record above
before receiving private records; then Codex adapts the data request and produces
a dated workplan for the agreed scope.
