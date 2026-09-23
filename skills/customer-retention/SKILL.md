---
name: customer-retention
description: Diagnose gross and net revenue retention for a PE portfolio company (cohort curves, churn and contraction drivers, segment concentration, involuntary churn, and leading indicators from product usage and support) and size retention-improvement opportunities. Use for churn, NRR/GRR, renewal risk, customer health, or customer-success questions.
---

# Purpose
Find where retained revenue is being lost, separate causes from correlations, and size only the churn that is realistically addressable.

# Rules
- Get cohorts from `compute_retention_cohorts(company_id, cohort_grain)` and headline GRR/NRR from `compute_saas_metrics`. Don't recompute them.
- Label every driver claim as **observed** (the data shows it) or **hypothesis** (plausible, not yet corroborated). Causal claims need corroboration beyond correlation. Reason codes plus usage or support signals count; one signal alone doesn't.
- CRM churn reason codes are entered by sales and are low-trust on their own. Cite them, but don't rely on them alone for high confidence.

# Procedure
1. **Headline.** GRR, NRR, and logo vs dollar retention for the trailing 12 months. Big gaps between logo and dollar retention show where the loss is concentrated: small customers or large ones.
2. **Cohort shape.** Is churn front-loaded (first 12 months: onboarding or fit problem) or steady (value or competitive problem)? Are recent cohorts better or worse than older ones?
3. **Segmentation.** Break churn and contraction down by segment, size band, product, acquisition channel, and tenure. Look for the smallest segment that explains most of the lost ARR.
4. **Involuntary churn.** Separate out failed payments, bankruptcies, and acquisitions. Failed-payment churn is usually a quick, low-risk win (dunning, card updater).
5. **Leading indicators.** For churned accounts compared with retained ones, check usage trend before renewal (`get_usage_metrics`) and support volume, severity, and CSAT (`get_support_metrics`). Record which signals show up early enough to act on.
6. **Renewal exposure.** ARR up for renewal in the next two quarters that shows the leading-indicator pattern, at segment level and not by named account in the output.
7. **Record findings** with `record_finding`, each tagged observed or hypothesis.

# Sizing guidance
| Opportunity | Baseline metric | Improvement rate means | Realization rate reflects |
|---|---|---|---|
| Voluntary churn reduction | `addressable_churned_arr` (annual voluntary churn in target segments) | Share of addressable churn prevented | Program ramp and coverage |
| Contraction reduction | `annual_contracted_arr` in target segments | Share of contraction prevented | Same |
| Involuntary churn recovery | `failed_payment_churned_arr` | Recovery share | Implementation timing |

- Exclude involuntary non-payment churn (bankruptcy, acquisition) from the addressable base.
- Program costs (CS headcount, health-scoring tooling) go in `annual_run_cost`. Skipping them overstates the value.
- If a price increase is proposed for the same customers, see the overlap rules in `pe-value-creation-diagnostic`.

# Red flags
- Retention "improving" only because the cohort window changed or churned logos were reclassified
- Health scores with no back-test against actual churn
- A single customer's churn driving the headline. Size those separately.

# Output contract
- Retention headline table with evidence ids.
- Cohort observations: shape, trend, and best and worst segments.
- Driver findings, each tagged observed or hypothesis, with confidence.
- Leading indicators and their lead time.
- Sized opportunities and program costs.
- `NEEDS_EVIDENCE` items, for example missing reason codes or no usage data.

# References
- `references/worked-example.md`: tool outputs and findings for the fictional Cedar fixture, generated from real tool calls.
