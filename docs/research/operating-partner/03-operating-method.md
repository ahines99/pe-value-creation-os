# Operating method: from ranked opportunities to an executable plan

Research and repository audit, 27 September 2026. This is a proposed implementation roadmap, not a claim that the features below exist or that Progress Software management has approved an operating plan. The user has delegated routine project choices to Codex. Estimates are focused engineering days, include relevant verification, and exclude waiting for external access or practitioner responses.

## Recommendation

Build one inspectable operating decision cycle: a reviewer compares the opportunity set, selects a limited first wave, sees why other work waits, assigns accountable owners, and reviews dated evidence at the next steering meeting. Prove that a capacity bottleneck or failed dependency changes the plan and its financial timing. Keep the existing deterministic calculations, evidence linkage and human approval boundary.

For the Progress case, use public reported facts as context and explicitly constructed operating schedules where private operating evidence is unavailable. Call the result a **research case with a simulated operating plan**. Do not represent fictional people, resource availability, customer contracts, approvals or outcomes as Progress facts. Financial opportunity amounts and management commitments remain hypothetical until supported by corresponding evidence.

## What is implemented, and what is actually missing

| Area | Verified implementation | Remaining gap and consequence |
|---|---|---|
| Prioritization | `src/pe_value_os/domain/prioritization.py::prioritize` uses policy weights for normalized base EBITDA, confidence, start month and one-time cost. Components are stored; ties break deterministically on opportunity ID. `tests/test_core_services.py` exercises ranking and weight changes. | The assessment's suggestion that ranking is only dollars is too strong. However, the score has no capacity, readiness, customer risk, reversibility or strategic-fit gate. Confidence maps to fixed fractions; these are ranking weights, not calibrated realization probabilities. Relative normalization means adding a candidate can change other scores. |
| Initiative classification | `domain/project_models.py::InitiativeClass` contains quick win, structural and enabler. `workflows/planning.py::classify` assigns quick win when the lever starts by month three, otherwise structural. | Enabler exists as an enum but the builder does not assign it. An early start does not establish low complexity, low risk or fast financial benefit. Foundational work can consume scarce capacity without having a directly sized EBITDA case. |
| Ownership | `workflows/planning.py::OWNER` assigns a workstream role, such as Chief Revenue Officer. | No separate executive sponsor, accountable operator, named assignee or explicit unassigned status. Pricing and sales efficiency can compete for the same executive without any warning. |
| 100-day planning | `build_plan` creates workstreams, KPI baselines and day-100/run-rate targets; milestone text is grouped under day 30, 60 and 100. It stores risks, dependency prose and governance cadence. | Milestones are generic strings, not dated deliverables with acceptance evidence, responsible owner, completion state and decision gates. Dependency prose cannot prevent an invalid launch. There is no supported resource-constrained start schedule. |
| Timing | `prioritization.py::phase` calculates in-year value from a lever's policy start month and ramp. `planning.py::day_100_fraction` approximates day 100 as 3.3 months. | Timing is lever-level, not initiative-specific or tied to completed prerequisites. Calendar milestones and value phasing can disagree. Delaying a contract review does not presently recalculate the initiative start through an execution model. |
| Human decisions | `approvals.py::decide` requires a human principal, company access, role and applicable scope/client restrictions. `apply_edits` removes initiatives and adjusts totals; exclusions and audit information exist. `tests/test_workflow.py`, `tests/test_workflow_remediation.py` cover approval/resumption and exclusions. | Approval is primarily a plan decision. There is no typed initiative selection rationale covering capacity/strategic trade-offs, decision owner, expiration/revisit date, or milestone-specific release decision. Keep the existing authority boundary when adding these. |
| Measurement | `kpi.py` activates approved KPIs, checks computable evidence-backed KPI coverage, recomputes due observations, compares period-aware targets and creates threshold/trend alerts. `domain/kpi_models.py` stores definitions, observations, alerts and notifications. `tests/test_ops.py`, `tests/test_audit_fixes.py` cover target behavior. | A KPI alert is not a steering action or realized EBITDA certification. Target paths are interpolated rather than derived from actual contractual events or an approved execution schedule. Need a dated response owner and disposition, not more alert channels. |
| Operating pilot | `docs/pilot/pilot-plan.md` describes a six-week permissioned company pilot and explicitly says it has not started. Approval activates monitoring; it does not act on company systems. | The private public-company research case does not satisfy the operating-company pilot. Keep its lighter research acceptance separate from staging/real-company deployment prerequisites. |

This audit inspected source and existing test definitions. It did not rerun the full suite or certify new execution behavior.

## Primary-source grounding

These are practitioner sources describing their own approach, not independent proof of a universal causal formula. The proposed field names, gates and capacity defaults below are our design judgments.

* Bain's *Global Private Equity Report 2015*, printed page 55, describes a management-and-sponsor value-creation plan focused on a small set of priorities, assigned accountability, implementation milestones, performance metrics and periodic refreshes. It supports selecting and resourcing a manageable plan rather than merely listing opportunities. Its historical return comparisons do not establish a causal performance promise for this application. [Bain report](https://media.bain.com/bainweb/PDFs/Bain_and_Company_Global_Private_Equity_Report_2015.pdf)
* McKinsey's 2019 practitioner article distinguishes quantified ambition from an actionable operating plan. It emphasizes granular milestones, clear responsibilities, resource allocation and implementation waves, while noting that financial evidence can lag implementation. This supports separate execution, KPI and financial-evidence states. [McKinsey, From pure investor to entrepreneurial owner](https://www.mckinsey.com/industries/private-capital/our-insights/from-pure-investor-to-entrepreneurial-owner-how-private-equity-firms-can-master-the-shift)
* Bain's November 2025 CEO guidance stresses aligning management and sponsor expectations through an actionable value-creation plan and transparent execution. It supports making disagreements and decisions explicit; it does not justify assuming the research case has management endorsement. [Bain, A Private Equity Fund Just Bought Your Company … Now What?](https://www.bain.com/insights/a-pe-fund-just-bought-your-company-now-what/)

## Minimum operating method

### 1. Establish eligibility before ranking

Every candidate receives a visible disposition: `ready_to_compare`, `needs_evidence`, `blocked`, `deferred`, `rejected` or `selected`. These are planning dispositions, separate from human approval and execution status. Evidence missingness is not a low numerical score that large modeled value can overcome.

The comparison gate asks whether the case has a supported baseline, an intervention explaining the driver change, a defined KPI, an explicit cost/timing basis, and a credible measurement path. A constructed case can pass for a simulation if every constructed input remains labeled; it cannot pass as validated company evidence. Unresolved legal, contractual or customer safety requirements block the affected launch step. A zero-value foundation can still be selected as a dependency with its own cost, owner and capacity demand.

### 2. Compare judgments without invented precision

Keep monetary ranges, cash requirements and timing as quantities with units. Use a short qualitative rubric for judgment fields, each with rationale, evidence IDs, author, timestamp and provenance:

| Judgment | Suggested choices | Interpretation |
|---|---|---|
| Evidence readiness | supported / partial / absent | Whether the intervention and baseline are evidenced; not a probability |
| Delivery complexity | contained / cross-functional / transformational | Number and criticality of operating changes, not an opaque number |
| Customer/operational exposure | low / material / high | Consequences of a failed implementation, with mitigating conditions |
| Reversibility | reversible / costly to reverse / effectively irreversible | Whether a pilot can stop without substantial damage |
| Strategic fit | direct / enabling / disputed | Relationship to the documented thesis |
| Capacity pressure | fits / conflict / unknown | Computed against declared resource availability; unknown stays visible |

Present the existing weighted score only as an optional baseline ordering, with its formula and caveat. Do not label it an objective best plan. Use a reviewer-authored ordered candidate list plus clear comparison reasons, such as “smaller modeled benefit, but contract evidence and owner capacity are available.” A dominated candidate may prompt a review, but dominance is never proof of rejection where strategic considerations differ.

Separate type from selection: quick win, foundation and strategic bet describe the work; selected/deferred/rejected describe a decision. A quick win should have explicit small scope, supported data, available operator capacity, manageable risk and a near-term measurable result. A start-month threshold alone is insufficient. Preserve disagreements and overrides with reasons; do not optimize for a particular override rate.

### 3. Make scarce management attention explicit

For the initial constructed case, assume at most **three concurrent major workstreams** and at most **one accountable major workstream per operator**. These are conservative demonstration defaults, not externally validated staffing benchmarks or Progress facts. Foundation work consumes capacity too.

Use weekly buckets of reserved change-work hours for scarce teams and operators, not a percentage of the entire employee workweek. A `CapacityBudget` identifies resource/role, week, available change hours, source and confirmation state. A `ResourceDemand` identifies initiative, resource, phase, week and hours. Unknown demand or availability means “capacity unverified,” not zero. Do not sum sponsor oversight and operator labor into an undifferentiated headcount quantity.

For the first release, the reviewer fixes the selection order. A deterministic greedy scheduler places each selected initiative at the earliest feasible week after its prerequisites and capacity constraints, using stable IDs for ties. It returns its assumptions and all blockers. A greedy result is a feasible proposal, not a mathematically optimal portfolio. Start with finish-to-start dependencies and calendar dates; complex lag/lead types can wait.

Keep a selected-but-unscheduled queue. If the horizon has no feasible slot, identify the constraining resource or unmet prerequisite. Adding capacity or changing priority creates a new proposal; it does not silently rewrite an approved baseline.

### 4. Convert promises into dated evidence and decisions

Use one accountable operator per initiative; a sponsor can cover several initiatives. For research, placeholders should say “Proposed operator: revenue operations lead; unconfirmed,” never imply an actual person accepted the work.

Each milestone contains a specific deliverable, acceptance criterion, due date, owner, predecessor IDs, evidence requirements, state and completion timestamp. Distinguish a completed task from an accepted deliverable. Proposed dates can exist before dependencies finish, but activation is blocked until required acceptance/decision records exist.

Add a `SteeringDecision` record with question, options, recommendation, decision owner, due date, affected initiative/version, evidence cutoff, chosen outcome, rationale and next review date. Authoring a recommendation is automated work; recording an actual operating approval requires the existing human boundary. Simulated decisions are explicitly marked and cannot appear in the actual approval history.

The steering packet should answer only: what changed, why it matters, what is blocked, who must act by when, and what the decision does to the financial forecast. Link deeper evidence. Existing weekly workstream, biweekly steering and monthly sponsor cadence are reasonable defaults; choose actual next dates instead of displaying cadence prose alone.

## Example 100-day case sequence

Use a configurable plan start date. The following worked calendar uses **5 October 2026 as day 0**, solely as a simulated kickoff. Day N means `start_date + N calendar days`; business-day adjustments must be explicit. It is not a promise about Progress activity or an engineering delivery schedule.

| Date / checkpoint | Proposed accountable role | Deliverable and acceptance | Decision / dependency |
|---|---|---|---|
| 5 Oct, day 0 | Research case lead; simulated CFO sponsor | Freeze public-financial baseline and label constructed schedules; log the underwriting hypothesis, exclusions and unresolved evidence. | Approve simulation scope only; no company intervention authorized. |
| 19 Oct, first steering | Proposed finance operations lead | Data dictionary and reconciliation exceptions; source and constructed inputs distinguishable at every drill-down. | Accept baseline for simulation or return it for correction. All financial conclusions inherit unresolved limitations. |
| 4 Nov, day 30 | Proposed revenue operations lead | Reconcile an illustrative renewal cohort, contract rights, notice dates and at-risk customer exclusions. Produce a pilot cohort and rollback/stop criteria. | Pricing pilot waits for contract evidence and risk review. Select a contained experiment, not an across-the-book change. |
| 18 Nov, steering | Proposed customer success lead | Pilot readiness and cohort exposure report; capacity conflicts resolved or escalation dated. | Proceed, defer or reject; preserve reason and the forecast/version affected. |
| 4 Dec, day 60 | Proposed revenue operations lead | First simulated pilot observation with denominator, measurement period, exclusions and comparison to baseline; separately list any lagged cash/financial evidence. | Continue or stop based on predeclared criteria. A KPI movement alone does not certify EBITDA. |
| 16 Dec, steering | Proposed finance lead | Refresh modeled timing and implementation-cost forecast; distinguish case simulation from observed company results. | Approve a revised simulation forecast while retaining the original baseline. |
| 13 Jan 2027, day 100 | Proposed operating sponsor | Decision memo: accepted deliverables, unresolved dependencies, KPI evidence, attribution limitations, next-phase budget/capacity request. | Scale, rework, defer or abandon each pilot; do not force a “success” outcome. |

A support-automation strategic bet can run only its evaluation-design foundation in the first wave if revenue operations or data engineering is already constrained. Customer-facing rollout remains dependent on a suitable evaluation set, measurable service-quality criteria, operator capacity and a rollback decision. Without actual ticket data, this stays a constructed demonstration. This illustrates disciplined sequencing without claiming that either intervention is warranted at Progress.

## Minimal contracts and integration

Extend the existing plan model rather than replace the workflow engine. Add structured records for:

1. `InitiativeExecution`: stable initiative ID, plan version, class, sponsor, accountable operator, assignment confirmation, disposition, proposed/committed dates, KPI and value-case references.
2. `Milestone`: stable ID, initiative, due date, deliverable, acceptance text, owner, state, required/accepted evidence, accepted-by and accepted-at.
3. `Dependency`: predecessor deliverable/decision, successor initiation or milestone, blocking flag and rationale. Reject missing references, cross-company references and cycles.
4. `CapacityBudget` and `ResourceDemand`: weekly change-hour budgets/demand with units and provenance, plus the configurable major-workstream limit.
5. `SelectionDecision` and `SteeringDecision`: dispositions, reasons, actor, date, evidence cutoff, due/revisit date and affected immutable plan version.

Use the existing repositories, plan serialization and audit events. An approved plan version is immutable; execution updates reference it and material rescheduling creates a proposed revision. Do not model tasks as new workflow runs. Stable dependency references must survive display-title edits and exclusions. Excluding a prerequisite must block or remove the dependent work explicitly, not leave an executable orphan.

Connect schedule output to the finance agent's initiative-level phasing contract. The scheduler provides earliest feasible dates and constraints; the value model calculates delayed in-year financial effects. Do not implement a second competing cash-flow calculator. Align KPI target timing with that same approved schedule, preserving the old target path for variance-to-original-plan reporting.

## Prioritized tickets

All engineering/research/artifact ownership below is **Codex**. Effort is incremental for this workstream and overlaps with financial modeling, lifecycle versioning and executive UI work owned by the other roadmap tracks; the coordinator should deduplicate it.

| Ticket | Priority / effort | Dependencies | Deliverable and acceptance |
|---|---|---|---|
| OM-01: decision rubric and worked case | P0 / 1–2 days | Evidence/thesis track's opportunity and assumption inventory | One short operating playbook and comparison matrix covering selected, deferred and rejected candidates. Every disposition has an intelligible reason; invented operational data is labeled. A high-value but unsupported item is held back. No mandatory user choices needed. |
| OM-02: execution and decision contracts | P0 / 2–3 days | OM-01; lifecycle track agrees stable plan/version IDs | Typed initiative, milestone, dependency and decision contracts; migration/backward compatibility for existing plans. Unassigned operators visible. Milestones have dates, deliverables and evidence requirements. Invalid references/cycles cannot be approved. |
| OM-03: capacity and dependency sequencing | P0 / 3–4 days | OM-02; assumption registry | Deterministic weekly scheduler and constraint explanations. One worked shared-resource conflict defers the lower-priority initiative; an enabler consumes capacity; unknown capacity is reported; no feasible slot produces a blocker. Declared budgets never exceeded in a committed schedule. |
| OM-04: dated plan and financial timing integration | P0 / 2–3 days | OM-03; finance track's initiative phasing contract | Calendar 30/60/100 view with original and proposed timing. A three-month delay visibly changes in-year value using the shared calculator. Excluding a prerequisite invalidates downstream launch. Existing approved totals/history remain traceable. |
| OM-05: steering decision cycle | P1 / 2–3 days | OM-02; lifecycle track's immutable revision policy | Packet with next meeting date, evidence cutoff, changed facts, blockers, decisions due, accountable owners and revisions. Complete one simulated proceed/defer/stop cycle; fake actors never appear as real human approvals. Actual decision endpoints retain current authorization rules. |
| OM-06: KPI-to-action and case acceptance | P1 / 2–3 days | OM-04/05; executive output and realization contracts | Link an off-track KPI or missed milestone to a dated management response and next evidence request. Demonstrate a changed decision and forecast, not simply a red badge. End-to-end case shows realized financial value as unverified until appropriate financial evidence exists. |
| OM-07: real operating-pilot calibration | Later / 1–2 engineering days plus external review | Permissioned company/operator available; operational-pilot entry criteria | Replace constructed budgets and owners with confirmed information; review tolerances and decision rights with an operator. Record objections and revise. This is explicitly outside research-showcase completion. |

The showcase method work is approximately **12–18 engineering days before cross-track deduplication**. Do not add this mechanically to UI/financial/versioning estimates that cover the same integration work. The operating calendar above is a simulation artifact and does not prescribe a 100-day software build.

## Meaningful acceptance scenarios

* Selection judgment: a large unsupported case remains `needs_evidence` despite ranking first; a smaller reversible intervention can be selected with a transparent reason. Construction provenance survives exports.
* Capacity: two initiatives demand the same operator in the same week; the second shifts, the constraint is visible, and any changed financial timing uses the shared calculator. Increasing a budget produces a new schedule proposal, not an edit to approval history.
* Dependencies: a cycle, missing predecessor or cross-company dependency is rejected. Removing an enabler cannot leave a dependent initiative cleared for launch. Renaming display text does not break references.
* Calendar: verify day 0/30/60/100 across month/year boundaries; timezone affects recorded decision instants but not silently the agreed calendar date. Late evidence cannot be shown as available at an earlier decision cutoff.
* Authority: a model can recommend; it cannot record a real milestone acceptance or operating approval without the established human principal. A simulated walkthrough never counts as human acceptance.
* Monitoring: delayed source data is marked as such and compared with an appropriate period. A missed milestone creates an actionable decision request; clearing the alert does not invent an improvement or realized EBITDA.
* Reproducibility: the same inputs, capacity budgets, ordering and policy yield the same schedule; a changed assumption produces a reviewable diff.
* Executive review: from the summary, a reviewer can explain why the chosen first wave fits, what waits, the next decision date and the supporting evidence without interpreting an opaque composite score.

## User involvement and deferred ideas

No additional user decisions are required to build the research showcase: Codex can choose and label the default capacity, roles, simulated kickoff and methodological assumptions, prepare the case, implement the contracts and run tests. User input is helpful for the final interview narrative, but it is not a prerequisite for constructing the artifact.

Nondelegable inputs arise only for a real company pilot: a data owner must grant permitted access; actual managers must confirm responsibilities and capacity; authorized humans must make operating decisions; an independent practitioner must supply their own review if the project is to claim independent validation. Codex can prepare requests, packets and revisions, but cannot manufacture those facts. The user need not arrange any of these merely to finish the simulated showcase.

Defer a general PM application, Jira integration, multi-company resource marketplace, full critical-path/Monte Carlo optimizer, automated calendar/email dispatch, learned scoring weights and calibrated execution probabilities. None is necessary to demonstrate a defensible first-wave decision. Do not expand into a ten-factor weighted score, use enablers to fabricate direct EBITDA, treat three workstreams as a universal rule, or automatically interpret KPI attainment as financial realization. The strongest portfolio evidence is one understandable plan that changes when the evidence or constraints change.
