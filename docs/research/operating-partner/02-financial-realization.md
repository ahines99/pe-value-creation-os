# Financial rigor and realization: operating-partner roadmap

Research date: 2026-09-27. Code reviewed: `8a6a540706110fa6e17137680921730df04c15a1`. This is a proposed implementation roadmap, not completed functionality or financial attestation. Progress Software is the recommended first research case; no licensed company figures or private operating records are reproduced here.

## Recommendation

Extend the existing deterministic engine into a reviewable monthly financial model for three selected initiatives. First establish a defensible baseline, operating assumptions, interactions and cost schedules. Then show separate EBITDA, cash and valuation views. Demonstrate the realization workflow with explicitly constructed observations until permissioned operating and accounting records exist.

The portfolio claim should be: **a reproducible underwriting and operating-review system with evidence-linked assumptions, explicit downside and an auditable realization method**. Public-company margins identify diligence questions; they do not prove avoidable cost or executable savings. A constructed operating schedule illustrates the method and cannot become a claim about Progress's actual contracts, staffing or performance.

## What already exists

Paths below are relative to the repository root; symbols identify the reviewed implementation.

| Capability | Evidence in code | Practical boundary |
|---|---|---|
| Decimal low/base/high sizing | `src/pe_value_os/domain/services.py:13`, `_scenario_ebitda`; `domain/project_models.py:25`, `ScenarioInputs`; `tests/test_sizing.py` | Baseline × improvement × captured share × flow-through − recurring annual cost. Captured share is not a probability of success. |
| Baselines and flow-through derived on the server | `domain/baselines.py`, `derive_baseline`; `domain/project_models.py:34`, `OpportunityProposal` | Proposer cannot supply arbitrary baseline value or flow-through. Assumptions remain mostly free text and policy defaults. |
| One-time cost and EV sensitivity | `domain/project_models.py:91`, `ValueCase`; `domain/services.py:22`, `size_value_case` | One-time cost is reported separately. Optional base EBITDA × supplied multiple exists already; no need to introduce this as a wholly new feature. |
| Input fingerprints and calculation version | `domain/services.py:18`, `inputs_hash`; `CALC_VERSION` | Fingerprint covers the opportunity, but excludes the separately supplied EV multiple. Valuation-input provenance needs extension. |
| Start and linear ramp; annual and in-year totals | `domain/prioritization.py:28`, `in_year_factor`; `:38`, `phase` | Lever-level timing multiplies net annual benefit by one factor. It cannot represent software fees starting before benefits, staggered contracts, upfront expense, capex or cash collection timing. |
| Weighted prioritization | `domain/prioritization.py:44`, `prioritize` | Weights EBITDA, ordinal confidence, timing and one-time cost. Confidence scores of 0.3333/0.6667/1 are ranking inputs, not calibrated probabilities. |
| Some double-counting protection | `domain/baselines.py:499`, `baseline_overlap`; `workflows/steps.py`, `evidence_review`; `llm/validation.py` | Rejects identical/nested baselines and incompatible scopes. Different pricing baselines can still overlap; this is warned about, and UI totals explicitly remain independent sums. |
| Approved scope recalculation | `src/pe_value_os/approvals.py:57`, `apply_edits` | Removing initiatives recomputes annual/in-year totals, but currently has no shared-cost or interaction model to recompute. |
| Measured KPI monitoring | `workflows/planning.py:152`, `_kpi`; `kpi.py`, `activate_plan`, `refresh_company`, `target_on`; `domain/kpi_models.py` | Approved baselines, targets, observations, evidence and deterministic variance alerts exist. KPI observations do not constitute accounting realization or causal attribution. |
| Operating ratios | `domain/metrics.py`, `compute_saas_metrics` | ARR/retention, CAC payback, LTV/CAC, margin and Rule of 40 variants exist. Burn multiple explicitly uses a negative-EBITDA proxy; do not relabel it cash burn. |
| Private public-company research | `research/models.py`, `Statement`, `Reconciliation`; `research/pilot.py`, `select_statements`, `metrics`, `analyze`; `tests/test_research_pilot.py` | Currency/period/vintage checks, whole-row revisions, peer medians, source bridges and illustrative basis-point sensitivities exist. Standardized operating income is not EBITDA; SG&A can include R&D. Research does not create operational approvals. |

One concrete wording defect belongs in the first change: `workflows/steps.py:453` and `tools/value_tools.py:314` call a nonpositive annual contribution “does not pay back.” Annual contribution alone is not a payback calculation. Use “nonpositive modeled annual contribution” until a cumulative cash schedule establishes payback.

## Correct the assessment before adopting its specification

1. **Use three bridges, not one mixed waterfall.** An EBITDA bridge contains operating earnings effects. Working-capital release, capex, financing and equity distributions belong elsewhere. Implementation expense can reduce in-period EBITDA; capitalized implementation spend affects cash and later depreciation/amortization. A steady-state view may exclude genuinely temporary costs only with a separately identified reconciliation.
2. **Separate rate, probability and confidence.** The existing realization rate is the share of a technical improvement captured. It must not silently become the probability of the initiative succeeding. Evidence strength and uncertainty are separate fields. Do not multiply the same risk haircut twice.
3. **Replace the proposed automatic stage chain.** Workflow status can be `hypothesis → sized → approved → executing → closed`, with rejected/paused/cancelled outcomes. Measurement is a parallel ledger: KPI observed, financial impact estimated, finance-validated period contribution, cash collected/paid, sustained run-rate assessment. None follows automatically from approval or a green KPI.
4. **Remove “EV realized” from initiative completion.** A multiple-based EV sensitivity remains modeled. Actual sale consideration, fees, debt repayment, retained interests and distributions require transaction evidence. A valuation mark is also distinct from cash proceeds.
5. **Do not add identified, approved, run-rate and realized dollars.** They are different views of the same opportunity. Every column needs period, scope and gross/net basis; an annual run-rate cannot be compared with three-month cumulative realization without an explicit period bridge.

Accounting reference: the SEC distinguishes EBITDA from differently adjusted measures and calls for reconciliation to net income when EBITDA is used as a performance measure. Its free-cash-flow guidance requires a definition and cautions that the measure is not automatically discretionary cash. We adopt those presentation disciplines; this portfolio project is not representing itself as an issuer filing. [SEC non-GAAP interpretations, questions 100.01, 102.07, 103.01–103.02](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures).

## Proposed model specification

### 1. Baseline and assumption contracts

Create an immutable `BaselineSnapshot` with entity, legal/consolidation perimeter, currency, unit, monthly calendar, fiscal calendar, accounting basis, source IDs/hashes, known-at timestamp, source vintage, approved-by record if any, and a reconciliation to reported financials. An underwriting snapshot and close snapshot are different versions. Reforecasting must preserve both; a correction produces a restatement record and a reason.

Each numeric `Assumption` needs a stable ID, value/unit, effective dates, source locator, source classification, rationale, downside/base/upside values, owner, status, and affected formulas. Suggested classifications: reported fact, permissioned operating fact, management representation, external benchmark, analyst assumption, constructed scenario. A citation to an entire data file is insufficient for a material assumption: identify its rows, field or transformation.

Define reported EBITDA, any adjusted EBITDA, and the analyst's maintainable-earnings view separately. Reconcile additions and deductions individually; do not assume every restructuring, acquisition or stock-compensation adjustment is economically avoidable. For Progress, complete a reported-to-standardized-to-model bridge before applying an EBITDA multiple. Do not add R&D to a standardized SG&A series that already contains it.

### 2. Monthly operating and financial schedules

Use 24 monthly periods initially, with day-100 cumulative results derived from the same dates and an explicit within-month convention. Permit scheduled renewals rather than forcing every pricing action into a linear ramp. Separate implementation start, customer eligibility, adoption, recognition, billing, collection and recurring-cost start.

For initiative `i` in month `t`, calculate incremental P&L against the locked counterfactual:

```text
delta_revenue[i,t] = modeled recognized revenue − counterfactual recognized revenue
delta_recurring_contribution[i,t]
    = delta_revenue − delta_COGS − delta_recurring_operating_expense
delta_in_period_EBITDA[i,t]
    = delta_recurring_contribution − expensed_implementation_cost
```

The first iteration can use explicit marginal-cost rates where transactions are unavailable, with those rates clearly assumed. It must preserve gross benefit, leakage, variable cost, fixed-cost action, ongoing fees and implementation expense as separate lines. The generic baseline-rate engine remains a supported screening calculation, not the final underwriting bridge.

| Initiative | Required driver bridge | Main disconfirming evidence |
|---|---|---|
| Pricing | Eligible renewals × contractual increase × adoption; net price after concessions; retained units; recognized revenue; incremental servicing/selling cost | Notice periods, price caps, observed churn/downsells, committed rebates or product-mix change |
| Retention | Defined opening cohort × prevented churn/downgrade × retained revenue timing × marginal contribution, less intervention expense | Cohort mismatch, natural recovery, renewal timing or retained revenue already counted in pricing |
| Support automation | Eligible contacts × automation coverage × successful resolution × net minutes avoided; expense removed or documented hiring avoided; ongoing model/vendor/QA cost | Recontacts, lower CSAT, agent work shifted rather than removed, no staffing or vendor-spend action |
| Procurement/cloud | Units × contracted rate change plus separately identified usage change; migration/termination expense and service risk | Minimum commitments, exit penalties, usage growth, costs moved to another account |
| Sales efficiency | Separate lower acquisition expense from higher conversion/output; show bookings → ARR → revenue timing and delivery costs | Headcount unchanged, demand deterioration, acquired revenue or sales-cycle lag |

Hours freed are capacity, not automatically EBITDA. Record redeployment, overtime removal, contractor reduction, attrition/backfill avoidance and headcount action separately. An assumed avoided hire is a modeled counterfactual until documented. Public SG&A or peer productivity alone supplies none of these facts.

### 3. Cash, capital and financing

Provide a separate incremental cash schedule, defined in the product as a management model rather than asserted to be a statutory cash-flow statement:

```text
incremental_unlevered_cash
    = incremental_in_period_EBITDA
    + explicit_non_cash_operating_adjustments
    − incremental_cash_operating_taxes
    − increase_in_operating_working_capital
    − capital_expenditure
```

Working capital must be defined by included accounts; exclude financing balances. Collection of existing receivables improves cash without creating new revenue. If implementation expense is already in EBITDA, deduct only its cash/accrual timing difference through the appropriate adjustment; do not deduct the same implementation amount again. Capitalized spend enters capex once. Track capex depreciation separately for EBIT/tax analysis, not as another EBITDA expense.

Show debt draws, amortization, interest, fees, minimum cash and cash sweeps in a distinct financing schedule when available. Do not infer financing from an operating multiple. A full lender covenant engine is outside the first showcase scope. If tax or working-capital inputs are unavailable, label the output “pre-tax operating cash proxy” and enumerate omissions instead of naming it free cash flow.

The operating/investing/financing separation and adjustment for accruals and non-cash items follow the cash-flow distinctions explained in [IFRS Foundation, IAS 7 overview](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/). The particular management-model equations above are proposed project design, not a claim of complete IFRS or US GAAP implementation.

### 4. Interactions and portfolio totals

Introduce a `BenefitPool` keyed by economic subject and time: customer-contract-period, employee/team-period, vendor-contract-period or account/cost-center-period. Record mutually exclusive alternatives, prerequisites, shared costs and explicit interactions. Distinct baseline names are not proof of distinct economic benefits.

For pricing plus retention, compute the combined cohort once. A price-volume interaction is a separate reconciled line or allocated by a declared deterministic rule. For support deflection plus workforce productivity, cap expense removal at supported spend and separate remaining capacity gains. Recompute shared costs if approval removes an initiative.

Report standalone gross opportunities alongside an interaction-adjusted selected plan. Do not present an executable total if material overlaps remain unresolved; show a subtotal for reconciled initiatives and mark the rest unaggregated. Allocation rules must preserve the combined result without implying scientific causal precision.

### 5. Uncertainty, sensitivities and modeled EV

Start with deterministic downside/base/upside cases, one-at-a-time sensitivities and a two-dimensional price-capture × churn view. Include delay, ongoing cost, implementation overrun and unit-margin sensitivities; show which assumptions change the decision. A scenario range is not a statistical confidence interval. Explain that one-at-a-time charts hold other inputs fixed and do not capture joint exposure.

Optional probability-weighted results should use explicit mutually exclusive joint states with probabilities summing to one. Label probabilities “analyst-assumed” unless supported by a documented historical calibration dataset, out-of-sample assessment and suitable outcome definition. Apply costs in failure/delay states as actually incurred; a success-probability haircut on net EBITDA is often wrong when setup cost is unavoidable. Capture correlated adoption or customer risks across initiatives; do not assume independence for convenience. Monte Carlo is deferred until distributions and dependencies can be justified.

Retain the existing constant-multiple sensitivity as `delta_EV = delta_maintainable_EBITDA × selected_multiple`. Version and hash the multiple, metric definition, date and source with the calculation. If presenting an exit bridge, distinguish operating earnings growth, multiple change and interaction:

```text
delta_EV = starting_multiple × delta_EBITDA
         + starting_EBITDA × delta_multiple
         + delta_EBITDA × delta_multiple
```

Do not allocate multiple expansion to an operational initiative without an explicit assumption. Equity proceeds additionally require debt, cash, other claims, fees, dilution and ownership allocation. An IPO valuation is not cash realized until an actual disposal/distribution occurs.

These valuation boundaries are supported by the [IPEV 2025 Guidelines](https://www.privateequityvaluation.com/Valuation-Guidelines), sections 2.4, 2.7 and 3.4: enterprise-to-investment allocation considers senior claims and dilution; multiples require metric comparability; backtesting compares estimates with liquidity-event evidence. This project's sensitivity is not an IPEV fair-value opinion.

### 6. Realization and attribution

Create a `RealizationEntry` with period, initiative, benefit pool, frozen baseline version, actual source records, recognition/collection status, calculation version, counterfactual method, adjustments, reviewer status and supersession link. Keep observed accounting performance, estimated attribution and independently reviewed attribution distinct.

A monthly bridge should reconcile locked baseline to actual EBITDA through business-as-usual volume/mix, FX, acquisitions/divestitures, initiatives, implementation expense and unexplained residual. The residual remains visible; never force all favorable variance into an initiative. Record the selected decomposition order, because price-volume interactions can change allocated components while the total stays fixed.

Prefer a feasible untreated cohort or staged rollout for the selected pricing/automation pilot. Where no credible comparator exists, describe the result as an estimated contribution with limitations. Finance review validates source reconciliation and accounting treatment; it does not by itself prove causality. Build the evaluation design before observing results. The [HM Treasury Magenta Book](https://www.gov.uk/government/publications/the-magenta-book/magenta-book-central-government-guidance-on-evaluation-html) distinguishes monitoring from impact evaluation and discusses counterfactual and theory-based approaches. Applying those evaluation principles to this private-equity workflow is our recommendation, not a PE-specific requirement from that source.

## Prioritized implementation tickets

Estimates are focused engineering days, including relevant tests and documentation, with data already available. They are planning ranges, not elapsed-calendar promises. Codex owns every implementation ticket, source mapping, draft accounting memo, constructed examples, tests and review packet. Alex need not build spreadsheets or write specifications. External finance review is reserved for independent attestation, not routine decisions or a prerequisite to building the showcase.

| Ticket | Priority / days | Dependencies | Deliverable and acceptance |
|---|---|---|---|
| FIN-01 Definitions and calculation provenance | P0 / 1–2 | None | Financial dictionary; distinguish captured share, probability, confidence, EBITDA/cash/run-rate; repair payback wording; version/hash EV inputs. Acceptance: two distinct multiples produce distinct valuation provenance while existing operating sizing remains reproducible. |
| FIN-02 Locked financial baseline | P0 / 2–3 | FIN-01; evidence workstream's source classifications | Baseline snapshot and adjustment register; preserve current/underwriting/close versions; reported-to-modeled bridge. Acceptance: no silent restatement, mixed currency/unit rejected, source changes create a new version, absent EBITDA cannot inherit an operating-margin label. |
| FIN-03 Typed assumptions and monthly schedules | P0 / 3–4 | FIN-02 | Three initiative templates; 24-month P&L schedules with independent benefit/cost timing; exact day-100 convention. Acceptance: trace any displayed amount to driver assumptions and dated sources; delayed benefit does not defer already committed costs. |
| FIN-04 Benefit pools and interactions | P0 / 2–3 | FIN-03 | Cohort/cost-pool relationships; mutually exclusive alternatives; shared-cost rules; reconciled aggregate. Acceptance: adding overlapping pricing/retention initiatives cannot double-count the same benefit; removing scope recomputes interactions and retained shared costs. |
| FIN-05 Cash and implementation bridge | P0 / 2–3 | FIN-03 | Separate working-capital, capex and expensed implementation schedules; cumulative cash/payback where defined. Acceptance: working-capital release has zero EBITDA effect; capex counted once; cash/proxy label reflects missing inputs; no “payback” label based on annual contribution alone. |
| FIN-06 Scenarios, sensitivities and valuation | P0 / 2–3 | FIN-04, FIN-05 | Downside/base/upside and driver sensitivity views; optional analyst-assumed joint states; maintainable-earnings × multiple matrix. Acceptance: all cases recompute full costs/interactions; no confidence score reused as probability; changing multiple changes EV but no operating/cash result. |
| FIN-07 Decision-ready financial packet | P0 / 1–2 | FIN-01–06; executive-output workstream | Separate EBITDA, cash and valuation bridges; definitions, assumptions, exclusions and falsification notes; one rejected/uneconomic case. Acceptance: selected totals reconcile and all constructed schedules are unmistakably labeled. Independent review may remain explicitly pending. |
| FIN-08 Realization ledger and variance bridge | P1 / 3–5 | FIN-02–05; lifecycle versioning contract | Append-only period entries, corrections, baseline-vs-actual reconciliation, visible residual and reviewer status. Acceptance: duplicate imports do not add value twice; corrections preserve history; KPI success alone cannot create finance-validated dollars. |
| FIN-09 Attribution demonstration and reviewer packet | P1 / 2–3 | FIN-08; permissioned data or labeled constructed example | Documented counterfactual/cohort design; adverse and ambiguous cases; accounting reconciliation and independent-review checklist. Acceptance: no identifiable comparator yields a qualified contribution estimate, not a causal savings claim; independent reviewer identity/date captured only after actual review. |
| FIN-10 Financing and exit evidence extension | P2 / 3–5 | FIN-05, FIN-08; actual financing/exit records | Simple debt/cash/proceeds bridge and event evidence, if useful for the selected case. Acceptance: modeled mark, transaction valuation and cash distributions cannot share a “realized” status; debt changes cannot increase EBITDA. |
| FIN-11 Empirical calibration | Deferred / 3–5 after suitable outcomes exist | FIN-08/09; sufficiently comparable completed initiatives | Outcome definitions, sample-bias notes, held-out calibration and monitoring. Acceptance: no “calibrated” probability without auditable cohort and validation; otherwise preserve analyst-assumed scenarios. |

FIN-01–07 are approximately **13–20 focused engineering days** for the financial showcase slice. FIN-08–09 add **5–8 days** for a meaningful realization-method demonstration. Other agents' UI, evidence and lifecycle work overlap these estimates and must be deduplicated in the integrated roadmap. A real outcome study takes the actual operating/financial reporting periods; software work cannot compress that evidence wait.

## Financial acceptance invariants

Use hand-worked golden cases and independent reconciliation checks rather than tests that repeat production formulas. Extend the existing sizing suite rather than creating a separate testing platform.

1. **Accounting separation:** reducing receivable collection days creates cash release, zero revenue and zero EBITDA; capex changes cash and the asset/depreciation schedule, not initial EBITDA.
2. **Time and scope:** monthly amounts sum to displayed period totals; no benefits before contractual eligibility; day-100 amounts use the same approved calendar. Annual run-rate and cumulative cash never share a total.
3. **Costs remain real:** zero adoption can produce negative net contribution; upfront fees survive delay/failure; expensed implementation is not subtracted twice in cash.
4. **Units:** Decimal arithmetic; explicit currency and units; percentages vs basis points validated; no combined currency total without a dated FX policy.
5. **Interactions:** a fixed cohort's combined result equals its component allocations plus explicit interaction/residual; overlapping pools cannot exceed supported revenue/spend removal; valid growth is represented explicitly rather than hidden inside a cap.
6. **Approval changes:** excluded initiatives produce no approved benefit; unavoidable shared costs remain; removed sole-use costs disappear according to the documented contract assumption.
7. **Uncertainty:** scenario probabilities sum to one; success/failure states include their respective costs; deterministic scenario labels do not imply calibrated odds. Higher benefit does not guarantee higher cash if it requires additional capex/WC.
8. **Valuation:** a multiple change cannot alter revenue, EBITDA, cash or KPI observations; maintainable-earnings definition is stable across compared multiples; EV sensitivity is never promoted to sale proceeds.
9. **History:** locked baseline hashes remain stable; revised actuals supersede rather than overwrite; duplicate transaction IDs cannot create additional contribution.
10. **Attribution:** unexplained favorable variance remains unassigned; transaction allocations conserve totals; a green KPI or approved plan creates no realization entry without source evidence.

## Deliberate limits

Do not build a full ERP, general ledger, universal LBO/covenant model, Monte Carlo platform or fund-return attribution engine for this milestone. Do not claim empirical probabilities from three illustrative cases. Do not add more synthetic companies to substitute for one carefully reconciled case. Keep generic UI/platform changes focused on exposing the financial reasoning already required above.

The complete showcase can include a constructed, clearly labeled realization demonstration while authentic Progress initiative realization remains unavailable. An independent reviewer can later attest to model reasoning and reconciliation; actual company impact additionally requires permissioned operating evidence and elapsed measurement periods.
