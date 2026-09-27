---
name: pricing-value-creation
description: Find and size pricing levers for a PE portfolio company (list-price increases, discount leakage, price realization at renewal, legacy price-book migration, packaging/tiering, and value-metric changes) using the price waterfall and deterministic sizing tools. Use when the task mentions pricing, discounting, monetization, packaging, price increase, or price realization.
---

# Purpose
Pricing is usually the fastest EBITDA lever, and also the easiest to overstate. This skill finds where price is leaking, sizes only what contracts and customer behaviour allow, and makes the churn response an explicit assumption.

# Rules
- Get the waterfall from `price_waterfall(company_id, period, segment)`. Don't reconstruct discounts from invoices yourself.
- Every sized opportunity states an explicit **customer-response assumption** in its realization rate. A base case assuming zero churn or downgrade response needs evidence, such as a prior increase that was absorbed.
- Contract constraints come before sizing. If contract terms aren't in the evidence store, the opportunity is `NEEDS_EVIDENCE`.

# Price waterfall
List price → **on-invoice discounts** (negotiated %, promotional, volume) → invoice price → **off-invoice leakage** (free months, extended payment terms, credits, uncharged services, rebates) → pocket price.

Report leakage as a share of list for each layer. The largest layer is usually the first place to look.

# Diagnostic checklist
1. **Discount dispersion.** For comparable deals (same product, similar size and segment), does discount vary widely? High dispersion with no link to deal size means discount governance is the lever, not list price.
2. **Discount timing.** Discounts concentrated at quarter or year end point to rep behaviour and approval policy.
3. **Renewal realization.** Did contracted uplifts at renewal actually happen? Compare contracted uplift with realized uplift in invoice data.
4. **Legacy price books.** Share of ARR on old price books or grandfathered plans, and the gap to the current price book.
5. **Packaging fit.** Feature usage by tier (`get_usage_metrics`). Heavily used premium features in low tiers, or unused features in high tiers, point to repackaging.
6. **Value metric.** Does price scale with the value customers get (seats, usage, transactions)? Fast-growing usage with flat price is a monetization gap.

# Contract constraints (check before sizing)
- Price-increase caps (fixed % or CPI-linked)
- Multi-year price locks
- Most-favoured-customer clauses
- Notice periods for price changes, which determine when uplift can start
- Termination-for-convenience rights

# Sizing guidance
| Opportunity | Baseline metric | Improvement rate means | Realization rate reflects |
|---|---|---|---|
| Renewal price uplift | `renewing_arr` (renewals in the next 12 months) | Uplift % | Accepted share after negotiation, churn, and downgrade |
| Discount governance | `discounted_arr` | Reduction in average discount, as % of list | Adoption of the approval policy by sales |
| Legacy migration | `legacy_price_book_arr` | Gap to current price | Share migrated in the window, net of churn |
| Packaging/value metric | `total_arr` with `metric_params.segment` for the affected segment | Expected ARPA change | Adoption and rollout timing |

- Only renewals inside the window count toward in-year value. Run-rate value is annualized. Label which one you mean.
- Implementation costs (CPQ changes, pricing study, sales training) go in `one_time_cost`. Ongoing tooling goes in `annual_run_cost`.
- Customer-concentration risk: if the top customers hold a large share of affected ARR, size them separately or exclude them, and say which.

# Red flags
- Increases proposed on customers with falling usage (check with `customer-retention`)
- Sales compensation that pays on bookings regardless of discount (flag for the 100-day plan)
- Competitive pricing claims with no evidence id

# Output contract
- Waterfall summary by segment, with evidence ids.
- Findings, one per leakage source or monetization gap.
- Opportunities with contract-constraint status (checked / `NEEDS_EVIDENCE`) and an explicit customer-response assumption.
- Risks: churn response, competitive response, concentration.


# Numeric claims and server validation
Before writing a numeric finding or proposal, call `get_numeric_sources(company_id)`. Copy an exact catalog key and use `{{quantity:KEY}}` in prose; for example `Legacy share is {{quantity:pricing.legacy.legacy_arr_share}}` only when that key is returned. The server renders metric, value, unit, company, period and evidence together. Do not paste bare values into `record_finding` or `propose_opportunity` text, invent keys, or use identifiers as numeric sources. Qualitative wording is allowed. Structured scenario-rate/cost fields remain assumptions and must not be recast as measured facts.

Proposal, draft and submission calls enforce sufficiency, source freshness, policy eligibility, evidence and overlap checks. If rejected, record the named gap and resolve it; rewording the same unsupported or overlapping proposal does not make it eligible. Worked examples below were regenerated through a scripted MCP replay on the date shown in each file. They illustrate executable calls and returned outputs, not a human acceptance session.

# References
- `references/worked-example.md`: tool outputs and findings for the fictional Beacon fixture, generated from tool calls; see its scripted replay date.
