# ADR 0010: dated incremental underwriting model

Status: accepted for the constructed exercise. This extends the financial model;
durable case revisions and exact-version research receipts are now described in
[ADR 0013](0013-immutable-case-reviews.md). No actual human review is asserted. Capacity scheduling
and version 2 benefit-availability masks are defined in [ADR 0012](0012-capacity-aware-operating-plan.md).

## Decision

Use the existing immutable Pydantic/Decimal conventions in `diligence`, with a
24-month calendar, stable initiative IDs, source-classed evidence, typed numeric
assumptions and explicit invalidating conditions. Preserve the existing screening
calculator and its approved historical plans. This module creates neither an
operating approval nor a realization claim.

The financial engine owns dated accrual and cash entries. The constructed scheduler
supplies effective dates and availability masks; it does not calculate financial totals.
Scenario assumptions reference stable IDs and declare units. Driver references,
cost references, source references, scenario identities and horizon dates are
validated before calculation. The public exercise rejects private source classes.

## Economics and timing

- Pricing combines uplift and incremental churn on one cohort. Price benefit is
  calculated on retained revenue; lost baseline revenue is separate. Variable
  costs follow the net revenue change. Collection lag and variable-cost payment
  lag are separate assumptions.
- Service capacity is contacts × coverage × net successful resolution × handling
  hours. Financial benefit is the minimum of avoided-work value, a declared cost
  action and eligible spend. Released hours without a cost action earn zero.
- Collections accelerate payment of existing receivables. The cash difference
  reverses on the counterfactual collection date within the modeled horizon. No
  new revenue, recurring earnings or valuation benefit is created.
- Recurring expense, implementation expense and capex have explicit recognition
  and payment dates. Payment can precede or follow expense recognition. Capex
  affects cash once, not EBITDA. The model does not calculate EBIT, depreciation,
  tax, financing or a statutory statement of cash flows.

Benefits accrue ratably within each calendar month after eligibility. Differences
of rounded cumulative accruals allocate exact cents without a negative rounding
residual on the final day. Explicit cost dates represent the chosen management
model convention, including monthly fees recognized at the start of the month.
Day 100 includes the start date and uses the same dated entries as monthly totals.

EBITDA plus the operating accrual-to-cash timing adjustment, the existing-receivable
timing movement and signed capex equals the **incremental pre-tax cash proxy**.
Implementation expense already present in EBITDA is not deducted a second time.
Delayed settlement beyond month 24 is shown separately. Cost recognition/payment
outside the horizon is rejected, requiring an explicit revised horizon design.

Funding uses dated cumulative cash balances. Cash-proxy recovery occurs after the
last negative cumulative balance within the forecast horizon; a temporary positive
collection balance followed by a reversal is not sustained recovery. This remains
a pre-tax modeled measure, not evidence of actual payback or post-horizon recovery.

## Aggregation, valuation and limitations

A benefit pool may have only one driver in each scenario. Pricing/churn interaction
is calculated together; unresolved overlaps are rejected rather than summed.
Shared costs occur once. Excluding initiatives removes only explicitly avoidable
costs; retained commitments survive even if every initiative is excluded. A richer
allocation/exclusivity model remains future work.

Valuation multiplies year-two recurring contribution by explicitly assumed
multiples. Temporary implementation expense is excluded through a named bridge;
the engine does not attest that the contribution is maintainable. It reports an
incremental EV sensitivity, not total enterprise value, equity value or proceeds.
Multiples change provenance and valuation without changing operating/cash output.
Scenario labels are judgmental cases, not probabilities or confidence intervals.

The [SEC non-GAAP interpretations, questions 102.07 and 103.01–103.02](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures)
support explicit measure definitions and reconciliation. They do not prescribe
this management model or certify its assumptions. No GAAP-compliance or independent
finance-review claim is made.

## Verification

Worked tests independently check price/churn interaction, recognition/payment
lags, midmonth eligibility, exact day 100, capex/expense separation, service cost
caps, collection reversals, exclusion with retained costs, adverse cases, rounding,
source-policy isolation and valuation independence. All monthly cash bridges and
annual/horizon totals reconcile. Public HTML escapes input and preserves source
files. Installed-package replay and narrow-screen/keyboard checks cover the new
command and page. These tests prove model behavior, not economic feasibility.
