# Skill session: diagnostic on Cedar Field Analytics (PVC-070)

For the domain expert and engineering lead reviewing whether the `pe-value-creation-diagnostic` skill works end to end.

## How the session was run

- **Company:** Cedar Field Analytics, a fictional fixture company with a planted churn problem. The existing worked example covers Beacon, the pricing fixture.
- **Client:** the MCP stdio server that the Claude Code plugin launches (`pvc mcp-stdio`, dev mode), driven through the MCP client protocol.
- **Analyst:** Claude, following the skill's procedure and making each judgment from the tool outputs: which levers to pursue, the scenario rates, the confidence levels and the wording. Nothing was scripted by the rule-based proposer.
- **Two passes.** A read-only pass (policy, profile, inventory, sufficiency for all four analyses, metrics, retention, churn, pricing, support, usage, benchmarks) informed the judgments. A second pass ran the interactive run: findings, proposals, sizing, evidence listing, prioritization, plan draft and approval request. The read-only results are deterministic, so the second pass saw the same data.
- **Deviation:** the second pass did not repeat the intake read before recording findings. That exposed a bug (below).
- **Not done:** no human performed this session. A 15-minute repeat by a team member in Claude Code is still recommended before the domain-expert review (PVC-071).

## What the session found

1. **Bug, fixed.** `record_finding` rejected valid evidence ids ("Evidence … not found") until a read tool had loaded and registered the company's evidence. A read made before the company was onboarded also cached the data without registering it, for 60 seconds. `record_finding` now registers the company's evidence itself, and the cache reloads once the company is onboarded. Regression test: `tests/test_mcp.py::test_findings_can_cite_evidence_right_after_the_run_starts`.
2. **The run lock holds.** A `record_finding` call after `request_approval` was refused: "awaiting_approval and can no longer be changed".
3. **The skill procedure could be followed with the tools as they are.** Every tool name and argument the skill names worked. The unsupported steps the audit found (marking items `NEEDS_EVIDENCE`, a `contradicts` relation) had already been rewritten; see the skill's rule 6.

## Output (the skill's output contract)

All figures are copied from tool results. Currency is USD. Value-case figures are annual EBITDA, shown to the cent as the tools return them.

### 1. Summary
- Retention is the value lever. GRR is 0.7951 against a policy floor of 0.88, and SMB GRR is 0.5830.
- Pricing is healthy and is not proposed as a lever. Discount dispersion is at most 0.0346, renewal realization 0.9407 and legacy share 0.0305.
- The weak sales-efficiency readings (CAC payback 255.0852 months, magic number 0.1253) are treated as a churn symptom, not a cost problem, because LTV/CAC is 7.9197.
- Four opportunities are sized, for a total base-case run-rate EBITDA of 737,709.60 (in-year 370,286.08), per `draft_100_day_plan`.
- The plan is submitted for approval (approval `53c66ea7`); nothing proceeds without a human decision.

### 2. Findings
| Finding | Statement | Confidence | Evidence |
|---|---|---|---|
| `960b0284` | Trailing-12-month GRR is 0.7951 against a policy minimum of 0.88; NRR is 0.8607. | high | `87ee76de` (ARR) |
| `64e67b57` | SMB GRR is 0.5830 versus 0.8722 in enterprise and 0.8354 in mid-market; SMB lost 66 of 150 opening logos. | high | `87ee76de`, `01d1baab` (customers) |
| `e6069446` | Poor onboarding and product gaps are the top voluntary reason codes (26 each). Churned accounts used 0.3940 of core seats versus 0.7463 for retained accounts. Early-life churn is over-represented (1.4574). | medium (hypothesis) | `e3338b4a` (churn), `02d82167` (usage), `87ee76de` |
| `1abf0747` | Failed-payment churn is 0.1255 of churned ARR (policy maximum 0.10). | high | `87ee76de`, `e3338b4a` |
| `a7ce556f` | Discount dispersion is at most 0.0346 by segment, renewal realization 0.9407 and legacy share 0.0305: no pricing opportunity. | high | invoices, price books, contracts, ARR |
| `d70467e3` | CAC payback is 255.0852 months and the magic number 0.1253, while LTV/CAC is 7.9197. Churn absorbs most new ARR. | medium (hypothesis) | `87ee76de`, `f0fb4758` (P&L) |

### 3. Opportunities
| Rank | Opportunity | Lever | Low | Base | High | One-time cost | Confidence |
|---|---|---|---|---|---|---|---|
| 1 | `993b4617` SMB onboarding and adoption programme (`addressable_churned_arr`, segment smb) | retention | 116,929.91 | 280,631.78 | 491,105.61 | 0 | medium |
| 2 | `b81d785a` Failed-payment recovery (dunning and card updater) (`failed_payment_churned_arr`) | retention | 113,599.21 | 212,051.86 | 333,224.35 | 0 | medium |
| 3 | `6effbe48` Tier-1 support deflection with AI self-service (`support_cost_tier1`) | ai_automation | 73,266.55 | 175,839.72 | 307,719.51 | 0 | low |
| 4 | `abcad5b3` Mid-market health scoring and CS coverage (`addressable_churned_arr`, segment mid_market) | retention | 28,827.60 | 69,186.24 | 121,075.92 | 0 | low |

The ranks come from `prioritize_opportunities`, and the base-case total matches the plan total. One-time costs are 0 because the company supplied none; the plan must not be read as costless (see Risks).

### 4. Assumptions
- SMB programme: improvement 0.10 / 0.20 / 0.30, realization 0.5 / 0.6 / 0.7 (low/base/high). Judgment informed by the utilisation gap; no pilot result yet.
- Failed-payment recovery: improvement 0.25 / 0.40 / 0.55, realization 0.6 / 0.7 / 0.8. These are typical recovery rates, not company history.
- Tier-1 deflection: improvement 0.10 / 0.20 / 0.30, realization 0.5 / 0.6 / 0.7. Judgment; validate with a pilot.
- Mid-market health scoring: improvement 0.05 / 0.10 / 0.15, realization 0.5 / 0.6 / 0.7. Mainly judgment, hence low confidence.
- Baselines and EBITDA flow-through were derived by the server from company data (policy version `2026.09.1-placeholder`). The analyst supplied none.

### 5. Risks and counterarguments
- The ranking puts tier-1 deflection (low confidence) above mid-market health scoring, because its base case is larger. A reviewer who weights confidence more heavily might swap them. The ranking is left as the tool returned it.
- Reason codes are sales-entered and low-trust. The onboarding hypothesis rests mainly on the utilisation signal.
- Tier-1 deflection may have headcount implications. The plan marks it as a decision needing approval (HR/legal review).
- There is no overlap. The two retention programmes act on different segments, voluntary and failed-payment churn are separate baselines, and support deflection does not act on churn.
- One-time and run costs are not yet known. The base cases are gross of those costs until management supplies them.

### 6. Data gaps
- All four analyses had sufficient data; there are no `data_gap` findings and no unsized opportunities.
- Peer benchmarks are a synthetic placeholder (`get_benchmarks` reports `synthetic: true`) and are not cited.
- Programme costs and pilot results would raise confidence for opportunities 1, 3 and 4.

### 7. Recommended next actions (each requires approval)
- Approve the retention and customer-success workstream (opportunities 1, 2 and 4), owned by the VP Customer Success. Its KPIs are segment GRR and involuntary churn share. *Requires approval.*
- Approve a tier-1 support deflection pilot, owned by the COO, subject to HR/legal review of headcount implications. *Requires approval.*
- Ask management for one-time and run costs for each programme, then re-size. *Requires approval to share cost data.*

### 8. Open questions for management
- Is there a current onboarding programme for SMB, and what does it cost per customer?
- Which payment processor handles renewals, and does it support automatic card updates?
- Are the sales-entered churn reason codes reviewed by customer success?
- What tier-1 support headcount changes, if any, would management accept?

## Contract check
| Output contract item | Met |
|---|---|
| 1. Summary, at most 5 bullets, totals only as tool sums | Yes |
| 2. Findings table (id, statement, confidence, evidence) | Yes |
| 3. Opportunities table with tool-output low/base/high, one-time cost, confidence, rank | Yes |
| 4. Assumptions, one line per scenario assumption with its source | Yes |
| 5. Risks and counterarguments, including any disagreement with the ranking | Yes |
| 6. Data gaps | Yes (none blocking) |
| 7. Next actions marked *requires approval* | Yes |
| 8. Open questions | Yes |
| Every number traceable to a tool result | Yes. The figures are from `compute_saas_metrics`, `compute_retention_cohorts`, `get_churn_summary`, `price_waterfall`, `get_support_metrics`, `size_value_case`, `prioritize_opportunities` and `draft_100_day_plan`. |
| Run ends with `request_approval`; no approval by the model | Yes |

## Tool-call transcript

Read-only pass:

1. `read project://policies`  → ok
2. `get_company_profile` {"company_id": "cedar-churn"} → ok
3. `read company://cedar-churn/data-inventory`  → ok
4. `check_data_sufficiency` {"company_id": "cedar-churn", "analysis": "unit_economics"} → ok
5. `check_data_sufficiency` {"company_id": "cedar-churn", "analysis": "pricing"} → ok
6. `check_data_sufficiency` {"company_id": "cedar-churn", "analysis": "retention"} → ok
7. `check_data_sufficiency` {"company_id": "cedar-churn", "analysis": "ai_opportunity"} → ok
8. `compute_saas_metrics` {"company_id": "cedar-churn"} → ok
9. `compute_retention_cohorts` {"company_id": "cedar-churn"} → ok
10. `get_churn_summary` {"company_id": "cedar-churn"} → ok
11. `price_waterfall` {"company_id": "cedar-churn"} → ok
12. `get_support_metrics` {"company_id": "cedar-churn"} → ok
13. `get_usage_metrics` {"company_id": "cedar-churn"} → ok
14. `get_benchmarks` {"metric": "grr", "peer_set": "b2b_saas_10_50m_arr"} → ok

Interactive run (after the fix):

1. `start_diagnostic_run` {"company_id": "cedar-churn", "mode": "interactive"} → ok
2. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "value_claim", "title": "GRR below policy floor", "confidence": "high", "evidence_ids": ["... → ok
3. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "observation", "title": "SMB retention gap", "confidence": "high", "evidence_ids": ["87ee7... → ok
4. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "hypothesis", "title": "Onboarding and product gaps drive voluntary churn", "confidence": ... → ok
5. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "observation", "title": "Involuntary churn above policy", "confidence": "high", "evidence_... → ok
6. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "observation", "title": "Pricing is not a lever here", "confidence": "high", "evidence_ids... → ok
7. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "hypothesis", "title": "Weak sales efficiency is a churn symptom", "confidence": "medium",... → ok
8. `propose_opportunity` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "lever": "retention", "baseline_metric": "addressable_churned_arr", "title": "SMB onboarding and adoption ... → ok
9. `propose_opportunity` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "lever": "retention", "baseline_metric": "addressable_churned_arr", "title": "Mid-market health scoring an... → ok
10. `propose_opportunity` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "lever": "retention", "baseline_metric": "failed_payment_churned_arr", "title": "Failed-payment recovery (... → ok
11. `propose_opportunity` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "lever": "ai_automation", "baseline_metric": "support_cost_tier1", "title": "Tier-1 support deflection wit... → ok
12. `size_value_case` {"company_id": "cedar-churn", "opportunity_id": "993b4617-0617-4ab4-bd94-a88e136a459a"} → ok
13. `list_evidence` {"company_id": "cedar-churn", "opportunity_id": "993b4617-0617-4ab4-bd94-a88e136a459a"} → ok
14. `size_value_case` {"company_id": "cedar-churn", "opportunity_id": "abcad5b3-486a-454c-9a67-8571c80043c0"} → ok
15. `list_evidence` {"company_id": "cedar-churn", "opportunity_id": "abcad5b3-486a-454c-9a67-8571c80043c0"} → ok
16. `size_value_case` {"company_id": "cedar-churn", "opportunity_id": "b81d785a-528d-418a-bdf1-f6f0b63281fd"} → ok
17. `list_evidence` {"company_id": "cedar-churn", "opportunity_id": "b81d785a-528d-418a-bdf1-f6f0b63281fd"} → ok
18. `size_value_case` {"company_id": "cedar-churn", "opportunity_id": "6effbe48-945e-49e6-ad27-256bbc7146da"} → ok
19. `list_evidence` {"company_id": "cedar-churn", "opportunity_id": "6effbe48-945e-49e6-ad27-256bbc7146da"} → ok
20. `prioritize_opportunities` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169"} → ok
21. `draft_100_day_plan` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169"} → ok
22. `request_approval` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169"} → ok
23. `get_run_status` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169"} → ok
24. `record_finding` {"run_id": "c926db0e-3ca5-4e14-a746-f778eb80e169", "finding_type": "observation", "title": "late", "confidence": "low", "evidence_ids": []} → refused: Run c926db0e-3ca5-4e14-a746-f778eb80e169 is awaiting_approval and can no longer be changed
