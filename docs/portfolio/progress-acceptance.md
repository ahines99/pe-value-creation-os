# Progress case: acceptance evidence and remaining work

**September 28, 2026 · internal engineering review · full five-outcome goal remains open**

This is the current review map for the public Progress case and constructed
lifecycle. It supersedes the old Beacon narrative as the primary portfolio
entry point. It does not erase the [historical application acceptance record](acceptance.md)
or [delegated v0.1.0 showcase closeout](showcase-closeout.md).

## What is verified

The financial/lifecycle implementation through [PR #32](https://github.com/ahines99/pe-value-creation-os/pull/32)
was tested at `e17b30b7046d27970e538034d79cf98824414943` and merged as
`6575997f67358d7144253a323be2c1e83a9212da`. The trees matched after merge.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36493440351)
passed: **1,047 tests on each of Python 3.12, 3.13 and 3.14**, **39 installed-package
evaluations**, **54 page/viewport checks**, installed CLI/Compose acceptance,
infrastructure validation and security/container scans. Published exhibit bytes
were checked against the merge's Git blobs. These counts describe that exact
implementation, not future commits or independent finance validation.

The new [review consistency command](../../scripts/check_progress_review.py)
additionally checks the linked bundle. Its CI receipt records all inspected hashes
and the current exit revision. The lineage update expands it to 15 conditions: exit inputs, original
operating-source inputs, full memo reproduction, public appendix, historical
valuation, original underwriting, capacity plan, frozen close, accounting
continuity, attribution reconciliation, authority boundaries and the two rendered
memo/exit pages, lineage authority and the rendered lineage page. It uses the application's calculators; hand-worked expectations
and adversarial cases remain in the separate test suites below.

## Requirement-by-requirement evidence

The subsequent [twelve-revision shared-pool lifecycle](allocation-lineage-review.html)
and [memo](allocation-lineage-memo.html) compose allocation policy with initiative
and scoped KPI history (ADR 0028). Its selected 60% population splits into 24% and
36%, retains target/read corrections and recombines without moving frozen claims.
`test_allocated_lineage.py` covers worked measurements, semantic tampering,
PostgreSQL/API persistence, audit rollback, access/approval boundaries and exit
composition. The extended bundle checker adds eight conditions, and browser
coverage now includes 27 pages at three widths. This closes the allocated-population
composition gap; automatic conversion of physical ownership and grouped exclusive
alternatives remain deliberately unsupported. Independent review and a performed
pilot remain absent. Older counts and open-item wording below describe their
specific earlier increments, not this version.

The current allocation increment adds a separate [six-revision review](allocation-review.html)
and [executive memo](allocation-memo.html). `test_benefit_interactions.py`,
`test_interaction_workflow.py`, `test_interaction_sources.py` and
`test_allocation_demo.py` cover the population/shared-cost rules, saved selection,
exact source pools and unchanged frozen claims. `check_allocation_review.py`
reproduces six financial snapshots, accounting and five rendered exhibits through
eight additional consistency conditions. Its browser coverage adds five pages to
the existing 19-page suite. These are software acceptance checks, not independent
finance validation or company outcomes. See [ADR 0027](../adr/0027-benefit-pool-allocation.md).
The older rows below retain their historical evidence; richer pool allocation and
exclusivity are now implemented within that ADR's explicit scope. Composition with
physical split/merge KPI lineage and independent challenge remain open.

“Implemented” below describes the indicated software behavior. “Open” means the
complete outcome is not established. Passing tests does not replace external facts.

| Objective / roadmap requirements | Authoritative artifacts and meaningful checks | Status and remaining evidence |
|---|---|---|
| **1. Public Progress diligence — OP-01/02/09** | [Public baseline](progress-baseline.html), [charter](../pilot/progress-case-charter.md); `test_public_diligence.py`, `test_quarterly_diligence.py`, `test_public_growth.py`, `test_public_peers.py` cover source classes, period differences, reconciliation, peer exclusion and withheld unsupported comparisons | Public replay and sourced observations implemented. Commercial conclusions, broader comparability and organic/perimeter explanations remain limited by evidence and independent review. No actual Progress engagement |
| **2. EBITDA, cash and valuation — OP-04/05/06/07** | [Underwriting](underwriting.html), [historical valuation](historical-valuation.html), [exit review](exit-review.html); `test_underwriting.py`, `test_historical_valuation.py`, `test_exit_review.py` cover hand-worked amounts, cost timing, cash reversals, missing earnings, negative residuals and EV decomposition | Explicit separate models implemented. Richer pool allocation/exclusivity, independently challenged adjustments/maintainability and actual transaction claim inputs remain open |
| **3. Capacity-aware 100-day plan — OP-08/10/11** | [Operating proposal](operating-plan.html), [source constraints](operating-sources.html), [execution receipts](execution.html); `test_operating_plan.py`, `test_operating_sources.py`, `test_execution.py` cover conflicts, dependencies, blocked gates, notice/quality/vendor limits and withdrawn support | Constructed feasibility and execution-state demonstration implemented. Actual operator commitments, effort, capacity and delivery evidence absent |
| **4. Executive memo — OP-12/13** | [Memo](decision-memo.html), [case study](case-study.md), [demo](progress-demo.md), [practitioner packet](practitioner-review.md); `test_decision_memo.py`, `test_memo_review.py` and bundle check reproduce the decision and reject rehashed financial tampering; browser script checks keyboard/disclosure/narrow views | Integrated packet and internal engineering challenge implemented. Observed human comprehension, external commercial/finance challenge and scored practitioner rubric remain unperformed; no overall acceptance score assigned |
| **5a. Underwriting-to-realization — OP-03/14/15** | [Case history](case-history.html), [realization](realization.html), [source review](source-review.html), [exit review](exit-review.html); `test_case_revisions.py`, `test_realization.py`, `test_source_revisions.py`, `test_exit_review.py`, `test_initiative_lineage.py`, `test_source_partitions.py` cover exact reviews, frozen baselines, corrections, residuals, tenant boundaries and old-hash compatibility | Ten-revision constructed lifecycle implemented with explicit initiative/task splits and merges, exact source ownership and immutable KPI definitions/readings; real causal attribution and independently reviewed lessons remain unproven |
| **5b. Historical replay — OP-16** | [Disclosure history](disclosure-history.html), `test_disclosure_history.py`; source-PDF row verification and cutoff tests | Provisional/final measurement-period comparison implemented. Exact public-availability time is unavailable; an accounting-error restatement is not demonstrated. Those claims remain withheld |
| **5c. Permissioned pilot — OP-17** | [Sponsor brief](../pilot/permissioned/sponsor-brief.md), [kickoff worksheet](../pilot/permissioned/kickoff-worksheet.md), [data request and roles](../pilot/permissioned/README.md), [entry criteria](../pilot/pilot-plan.md) | Package prepared. No sponsor, private ingestion acceptance, authorized records, intervention or outcome observation. Pilot has not started |
| **Production — OP-18 / existing launch gates** | [Production roadmap](../portfolio-finalization-roadmap.md), pilot entry criteria and operations runbooks | Separate later scope; local/static acceptance does not establish deployed identity, recovery, live alerting, SLOs, signed reviews or staffed operations |

Test files are in [`tests/`](../../tests). Their names identify validation scope;
the exact CI logs establish which build executed them. A test name alone is not
proof of correctness or completion.

## Hard-gate audit

| Gate | Current evidence | Limit / next action |
|---|---|---|
| Allowed-source replay | Public/constructed typed inputs and installed-package regeneration without vendor services; bundle reproduction | No vendor extract included; replay does not independently re-extract filings |
| Source truth | Public facts, authored assumptions and constructed observations stay distinct; unsupported claims remain blocked/unsized | Reviewer must assess commercial relevance and missing operating populations |
| Financial reconciliation | Independent numerical examples plus separate EBITDA/cash/EV exhibits; adverse source correction remains adverse | Richer overlap allocation and maintainability review open |
| Feasible plan | Resource/dependency conflicts change dated schedule and economics; missing prerequisites block work | Assumed budgets cannot establish actual management capacity |
| Version and authority | Immutable revisions, exact-hash receipts, scoped access, simulation labels and preserved frozen close | Split/merge and KPI history implemented for disjoint populations; no simulated review becomes human authority |
| Executive challenge | Recomputed alternatives, visible contrary evidence, internal adversarial tests and prepared review prompts | No observed comprehension or external score; do not call this practitioner-reviewed |
| Usability and publication | 18 pages × three widths in PR #32; keyboard and disclosure checks; rendered memo/JSON consistency | Browser automation does not establish accessibility certification or human usability acceptance |
| Honest outcome | Actual company value, proceeds and pilot result unavailable | Company participation and observed evidence are external prerequisites |

## Remaining work and ownership

1. **Codex:** maintain exact-build acceptance for the [initiative/KPI lineage](lineage-review.html) implementation; preserve its disjoint-population limits. [PR #34](https://github.com/ahines99/pe-value-creation-os/pull/34) records this increment's CI. The separate allocation exercise now covers fixed shares and mutually exclusive choices; composition with physical KPI lineage remains open.
2. **Codex:** complete explicit allocation/KPI-lineage composition and targeted source/commercial diligence where public evidence can resolve them. Preserve unsupported or adverse conclusions.
3. **Codex:** maintain this packet and execute corrections from review. A human/practitioner session is unperformed until someone actually participates; blank worksheet fields remain blank.
4. **Codex:** prepare the agreed private ingestion and readiness evidence once a sponsor defines scope. Generic readiness work may proceed, but no company environment or permission is presumed.
5. **Alex, when available:** introduce a willing reviewer or authorized company sponsor. No immediate data, credentials or setup are requested.
6. **Sponsor/company:** authorize records and processing, validate accounting and capacity, make intervention decisions, perform operations and review observed outcomes. Codex prepares mappings, calculations, review packets and reporting.

The six-week diagnostic and any subsequent day-30/60/100 intervention cycle have
separate authorization and clocks. Software work cannot manufacture elapsed
operating periods, actual management decisions or independent review.

This packet advances OP-13; it does not close every OP-01–17 criterion or the full
goal. The [capability roadmap](../operating-partner-roadmap.md) retains the original scope.
