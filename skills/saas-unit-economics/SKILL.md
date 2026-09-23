---
name: saas-unit-economics
description: Assess SaaS growth efficiency and unit economics for a portfolio company (ARR bridge, NRR/GRR, CAC payback, LTV/CAC, magic number, burn multiple, Rule of 40, gross margin) using deterministic metric tools, then turn weaknesses into evidence-cited findings and sales-efficiency or gross-margin opportunities. Use for go-to-market efficiency, sales productivity, "are the unit economics healthy", or growth-vs-profitability questions.
---

# Purpose
Diagnose *why* growth efficiency is weak, not just *that* it is weak, and route each root cause to the right lever.

# Rules
- Get every metric from `compute_saas_metrics(company_id, period)`. The definitions below are for interpreting and reviewing tool output. Never compute them yourself.
- The tool reports which variant it used (for example, EBITDA vs FCF margin in Rule of 40). Quote the variant.
- Screening thresholds live in `project://policies` and are set by the fund. Use them. Don't substitute remembered "industry benchmarks". For peer context, call `get_benchmarks(metric, peer_set)` and cite the result.

# Metric definitions (house standard)
| Metric | Definition |
|---|---|
| ARR bridge | Opening ARR + new + expansion − contraction − churn = closing ARR |
| GRR | (Opening ARR − contraction − churn) ÷ opening ARR, trailing 12 months, opening cohort only. Cannot exceed 100%. |
| NRR | (Opening ARR + expansion − contraction − churn) ÷ opening ARR, same cohort and window |
| CAC payback (months) | Prior-quarter S&M expense ÷ (net new ARR in quarter × subscription gross margin) × 12 |
| LTV / CAC | (ARPA × subscription gross margin ÷ annual dollar churn rate) ÷ CAC per new customer |
| Magic number | (Current-quarter revenue − prior-quarter revenue) × 4 ÷ prior-quarter S&M expense |
| Burn multiple | Net burn ÷ net new ARR, same period |
| Rule of 40 | Revenue growth % + profit margin % (variant reported by tool) |
| Subscription gross margin | Subscription revenue less hosting, third-party software, and support COGS, excluding services |

# Data-quality checks (before interpreting)
- **Bookings vs ARR.** Multi-year prepaid contracts, one-time fees, or services revenue counted as ARR inflate every ratio. Check the ARR definition in the data inventory.
- **Capitalized commissions.** Under ASC 340-40, commissions may be capitalized. CAC must use commissions *paid* or *expensed as incurred*, not amortization. If you can't tell, flag it.
- **S&M allocation.** Confirm that customer success and account management are classified consistently. Moving them between S&M and COGS shifts both CAC and gross margin.
- **Entity duplication.** Logos with several legal entities distort customer counts and ARPA. Check with the entity-resolution notes in the data inventory.
- **Period mismatch.** Every ratio must use aligned periods. The tool enforces this, but check it when combining outputs.

# Diagnostic trees
**Weak CAC payback or magic number.** Decompose in this order:
1. Spend: S&M growth vs new ARR growth, and mix by channel and segment.
2. Conversion: win rate and pipeline coverage trend (CRM).
3. Deal size: ACV trend by segment. If ACV is falling, check discounting with `pricing-value-creation`.
4. Capacity: ramped vs unramped reps, attainment distribution.
5. Margin drag: if subscription gross margin is low, payback is weak even with healthy acquisition. Go to the *Low gross margin* tree.

**Weak NRR.** Split into GRR and expansion:
- GRR weak → hand off to `customer-retention`.
- GRR healthy but expansion weak → packaging and upsell path. Hand off to `pricing-value-creation`.

**Low gross margin.** Hosting cost per customer or unit of usage, support cost per customer, and services mix. Automation candidates go to `ai-opportunity-assessment`.

**High burn multiple with healthy payback.** Look outside go-to-market: G&A and R&D growth vs revenue growth, from `get_financials`.

# Opportunity framing
| Lever | Typical baseline metric | Notes |
|---|---|---|
| `sales_efficiency` | `s_and_m_expense` | Savings at constant new ARR. Flow-through is set server-side. State the assumption that new ARR holds. |
| `gross_margin` | `subscription_cogs` | Hosting or vendor renegotiation, support efficiency. Add a run cost if tooling is needed. |

Never size "grow faster" as an opportunity on its own. Growth levers belong to pricing, retention, or a specific GTM change with evidence.

# Output contract
- Metric table: metric, value, period, variant, evidence id, and peer percentile if benchmarked.
- Findings, one per root cause, each with evidence ids, recorded with `record_finding`.
- Hand-offs to other lever skills, with the reason.
- Data-quality flags that change interpretation.
- `NEEDS_EVIDENCE` items.

# References
- `references/worked-example.md`: tool outputs and findings for the fictional Cedar fixture, generated from real tool calls.
