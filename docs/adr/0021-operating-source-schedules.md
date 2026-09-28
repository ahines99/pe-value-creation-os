# ADR 0021: Constructed operating records constrain a prospective forecast

Status: implemented. This is an analytical source challenge, not a new approved
case revision or an operating actuals import. Earlier immutable cases, financial
claims and execution receipts remain intact.

## Decision

Bind one constructed source book to the exact original underwriting and proposed
100-day plan. Require matching case, company, currency, input fingerprints and
cutoff. Use the scheduler's proposed acceptance dates, then derive record-level
eligibility and timing. Reuse the existing Decimal financial ledger, dated
accruals, settlement lags, costs, totals and funding calculation.

The public input contains five authored contracts, two service queues in each of
24 authored monthly plans, one vendor expense pool and five opening invoices.
No record describes a Progress customer, vendor, invoice or intervention.
Public consolidated statements provide company context only. Declared controls
reconcile the exercise's scope, not a fabricated company or segment ledger.

## Rules

### Pricing

Each distinct contract has a monthly revenue baseline, renewal and term-end
dates, required notice, proposed notice date, explicit permission and a cap.
The earliest notice is the latest of the proposed date, source cutoff and
scheduled acceptance gate. Notice after the deadline blocks that renewal. An
economic launch after renewal also blocks it; the model cannot impose a mid-term
change or silently roll the contract into another renewal. Absent permission,
missing caps and nonpositive permitted uplift create no pricing credit.

Eligible terms use the lower of assumed uplift and contractual cap. The existing
capture, incremental churn and variable-cost formulas apply once to that row.
Revenue accrues only through the stated term end and within the forecast horizon.
Longer contractual terms retain their original end date without extrapolating
earnings past the 24 modeled months. The ledger's optional benefit
end date limits accrual, while settlements retain their lagged dates. The default
aggregate model is unchanged. A collection reversal cannot be truncated through
this new option.

### Service

Monthly queue contacts must reconcile to a declared control. Eligible contacts
cannot exceed the population; sample, resolved and repeated-contact counts must
reconcile. Quality-failed or missing-review queues and zero-sample queues cannot
contribute capacity. Aggregate eligible volume is capped by the scenario's
coverage assumption. Each remaining queue uses the lower of scenario resolution
and net sample resolution, multiplied by its handling time. Subtract the authored
monthly QA workload and floor net capacity at zero.

This sample is a constructed constraint, not a statistically validated success
estimate. Coverage and resolution remain judgmental scenario inputs. Capacity
accrues after the later of economic launch and proposed acceptance. Spend removal
requires separate vendor release evidence/date and is capped by avoided work,
the original scenario's action budget and vendor spend above its minimum.
Vendor release may lag capacity availability. The first partial month is prorated
by the shared daily accrual convention. Missing months explicitly block service
benefit and keep all original costs; they are not observed zero-activity months.

This adapter covers a single vendor pool with vendor-reduction or no-action
semantics. It does not impersonate a staffing, hiring or multi-vendor allocation
model. Source rates and populations replace aggregate estimates; scenario action
budgets, coverage/resolution limits and all costs remain explicit.

### Collections

Opening invoices predate the source cutoff. Credits and prior payments reduce
open balance; disputes reduce eligible balance. Each invoice retains an authored
acceleration and counterfactual payment date. The actual modeled acceleration
waits for both scenario readiness and the capacity plan. A missed window produces
no benefit. Apply the scenario acceleration fraction to the eligible balance,
then record equal positive and negative cash movements. Neither movement creates
revenue or EBITDA. Both dates must fit inside the explicit horizon.

### Controls and authority

Reject duplicate contracts/invoices, duplicate service months/queues, inconsistent
amounts/counts and mismatched scope totals. Require distinct assumption references
within each driver so source overrides cannot alias unrelated quantities. Private
source classifications are rejected; this is not the permissioned-data lane.

Every original dated expense, fee and capex item remains once. A blocked source
benefit does not cancel its cost. The report exposes record decisions, monthly and
daily ledger entries, original scheduled forecast, source scope and fingerprints.
Source changes create new report fingerprints without rewriting original inputs.
There is no database mutation, management approval, automatic case promotion,
causal attribution, model call, exit value or actual company result.

## Worked result

In the base example, the 300,000 monthly January contract misses its 90-day
notice deadline. The 250,000 April contract qualifies at a 4% cap; the 150,000
February contract qualifies at a 3% cap and expires in June. Two other contracts
lack permission. For the short contract, full-month gross uplift is 2,910.38,
churn leakage is 750.00 and variable-cost change is −432.08: EBITDA is 1,728.30.
The final June revenue receipt still settles in July, after accrual ends.

The base service case releases 760 full-month net hours: 7,000 coverage-limited
contacts × 60% resolution × 0.2 hours − 80 QA hours. Vendor savings start on
February 15, yielding 9,000 in February and 18,000 in a full subsequent month.
The quality-failed queue remains excluded despite its high resolution count.

Invoices reconcile to 1,300,000 open balance; 450,000 is disputed, and another
100,000 misses its acceleration window. Base acceleration is 15% of 750,000,
or 112,500, which reverses on March 15. The collection mechanism has zero EBITDA.

With all original costs retained, base year-one EBITDA is **−18,314.50**, cash is
**−38,532.00**, and day-100 cash is **−21,500.00**. The downside remains negative.
No multiple is applied to these bounded and unreviewed future benefits.

## Verification and remaining work

Independent worked checks cover price caps, churn, partial months, delayed cash,
term expiry, quality/recontacts/QA, minimum commitments, missing sources,
collections reversal, blocked capacity and retained costs. Corrections change the
source-bound report while preserving earlier inputs. Export tests cover source
classification, stale bindings, overwrite prevention and escaped text.

Remaining work includes actual authorized operating records, real notice/release
evidence, finance/practitioner challenge, actual effort/capacity, shared-pool
allocation and exclusivity across competing interventions, lifecycle/learning,
and any reviewed promotion into a new case revision. The public comparative
amortization difference is also still unresolved; this source exercise does not
resolve or bypass that accounting question.
