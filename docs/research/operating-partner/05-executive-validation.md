# Executive decision quality, validation and portfolio narrative

Research date: 2026-09-27. This is a proposed roadmap, based on the implemented executive views, research renderer, acceptance records and the supplied operating-partner assessment. It introduces no claims of company participation, actual operating performance, external finance sign-off or completed human client acceptance.

## Recommendation

Build one decision-useful Progress Software case using independently sourced public facts and an explicitly constructed operating scenario. Preserve the existing visual system. Invest the next increment in a clear thesis, rejected or deferred alternatives, traceable assumptions, separate financial bridges and a demonstrable change of decision when evidence changes.

Use two connected reading levels: a two-page IC/operating-review memo for PE executives, and an inspectable appendix for technical reviewers. The public case must reproduce from permitted public inputs without LSEG/WRDS credentials. The private licensed research case can inform investigation, but its rows, charts and derived extracts do not automatically become public artifacts. Apache-2.0 licensing of the code does not establish redistribution rights for vendor data.

The supplied assessment is directionally useful but its sample figures, suggested peer gaps and example opportunities are not project findings. Nor should its suggested number of accepted/rejected initiatives become a quota: the case must show judgment, including a genuine negative result where supported, without manufacturing conclusions.

## Implemented capabilities and remaining gaps

Paths are relative to the repository root. Function names identify the inspected implementation.

| Area | Implemented evidence | Remaining decision-quality gap |
|---|---|---|
| Executive workspace | `src/pe_value_os/api/portfolio_views.py`, `home_page`: current assessments, decision needs, scoped company cards | Needs a case thesis and portfolio-level distinction between evidence-supported opportunity and constructed scenario; additional dashboard decoration adds little. |
| Review memo | `api/review_views.py`, `review_page`, `_workstream`, `_case`: annual/in-year amounts, contribution bars, owners, milestone disclosures, low/base/high, costs, input rates and evidence links | Contribution bars sum independent cases and explicitly warn about overlap. They are not an interaction-adjusted bridge from current EBITDA to a resulting EBITDA level. Top-line confidence is not a calibrated expected-value estimate. |
| Approval controls | `api/review_views.py`, `_decision`; `approvals.py`, `apply_edits`: approve, changes requested, reject, rationale, scoped exclusions, decision receipt and recomputed totals | Needs specific requests with resource commitment, prerequisites, stop conditions and version-linked outcome. Simulated decisions must be separate from real authorized human records. |
| KPI monitoring | `api/review_views.py`, `_kpi_card`, `kpi_page`; `domain/kpi_models.py`: baseline, target, observations, variance, source evidence and run linkage | An on-track KPI is not accounting realization or causal attribution. Need reconciliation from operational movement to recorded earnings/cash, with unexplained variance visible. |
| Public-company research | `research/render.py`, `render_report`: baseline cards, peer context, annual/quarterly history, source reconciliations, basis-point sensitivities and diligence agenda | Current readout is generic and cautiously unsized. It lacks a company-specific decision thesis, explicit disconfirming evidence, scenario mechanisms, cash schedule, interaction-adjusted bridge and executable management plan. |
| Reproducible evidence | `research/pilot.py`, `select_statements`, `analyze`; `tests/test_research_pilot.py`: source hashes, coherent revisions, missingness, currency/period eligibility and private output restrictions | Hashes establish input identity, not truth or actionability. Public issuer sourcing and assumption lineage need a separate permitted-input route. |
| Showcase verification | `tests/test_executive_ui.py`, `tests/test_portfolio_integration.py`, `scripts/check_portfolio_browser.py`, `docs/portfolio/acceptance.md` | Automated functional/browser evidence exists. It is not user usability acceptance, practitioner agreement or company validation. Claude Code connectivity does not prove an actual human walkthrough occurred. |
| Public narrative | `docs/portfolio/case-study.md`, `demo-report.md`, examples and captured screenshots | Existing Beacon narrative correctly says synthetic. Extend it with public-fact/constructed-scenario separation rather than relabeling synthetic outputs as Progress operating evidence. |

The present research renderer's hard-coded pending-human language should eventually be driven by explicit review state, while retaining the historical acceptance record. User delegation of design choices can authorize us to proceed; it cannot be converted into a fabricated client session or financial attestation.

## Decision memo specification

These layout and content requirements are project recommendations, not an industry-mandated template. ILPA provides a useful reference for consistent company-level reporting; its 2019 template remains a named reference, and ILPA has announced a refresh. Do not claim conformance to a new template without examining the released specification. [ILPA 2019 portfolio company template](https://ilpa.org/resources-tools/resource-library/2019-ilpa-portfolio-company-metrics-template/), [ILPA refresh announcement](https://ilpa.org/news/portfolio-company-metrics-template-refresh/).

### Page 1: the decision

1. **Context strip:** company, case mode, source cutoff, accounting period, currency/unit, memo version and author/reviewer status. Prominent labels distinguish reported facts, licensed-private analysis and constructed operating scenario. Progress is the case subject, not a represented client or investment holding.
2. **Thesis in three sentences:** what the public record establishes; what operating mechanism might explain or change performance; what remains unproven. Include the strongest counterargument. Unsupported operating detail remains a question, not narrative fact.
3. **Baseline strip:** revenue, defined earnings measure, growth and available leverage context. Each figure carries period and source reference. Show unavailable inputs explicitly. Standardized operating income must never receive an EBITDA label.
4. **Value view:** present interaction-adjusted scenario run-rate, cumulative day-100 and year-one effect, plus implementation cash requirement. State the case basis beside the amounts. Display an expected-value total only if probabilities, dependencies and scenario aggregation have explicit defensible definitions; otherwise use downside/base/upside assumptions.
5. **Selected actions:** at most three initial priorities, each with accountable role, evidence basis, next milestone and decision. A data-enabling activity can be selected without fabricated EBITDA. Separate selected, deferred, rejected and unsized items.
6. **Decisions due:** a small table of requested action, authority, resources/capacity, prerequisites, deadline, reversal/stop condition and next review. Example: authorize a bounded constructed experiment in the showcase; request a real contract sample only in a future permissioned pilot.
7. **Two or three material risks:** describe their mechanism and effect on the recommendation. Avoid generic risk lists that do not change an action.

### Page 2: the case against the recommendation

Show three distinct financial exhibits, the two assumptions most likely to reverse the selection, rejected/deferred alternatives and the first 30/60/100-day decisions. Explain what new evidence would invalidate each selected thesis. A reviewer should be able to argue against the recommended action from this page alone.

### Appendix: verification without clutter

Provide evidence locators, source class, accounting reconciliations, peer inclusion/exclusion rules, assumption register, scenario formulas, interaction ledger, full monthly schedules, capacity/dependency conflicts, decision history and reproduction command. Preserve the same calculation/version IDs across web view, JSON and any rendered PDF. Do not add a second manual spreadsheet calculation path merely for presentation.

## Chart and sensitivity semantics

The SEC's non-GAAP interpretations emphasize clear labels, consistent adjustments and reconciliation; they specifically warn about excluding normal recurring operating costs. Use these as financial presentation discipline here, not as a claim that this personal project has received regulatory review. EBITDA reconciles to net income under the cited interpretation; operating income and adjusted measures require accurate distinct names. [SEC non-GAAP interpretations, questions 100.01–100.05 and 103.01–103.02](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures).

| Exhibit | Required semantics | Reject |
|---|---|---|
| Annual earnings bridge | Defined baseline; incremental initiative effects; leakage/shared-cost/overlap adjustments; resulting earnings. Steady-state and year-one views are separate. Every step reconciles to the same underlying model. | A baseline-free contribution bar called a waterfall; unadjusted overlaps; recurring fees omitted; working capital inserted as EBITDA. |
| Cash bridge | Explicit horizon; incremental operating cash effects, collections/payment timing, implementation cash, capex and working-capital movement under a stated convention. Explain omitted taxes/financing if presenting only a partial incremental cash view. | EBITDA labeled cash flow; repeating a one-time working-capital release annually; subtracting the same implementation cash twice. |
| Valuation sensitivity | Modeled earnings metric and year, assumed multiple, clearly labeled hypothetical EV range. Any equity-value extension separately reconciles net debt and other relevant claims at the same date. | Modeled EV called proceeds or realized return; unsupported current multiple; automatic multiple expansion from operational improvements. |
| Assumption sensitivity | Two-driver matrix or tornado based on economically meaningful bounds; fixed reference case; units and dependent assumptions visible; timing scenario changes in-period value. Show break-even only when a valid schedule supports it. | Arbitrary plus/minus percentages presented as calibrated confidence; adding alternative scenarios; constant-churn pricing scenarios when the case explicitly assumes a price/churn interaction. |
| Realization reconciliation | Approved case versus revised case versus observed operating change versus supported financial attribution, for the same period and perimeter. Show remaining unexplained variance. | A KPI target achievement promoted directly to realized EBITDA; simulated accounting observations described as actual company results. |

A sensitivity should answer a decision, such as whether a delayed launch still warrants scarce management capacity. Low/base/high alone does not show which assumption drives the conclusion. Show the assumption value at which the decision changes, if one exists within the tested domain; otherwise report that no reversal was found in that domain.

Use restrained SVG or existing HTML components. Negative values must extend on the correct side of a labeled zero reference; use direct labels and signs, not color alone. Include a nearby explanation and an accessible data table; interactive states must remain understandable in printed/static output. W3C recommends both short identification and a detailed equivalent for complex images. [W3C complex image guidance](https://www.w3.org/WAI/tutorials/images/complex/).

## Challenge protocol

Codex prepares and runs a scripted challenge pack against the public baseline plus constructed operating scenario. Record inputs, expected decision implications, actual result and unresolved judgment. Test independent expected examples, not a copy of the production formula.

| Challenge | Expected behavior |
|---|---|
| “The peer margin difference reflects acquisition amortization and product mix.” | Show definition/perimeter bridge; revise or withhold the comparison; remove unsupported addressable-gap claims. |
| “The customer is not eligible for repricing during the modeled year.” | Eligibility and timing reduce the reachable population and in-year value; immutable prior case remains inspectable. |
| “Price increases worsen renewal retention.” | Show the coupled downside mechanism and decision threshold rather than adding separate optimistic pricing and retention benefits. |
| “Both initiatives claim savings from the same employees.” | Surface shared population and action conflict; adjust combined value or prevent simultaneous inclusion. Hours freed alone do not prove cost removed. |
| “The CFO has capacity for only one major workstream.” | Re-sequence or defer, explain the constraint and recompute timing/value from the shared engine. |
| “The API labels an assumed vendor value as a reported fact.” | Reject the source-class promotion; maintain evidence provenance through memo and exports. |
| “KPI improved, but total EBITDA fell.” | Separate business volume/mix, external changes, initiative contribution and unexplained variance; avoid false causal certainty. |
| “Collections improve by 10 days.” | Show a working-capital/cash effect under explicit assumptions; no automatic EBITDA or perpetually recurring benefit. |
| “An executive rejects the highest-dollar hypothesis.” | Preserve reason, evidence, version and decision rights; do not overwrite the original model or silently restore the rejected item. |
| “A peer or source period is removed.” | Recompute eligible sample and median; withhold insufficient comparisons; retain sensitivity of the thesis to selection. |

Optional practitioner review is a 30–45-minute session: five minutes of silent memo reading, ten minutes explaining the recommendation and its strongest objection, fifteen minutes challenging two assumptions, then scoring and recorded disagreement. Codex produces the packet, prompts and response log. A real reviewer supplies their own views and identity/role with consent; Codex must not impersonate that person. Without a reviewer, label the result **internal challenge completed; external review not performed**. This does not block completion of an explicitly simulated portfolio case.

## Acceptance rubric

The following thresholds are proposed project release criteria, not empirically validated industry standards. Score each dimension 0–4: 0 absent; 1 mostly assertion; 2 partial and materially incomplete; 3 complete, reproducible and decision-useful; 4 additionally withstands documented challenge with meaningful limitation handling.

| Dimension | Weight | Evidence for a score of at least 3 |
|---|---:|---|
| Source truth and provenance | 20 | Every material claim has origin, period, unit, locator and classification; constructed and licensed inputs remain distinguishable. |
| Financial coherence | 25 | Baseline and three financial views reconcile; costs, timing and interactions accounted for; unexplained amounts visible. |
| Commercial judgment | 20 | Clear mechanism and falsifier, plausible alternative explanation, supported disposition of alternatives and no automatic benchmark-to-savings leap. |
| Executability | 15 | Accountable roles, constrained capacity, dependencies, dated milestones, explicit decisions and stop conditions. |
| Executive comprehension | 10 | First page answers what to decide, why, value basis, main risk and next action; drill-down supports rather than contradicts it. |
| Technical reproducibility | 10 | Clean permitted-input replay, consistent version IDs, meaningful challenge evidence and exports matching the computation. |

Calculate `sum(weight × score / 4)`. Proposed release threshold: **at least 80/100, every dimension at least 3, and zero hard failures**. Record who scored and whether they were internal, automated or external. Automated tests cannot award a human comprehension score; Codex can provide a clearly labeled internal assessment, with observed human comprehension unassessed until a real session occurs.

Hard failures override the weighted result:

- Invented company operating data, approval, reviewer endorsement or actual client use presented as real.
- Licensed inputs or derived artifacts entering a public bundle without applicable permission.
- A headline amount cannot be reproduced or does not reconcile within declared display rounding; mismatched period/currency/perimeter silently combined.
- EBITDA, working-capital cash, EV and realized proceeds mixed or mislabeled.
- Double-counted benefits or costs knowingly left in an approved aggregate without a quantified reconciliation or blocking status.
- Ordinal confidence presented as a calibrated probability, or hypothetical upside presented as achieved value.
- A failed source, contradictory evidence or required approval bypassed to preserve a favorable result.
- An assumed operator/capacity allocation presented as a management commitment.

Keep three completion claims separate: **simulated-case release**, **practitioner-reviewed analysis**, and **permissioned operating pilot with measured outcomes**. The first is achievable under current authorization. The latter two require actual external evidence, not more polished language.

## Prioritized implementation tickets

All implementation and artifact preparation is owned by Codex. Estimates are focused engineering days for this workstream; dependencies overlap with the other four tracks and must be deduplicated in the combined roadmap.

| Ticket | Priority / effort | Dependencies | Deliverable and acceptance |
|---|---|---|---|
| EV-01: memo and claim contracts | P0 / 1–1.5 days | Commercial track source/thesis contract; finance baseline conventions | Typed memo sections and claim register with source class, version, explicit recommendation, counterargument and decision request. Existing synthetic case remains labeled; unsupported fields render unavailable. |
| EV-02: three financial exhibits | P0 / 2–3 days | Finance monthly schedule, interaction/cost model and valuation contract | Extend current memo with earnings/cash/EV exhibits and accessible tables from shared calculation output. Negative, zero, partial-data and excluded-initiative cases reconcile; no mixed-unit totals. |
| EV-03: decision-sensitive assumptions | P1 / 1.5–2.5 days | EV-01/02; commercial falsifiers; finance sensitivity function | Two-driver matrix/tornado, timing case and reversal explanation. Scenario changes preserve assumptions/version and update all dependent views consistently. No uncalibrated expected-value headline. |
| EV-04: constrained execution and decision brief | P1 / 1–2 days | Operating track capacity/schedule and lifecycle decision IDs | Two-page memo with selected/deferred/rejected/unsized items, specific asks and 30/60/100 milestones. Removing a prerequisite shows the dependent blocker and revised timing. |
| EV-05: skeptical review and rubric | P1 / 1.5–2 days | EV-02–04; realization contract from lifecycle/finance tracks | Challenge pack, internal scorecard, discrepancy log and fixes. All hard failures resolved; thresholds met with reviewer type clearly stated. Existing human records preserved. |
| EV-06: public technical proof and narrative | P1 / 1–1.5 days | Public-data route from commercial track; EV-05 | Reproducible public case, current screenshots, short walkthrough, claim-to-artifact map and updated case study/resume text. Public bundle contains no licensed extracts and replays without vendor credentials. Claims refer to verified build artifacts. |
| EV-07: optional external calibration | Later / 0.5–1 engineering day plus reviewer availability | EV-05 packet; willing authorized reviewer | Codex organizes supplied feedback into a response log and revises the case; real reviewer supplies assessment. No outside contact without explicit authorization. Not a simulated-case release blocker. |

This is **8–12.5 focused engineering days for EV-01–06**, excluding upstream financial/data/scheduling implementation and external waiting time. EV-01 can begin immediately; EV-02 depends on financial outputs rather than placeholder chart numbers. Avoid adding these days mechanically to overlapping integration estimates in other tracks.

## Ownership and portfolio framing

Codex owns research, lawful public sourcing, proposed assumptions, source reconciliation, implementation, charts, scenario generation, tests, internal challenge, release verification, documentation and interview materials. Use Progress as the default case and Claude Code as the preferred client under the user's delegated choices. No further aesthetic questionnaire or Docker decision is necessary.

Nondelegable user actions arise only when applicable: personally sign in to licensed services; supply a genuine company introduction or contextual facts if pursuing an operating pilot; authorize a specific external communication; confirm real management commitments; or provide an actual personal usability assessment. A practitioner must supply their own judgment. None of those should be fabricated to close a software milestone.

An honest current resume formulation is:

> Built a PE value-creation research and review platform with deterministic scenario sizing, evidence lineage, human approval controls and KPI monitoring; added private public-company financial research with source reconciliation and reproducible validation.

After the proposed case is actually completed:

> Developed a reproducible Progress Software diligence case using public filings and explicitly constructed operating schedules; linked commercial hypotheses to earnings, cash and valuation scenarios, constrained 100-day sequencing, and documented rejection/defer decisions under sensitivity analysis.

Use verified counts only when supported by a release-specific report. Do not claim money saved, actual portfolio deployment, real customer/contracts analyzed, independently validated investment recommendations, or realized investment returns. A compelling interview demonstration is to explain what the evidence supports, challenge an assumption, show the resulting changed decision and identify what a real CFO would need to verify next.
