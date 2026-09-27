---
name: ai-opportunity-assessment
description: Assess where AI and automation can create measurable value in a PE portfolio company (cost-to-serve in support, onboarding and back office; AI product features that support pricing or retention; GTM productivity), scoring value, feasibility, risk and time-to-value and sizing only what volume and cost data support. Use for AI strategy, automation, GenAI, or operating-efficiency-through-AI questions.
---

# Purpose
Replace "we should use AI" with a short, evidence-backed list of workflows where automation has measurable volume, cost, and feasibility, and route revenue-side AI ideas to the levers that actually capture the value.

# Rules
- Only workflows with **measured volume and unit cost** can be sized. Everything else stays an unsized candidate.
- Cost-out opportunities use lever `ai_automation`. AI *product features* create value through price or retention, so size them in `pricing-value-creation` or `customer-retention`, not here. Don't count them twice.
- Headcount reduction is a management action. Frame savings as capacity or cost-to-serve and mark any headcount implication *requires approval*, noting that HR and legal review is needed.
- Customer data use can be restricted by contracts or DPAs. If a candidate needs customer data and the terms aren't in evidence, it's `NEEDS_EVIDENCE`.

# Procedure
1. **Inventory candidate workflows from data, not from general AI patterns.**
   - Support: ticket volume by category, handle time, and cost per ticket (`get_support_metrics`, `get_financials`).
   - Onboarding and implementation: time-to-live and services cost.
   - Back office: finance ops, billing operations, collections headcount and volumes (`get_financials`).
   - GTM: proposal and RFP volume, SDR research time, if tracked.
2. **Profile each candidate:** annual volume, unit cost, share of volume the automation can address (evidence: a categorized sample, not an assumption), quality tolerance (how costly is an error?), data availability, and constraints.
3. **Score** each candidate on the four dimensions below.
4. **Size** the top candidates that have evidence. List the rest as unsized, with the data needed.

# Scoring rubric (1 = weak, 3 = strong)
| Dimension | 3 means |
|---|---|
| Value | Large measured cost pool, high addressable share |
| Feasibility | Structured, repetitive work; labelled history available; mature tooling |
| Risk (inverted) | Errors are cheap and reversible; a human review step exists; no regulated data |
| Time to value | Pilot possible within 60 days on existing systems |

Report the scores. Don't combine them into one number. `prioritize_opportunities` does the deterministic ranking once candidates are sized.

# Sizing guidance
| Field | Meaning here |
|---|---|
| Baseline metric | Annual cost of the workflow, e.g. `support_cost_tier1` |
| Improvement rate | Addressable share × expected automation or deflection rate |
| Realization rate | Adoption ramp and quality-gated rollout in the window |
| `annual_run_cost` | Inference, vendor licences, and oversight time. Always non-zero. |
| `one_time_cost` | Integration, data preparation, evaluation build |

# Red flags
- Deflection rates quoted from vendor marketing instead of a company pilot or categorized sample
- Savings that assume removing roles still needed for escalations
- Candidates touching regulated decisions (credit, employment, health) with no human review
- Proposals with no evaluation plan. Every piloted AI workflow needs an accuracy measure and a rollback path.

# Output contract
- Candidate table: workflow, volume, unit cost, addressable share, the four scores, and evidence ids.
- Sized `ai_automation` opportunities, with run costs.
- Revenue-side AI ideas handed off to the pricing or retention skills, with the reason.
- Unsized candidates and the data needed.
- Risks, including data-rights and quality risks.


# Numeric claims and server validation
Before writing a numeric finding or proposal, call `get_numeric_sources(company_id)`. Copy an exact catalog key and use `{{quantity:KEY}}` in prose; for example `Legacy share is {{quantity:pricing.legacy.legacy_arr_share}}` only when that key is returned. The server renders metric, value, unit, company, period and evidence together. Do not paste bare values into `record_finding` or `propose_opportunity` text, invent keys, or use identifiers as numeric sources. Qualitative wording is allowed. Structured scenario-rate/cost fields remain assumptions and must not be recast as measured facts.

Proposal, draft and submission calls enforce sufficiency, source freshness, policy eligibility, evidence and overlap checks. If rejected, record the named gap and resolve it; rewording the same unsupported or overlapping proposal does not make it eligible. Worked examples below were regenerated through a scripted MCP replay on the date shown in each file. They illustrate executable calls and returned outputs, not a human acceptance session.

# References
- `references/worked-example.md`: tool outputs and findings for the fictional Cedar fixture, generated from tool calls; see its scripted replay date.
