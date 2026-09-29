# Progress case: acceptance evidence and remaining work

**September 29, 2026 · internal engineering review · full five-outcome goal remains open**

This is the current review map for the public Progress case and constructed
lifecycle. It supersedes the old Beacon narrative as the primary portfolio
entry point. It does not erase the [historical application acceptance record](acceptance.md)
or [delegated v0.1.0 showcase closeout](showcase-closeout.md).

## What is verified

The financial/lifecycle implementation through [PR #36](https://github.com/ahines99/pe-value-creation-os/pull/36)
was tested at `4bf92ab2539cdced14fcd0fcd384b484db13e7d7` and merged as
`c806eaf97a84b5f3d60c3a2d1ab81b2d8ee2a8de`. The trees matched after merge.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36511734336)
passed: **1,154 tests on each of Python 3.12, 3.13 and 3.14**, **39 installed-package
evaluations**, **81 page/viewport checks** and **31 bundle conditions**, installed
CLI/Compose acceptance, infrastructure validation and security/container scans.
Twelve published files were checked against the merge's Git blobs. The local
suite passed 1,153 tests with one Windows symlink-privilege skip. These counts
describe that exact implementation, not subsequent documentation changes or
independent finance validation.

The new [review consistency command](../../scripts/check_progress_review.py)
additionally checks the linked bundle. Its CI receipt records all inspected hashes
and the current exit revision. The lineage update expands it to 15 conditions: exit inputs, original
operating-source inputs, full memo reproduction, public appendix, historical
valuation, original underwriting, capacity plan, frozen close, accounting
continuity, attribution reconciliation, authority boundaries and the two rendered
memo/exit pages, lineage authority and the rendered lineage page. It uses the application's calculators; hand-worked expectations
and adversarial cases remain in the separate test suites below.

## Requirement-by-requirement evidence

The subsequent [accounting-restatement exhibit](accounting-restatement.html)
compares independently retrieved original and amended FY2005 filings, reconciles
17 financial rows per version and preserves the intervening non-reliance notice.
Released in [PR #37](https://github.com/ahines99/pe-value-creation-os/pull/37),
tested at `d1016dd1732ea24e1075c8032a674205cf0a7951` and merged as
`18d8c85c3cc0f51bb36842366c9aba874eb32997` with identical trees. All ten
[CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36619814502)
passed: 1,175 tests on each Python version, 84 browser checks, 31 bundle conditions
and 39 installed-package evaluations. Eight published files matched the merge.
Its date-only chronology does not close the missing exact-publication criterion.

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
pilot remain absent. The current remaining sequence is maintained in the
[completion checklist](remaining-work.md).

The current allocation increment adds a separate [six-revision review](allocation-review.html)
and [executive memo](allocation-memo.html). `test_benefit_interactions.py`,
`test_interaction_workflow.py`, `test_interaction_sources.py` and
`test_allocation_demo.py` cover the population/shared-cost rules, saved selection,
exact source pools and unchanged frozen claims. `check_allocation_review.py`
reproduces six financial snapshots, accounting and five rendered exhibits through
eight additional consistency conditions. Its browser coverage adds five pages to
the existing 19-page suite. These are software acceptance checks, not independent
finance validation or company outcomes. See [ADR 0027](../adr/0027-benefit-pool-allocation.md).
Pool allocation and exclusivity are implemented within that ADR's explicit scope;
ADR 0028 adds scoped KPI split/merge history. These are distinct supported
contracts, not automatic conversion between physical ownership and shared pools.
Independent challenge remains unperformed.

“Implemented” below describes the indicated software behavior. “Open” means the
complete outcome is not established. Passing tests does not replace external facts.

| Objective / roadmap requirements | Authoritative artifacts and meaningful checks | Status and remaining evidence |
|---|---|---|
| **1. Public Progress diligence — OP-01/02/09** | [Public baseline](progress-baseline.html), [charter](../pilot/progress-case-charter.md); `test_public_diligence.py`, `test_quarterly_diligence.py`, `test_public_growth.py`, `test_public_peers.py` cover source classes, period differences, reconciliation, peer exclusion and withheld unsupported comparisons | Public replay and sourced observations implemented. Commercial conclusions, broader comparability and organic/perimeter explanations remain limited by evidence and independent review. No actual Progress engagement |
| **2. EBITDA, cash and valuation — OP-04/05/06/07** | [Underwriting](underwriting.html), [historical valuation](historical-valuation.html), [exit review](exit-review.html), [allocation and KPI composition](allocation-lineage-review.html); financial, interaction and allocated-lineage tests cover hand-worked amounts, cost timing, cash reversals, missing earnings, negative residuals, shared pools and EV decomposition | Separate models, fixed-share pools, exclusivity and scoped KPI composition implemented. Comparative amortization, independently challenged adjustments/maintainability and actual transaction claim inputs remain open |
| **3. Capacity-aware 100-day plan — OP-08/10/11** | [Operating proposal](operating-plan.html), [source constraints](operating-sources.html), [execution receipts](execution.html); `test_operating_plan.py`, `test_operating_sources.py`, `test_execution.py` cover conflicts, dependencies, blocked gates, notice/quality/vendor limits and withdrawn support | Constructed feasibility and execution-state demonstration implemented. Actual operator commitments, effort, capacity and delivery evidence absent |
| **4. Executive memo — OP-12/13** | [Memo](decision-memo.html), [case study](case-study.md), [demo](progress-demo.md), [practitioner packet](practitioner-review.md); `test_decision_memo.py`, `test_memo_review.py` and bundle check reproduce the decision and reject rehashed financial tampering; browser script checks keyboard/disclosure/narrow views | Integrated packet and internal engineering challenge implemented. Observed human comprehension, external commercial/finance challenge and scored practitioner rubric remain unperformed; no overall acceptance score assigned |
| **5a. Underwriting-to-realization — OP-03/14/15** | [Case history](case-history.html), [realization](realization.html), [source review](source-review.html), [exit review](exit-review.html), [allocated lifecycle](allocation-lineage-review.html); revision, realization, source, exit and lineage tests cover exact reviews, frozen baselines, corrections, residuals, tenant boundaries and old-hash compatibility | Ten-revision physical-ownership and twelve-revision shared-pool constructed exercises implemented, with initiative/task changes and immutable scoped KPI definitions/readings. Real causal attribution and independently reviewed lessons remain unproven |
| **5b. Historical replay — OP-16** | [Disclosure history](disclosure-history.html), [accounting restatement](accounting-restatement.html), `test_disclosure_history.py`, `test_accounting_restatement.py`; independent source-PDF verification, reconciliation and cutoff tests | Separate measurement-period and actual accounting-error comparisons implemented; restatement released with exact-build acceptance. Date reconstruction suspends numbers during non-reliance. Exact public-availability time remains unavailable, so OP-16 is not complete |
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
| Financial reconciliation | Worked numerical examples plus separate EBITDA/cash/EV exhibits, shared pools and retained costs; adverse source correction remains adverse | Comparative amortization and independent maintainability review remain open; tests do not establish finance approval |
| Feasible plan | Resource/dependency conflicts change dated schedule and economics; missing prerequisites block work | Assumed budgets cannot establish actual management capacity |
| Version and authority | Immutable revisions, exact-hash receipts, scoped access, simulation labels and preserved frozen close | Split/merge and KPI history implemented for disjoint ownership and explicit shared-pool scopes; no simulated review becomes human authority |
| Executive challenge | Recomputed alternatives, visible contrary evidence, internal adversarial tests and prepared review prompts | No observed comprehension or external score; do not call this practitioner-reviewed |
| Usability and publication | 27 pages × three widths in PR #36; keyboard and disclosure checks; rendered memo/JSON consistency | Final guided-route acceptance remains; browser automation does not establish accessibility certification or human usability acceptance |
| Honest outcome | Actual company value, proceeds and pilot result unavailable | Company participation and observed evidence are external prerequisites |

## Remaining work and ownership

1. **Codex:** follow the [step-by-step completion checklist](remaining-work.md), preserving PR #36 as the current verified implementation and the original OP requirements as the acceptance baseline.
2. **Codex:** finish public-source, financial-definition, peer/thesis and historical-replay research. Preserve unsupported or adverse conclusions and explicitly identify any criterion that evidence cannot satisfy.
3. **Codex:** consolidate the executive walkthrough, finalize portfolio packaging and execute acceptance and review corrections. A practitioner session is unperformed until someone participates; blank worksheet fields remain blank.
4. **Codex:** build and test generic private ingestion and readiness controls with permitted fixtures, then adapt them to the sponsor's authorized scope. No company environment or permission is presumed.
5. **Alex, when available:** introduce a willing reviewer or authorized company sponsor. No immediate data, credentials or setup are requested.
6. **Sponsor/company:** authorize records and processing, validate accounting and capacity, make intervention decisions, perform operations and review observed outcomes. Codex prepares mappings, calculations, review packets and reporting.

The six-week diagnostic and any subsequent day-30/60/100 intervention cycle have
separate authorization and clocks. Software work cannot manufacture elapsed
operating periods, actual management decisions or independent review.

This packet advances OP-13; it does not close every OP-01–17 criterion or the full
goal. The [capability roadmap](../operating-partner-roadmap.md) retains the original scope.

The September 29 [peer-source review](../research/operating-partner/07-peer-evidence-review.md)
adds verified SS&C statements to the existing selected cohort. All four candidates
now have mapped public sources; broader context changes while strict medians
remain withheld. This does not establish normalized profitability or sized savings.
