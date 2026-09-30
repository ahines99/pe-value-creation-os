# Progress case: acceptance evidence and remaining work

**September 29, 2026 · internal engineering review · eight-step showcase closeout remains open**

This is the current review map for the public Progress case and constructed
lifecycle. It supersedes the old Beacon narrative as the primary portfolio
entry point. It does not erase the [historical application acceptance record](acceptance.md)
or [delegated v0.1.0 showcase closeout](showcase-closeout.md).

## Current eight-step showcase closeout

This is the authoritative acceptance register for the requested showcase finish.
Private-pilot feature expansion is later work; its unfinished features do not
replace the public-case requirements below. Actual practitioner participation and
historical timing cannot be inferred from passing software checks.

| Requested step | Status | Evidence / remaining acceptance |
|---|---|---|
| 1. Release attribution | Complete | PR #50: ten CI jobs, 1,757 tests per Python, seven published files verified against merge `939c91e36f36885444fb8d397f62009a479268b4`. |
| 2. Release executive attribution review | Complete | PR #51: ten CI jobs, 1,781 tests per Python, 84 public and 12 private browser checks; five changed published files match merge `781f1f4276919735c7fa55fad4339d1ff0ff1311`. The interface uses authenticated private data; static Pages is not the running private application. |
| 3. Public-company diligence dispositions | Complete at public-research scope | [Final register](../research/operating-partner/09-public-diligence-disposition.md) covers acquisitions/perimeter, organic-growth limits, peers and retain/reject/defer decisions with explicit reopening evidence. Unavailable management facts remain unavailable. |
| 4. Financial-definition exceptions | Disposition documented; component explanations unavailable | [Financial review](../research/operating-partner/08-financial-definition-review.md) retains all four differences, specified data requests and withheld dependent measures. No normalized earnings or independent finance approval claimed. |
| 5. Historical disclosure timing | Open | Original/restated filings and chronology exist; exact first public availability remains unverified. SEC acceptance and an after-close announcement do not satisfy this requirement. |
| 6. Executive narrative and interview package | Aligned and locally verified | Landing page, README, case study, demo, architecture, setup, screenshots and resume guide distinguish the public case, fictional approval demo and permissioned attribution interface. Closeout release evidence is linked below. |
| 7. Final showcase acceptance | Local acceptance complete; exact release receipt required | Fresh locked checkout: 25 build/check commands, 31 consistency conditions, 147 focused tests and 84 public browser checks passed. The closeout PR records final exact-head CI, merge identity and publication verification; do not infer those from local checks alone. |
| 8. Actual practitioner feedback | Prepared; session unperformed | [Review packet](practitioner-review.md) provides the session and response log. A real participant must supply comprehension evidence, objections and disposition; no score has been assigned. |

## What is verified

### Final showcase package

[PR #52](https://github.com/ahines99/pe-value-creation-os/pull/52) is the release
record for this closeout package. Its final verification receipt identifies the
tested head, CI run, merge and published-file hashes. Step 7 is satisfied only
when that receipt confirms all ten CI jobs and exact publication; the PR's creation
alone is not acceptance. This release gate does not close steps 5 or 8.

A separate clean checkout at `ef785058e94277666293a7f59574f31919123088` used a
fresh `uv sync --frozen --extra dev` environment and no vendor or model credentials.
All 25 public build/check commands passed, including 15 primary-bundle and two
sets of eight allocation conditions. Regenerated public JSON retained the same
business values: recursive comparison, including embedded JSON, found changes
only in generated revision UUIDs, recorded/created timestamps and content hashes.
Fresh simulation histories are therefore not byte-identical release artifacts;
publication is separately compared against the released Git blobs.

The unchanged financial/research implementation passed 147 focused tests. Source
checks verified 15 growth facts plus nine disclosure anchors, 126 peer facts and
anchors, and 13 dated balance facts with five debt reconciliations. All 84 current
public page/viewport checks passed at 1440, 768 and 375 pixels, including keyboard
navigation and disclosures. Landing screenshots at all three widths and the
private review tablet screenshots were visually inspected, supplementing the
private desktop/phone release inspection. These are engineering checks, not
independent financial or human usability validation.

### Executive attribution interface

The private executive review workspace was released in
[PR #51](https://github.com/ahines99/pe-value-creation-os/pull/51), tested at
`8707fcedd89a69f6d863f77a21da86c8b07fbcf8` and merged as
`781f1f4276919735c7fa55fad4339d1ff0ff1311` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36654645174)
passed: 1,781 tests on each supported Python version, 84 public and 12 private
page/viewport checks, 31 bundle conditions and 39 installed-package evaluations.
Five changed published files matched the merge. Local regression passed 243 tests;
the final decision-history assertions separately passed both repository/session
checks. The 24 new workspace tests and 12 browser checks use fictional records.
The private application itself is not hosted by the static portfolio site.

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

The subsequent peer-source review was released in
[PR #38](https://github.com/ahines99/pe-value-creation-os/pull/38), tested at
`cd841b165cb9af25a80cf8b354ab6793e9cb16a1` and merged as
`de2ee940ad9f6f1a2735dc15d208b72bbb831362` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36622008898)
passed: 1,176 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Thirteen published
files matched the merge. The four sourced candidates remain subject to
metric-level exclusions; strict peer medians are still withheld.

The financial-definition review was released in
[PR #39](https://github.com/ahines99/pe-value-creation-os/pull/39), tested at
`d172d3da31dda587d987c1436534d22d9bee51fb` and merged as
`082beb0c972b562ad0e0fd659089cc0a977d7474` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36624637599)
passed: 1,176 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Nine published files
matched the merge. Both briefs now expose all four supplied annual/interim
amortization exceptions. Their causes and independent finance review remain open.

The executive walkthrough and interview guide were released in
[PR #40](https://github.com/ahines99/pe-value-creation-os/pull/40), tested at
`25775e8294cf180baad6d6da3ba3e42e34f83d20` and merged as
`34c75f5ff46a0f83ac8dc73044e753de7789d858` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36626437331)
passed: 1,176 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Sixteen published
files matched the merge, including the primary route, screenshots and guides.
The browser suite checks the route's six destinations and binds the landing
conclusion to the saved memo. Observed human comprehension remains unperformed.

The private intake preflight was released in
[PR #41](https://github.com/ahines99/pe-value-creation-os/pull/41), tested at
`048acca8d99e83112ad4d2b9f454631c53cec1dd` and merged as
`3188280ee8597c4dd6c68df9fc6e9a168307214c` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36628596953)
passed: 1,227 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Six published files
matched the merge. The checks used fictional private-lane fixtures; permission
verification, finance acceptance, admission and a performed pilot remain absent.

The processing-grant registry was released in
[PR #42](https://github.com/ahines99/pe-value-creation-os/pull/42), tested at
`8578ca0ef189a9978ab2a5f84a5496a65972caca` and merged as
`168833a358b5719b15a5a91514eacef58f794e3d` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36630887673)
passed: 1,264 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Seven published
files matched the merge. These are fictional-fixture software checks, not
actual company authorization, independent finance review or a performed pilot.

The private source-custody and finance-review workflow was released in
[PR #43](https://github.com/ahines99/pe-value-creation-os/pull/43), tested at
`ebbb960c2760171fb6b4018455cfcaaa66c524b0` and merged as
`35a93214936f74a6339be2e5a36aff90a768713c` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36633938733)
passed: 1,319 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Eight published files
matched the merge. Local focused checks passed 55 tests, and migration round-trip
passed at 0009. No actual private company records or performed pilot are represented.

The private financial-snapshot workflow was released in
[PR #44](https://github.com/ahines99/pe-value-creation-os/pull/44), tested at
`cdbf05e772a133d5475f7c88ebc0f4ed1af526b6` and merged as
`e97a5f6c52f268aaf61e3334b5deb2406313a4b5` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36636672315)
passed: 1,356 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Nine published files
matched the merge. The local focused/regression suite passed 373 tests with one
Windows symlink-privilege skip; migration round-trip passed at 0010. This remains
fictional-fixture software validation, not company acceptance or a performed pilot.

The private underwriting workflow was released in
[PR #45](https://github.com/ahines99/pe-value-creation-os/pull/45), tested at
`5e1de4fa6b23fdb00bfdb551a0972d2f4f41c396` and merged as
`2a9f3e11b539e4e55d8930be541d13abe7f65953` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36639076145)
passed: 1,421 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Seven published files
matched the merge. The local focused/regression suite passed 387 tests with one
Windows symlink-privilege skip; migration round-trip passed at 0011. These checks
use fictional inputs and do not establish actual company review or pilot results.

The private capacity-plan workflow was released in
[PR #46](https://github.com/ahines99/pe-value-creation-os/pull/46), tested at
`ed208745bb08fc5851c9523d5d7f8321c7b1652f` and merged as
`f6247d715e91de105e7fea4fb5044a0c9fe0681e` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36640797738)
passed: 1,490 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Eight published files
matched the merge. The local focused/regression suite passed 467 tests with one
Windows symlink-privilege skip; migration round-trip passed at 0012. These checks
use fictional inputs and do not establish management commitment or pilot results.

The private human-review and frozen-baseline workflow was released in
[PR #47](https://github.com/ahines99/pe-value-creation-os/pull/47), tested at
`3a79d8c961b4d5a539b40856bec37863dbdfe761` and merged as
`607299a92e24178b8ad984f082cf1cb544a35fd5` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36643048658)
passed: 1,556 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Nine published files
matched the merge. Local focused checks added 66 tests; the related regression
suite passed 461 tests with one Windows symlink-privilege skip. Migration
round-trip passed at 0013. These are fictional-fixture software checks, not
actual human company review, operating authorization or pilot results.

The private counterfactual and monthly-observation workflow was released in
[PR #48](https://github.com/ahines99/pe-value-creation-os/pull/48), tested at
`a40caaa7f62ef5095ccc7ebbb0e629416208cc22` and merged as
`4560a744260246158082e7c02ba8360c6ac76771` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36647436171)
passed: 1,637 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Six published files
matched the merge. The new focused suite passed 81 tests; migration round-trip
passed at 0014. Differences remain explicitly unattributed. These fictional-fixture
checks do not establish actual company review, realized value or a performed pilot.

The private intervention and delivery workflow was released in
[PR #49](https://github.com/ahines99/pe-value-creation-os/pull/49), tested at
`6b6830d089b4e298641ddfb30a75985b305ae01a` and merged as
`e743249f9c5d64e84a08382e2c076f34a368b7d1` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36649675120)
passed: 1,701 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Six published files
matched the merge. The execution workflow has 64 new checks; migration round-trip
passed at 0015. The related local regression suite passed 605 tests with one
Windows symlink-privilege skip before the final capacity-identity guard; that guard
and valid authorization path separately passed three focused checks. These are
fictional-fixture software checks, not company authority or actual operating work.

The private attribution and separate finance-review workflow was released in
[PR #50](https://github.com/ahines99/pe-value-creation-os/pull/50), tested at
`e15b8552b85e5d0832995f6c0854a71f101a2d0d` and merged as
`939c91e36f36885444fb8d397f62009a479268b4` with identical trees.
All ten [CI jobs](https://github.com/ahines99/pe-value-creation-os/actions/runs/36652115051)
passed: 1,757 tests on each supported Python version, 84 browser checks,
31 bundle conditions and 39 installed-package evaluations. Seven published files
matched the merge. The attribution workflow has 56 new checks; the related local
regression suite passed 662 tests with one Windows symlink-privilege skip.
Migration round-trip passed at 0016. These are fictional-fixture checks, not
independent company finance acceptance, proof of causal impact or a performed pilot.

The new [review consistency command](../../scripts/check_progress_review.py)
additionally checks the linked bundle. Its CI receipt records all inspected hashes
and the current exit revision. The lineage update expands it to 15 conditions: exit inputs, original
operating-source inputs, full memo reproduction, public appendix, historical
valuation, original underwriting, capacity plan, frozen close, accounting
continuity, attribution reconciliation, authority boundaries and the two rendered
memo/exit pages, lineage authority and the rendered lineage page. It uses the application's calculators; hand-worked expectations
and adversarial cases remain in the separate test suites below.

The subsequent [private source-custody increment](../pilot/permissioned/intake-records.md)
implements atomic source bytes and receipts, persisted quarantine/corrections,
exact-version human finance decisions and current accepted-source checks. Local
tests cover memory/PostgreSQL/API, revocation races, rollback and source reproduction.
Its CI/publication acceptance is now verified in PR #43. The subsequent
[private financial snapshots](../pilot/permissioned/financial-snapshots.md) calculate
monthly inputs with exact source/review/grant bindings and explicit accounting
definitions; CI/publication acceptance is verified in PR #44. The
[private underwriting increment](../pilot/permissioned/underwriting.md) is released
in PR #45. [Private capacity plans](../pilot/permissioned/capacity-plans.md)
are released in PR #46. [Reviewed baselines](../pilot/permissioned/reviewed-baselines.md)
are released in PR #47. The [private-observation increment](../pilot/permissioned/observations.md)
adds reviewed counterfactuals, accepted whole-month actuals and unattributed
frozen-plan comparisons, released and verified in PR #48. The subsequent
[private execution increment](../pilot/permissioned/execution.md) records bounded
human intervention decisions, delivery segments and exact prerequisite acceptance,
released and verified in PR #49. The [private attribution increment](../pilot/permissioned/attribution.md)
adds signed allocations, delivery-to-claim checks, residuals and separate finance
review, released and verified in PR #50. The
[private finance review workspace](../pilot/permissioned/review-workspace.md) adds
an executive attribution page and exact-version human decision form, released
and verified in PR #51. Private operating-source and delivery-cost reconciliation,
executive memo, remaining pilot screens, retention operations and all
real-company pilot evidence remain outstanding.

## Requirement-by-requirement evidence

The primary entry now follows one six-stop decision story, with the separate
shared-pool and local application examples identified explicitly. The
[presenter guide](progress-demo.md) and case study preserve period and example
boundaries. Browser checks verify all route destinations, keyboard access and
the landing conclusion against the saved memo. This provides automated route
acceptance, not observed executive comprehension or practitioner endorsement.

The [financial-definition review](../research/operating-partner/08-financial-definition-review.md)
records the outcome of the selected-source investigation: supported earnings and
cash definitions, four source-period amortization exceptions and the related
derived-quarter limit, retained expenses and historical valuation boundaries.
Both decision briefs now expose the interim exceptions previously absent from the
executive register. No unresolved component is relabeled or used to create an addback.

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
| Usability and publication | Historical PR #36: 27 pages × three widths. PR #40: 84 page/viewport checks, including the six-stop primary route, keyboard/disclosure checks and memo/JSON consistency; sixteen published files matched its merge | Automated route and publication acceptance verified; browser automation does not establish accessibility certification or observed human usability acceptance |
| Honest outcome | Actual company value, proceeds and pilot result unavailable | Company participation and observed evidence are external prerequisites |

## Remaining work and ownership

1. **Codex:** verify the exact closeout release and append its receipt to PR #52. Retain this register as the acceptance index; pending publication is not a completed release.
2. **Codex:** pursue historical dissemination evidence if a defensible source becomes available. Exact first-public-availability remains unmet. The four financial-definition exceptions retain their documented dispositions and specific component requests; unsupported adjustments remain withheld.
3. **Alex:** introduce a willing practitioner when available. **Codex:** prepare the session, record actual objections and comprehension evidence, implement corrections and return material changes for reviewer disposition. Blank responses and scores remain blank until participation occurs.
4. **Later pilot:** resume the [broader checklist](remaining-work.md) only after showcase work. Codex implements remaining private workflow and readiness work; an authorized sponsor must supply permitted records, accounting/capacity validation, operating decisions and observed outcomes. No company participation is presumed.

The six-week diagnostic and any subsequent day-30/60/100 intervention cycle have
separate authorization and clocks. Software work cannot manufacture elapsed
operating periods, actual management decisions or independent review.

This packet advances OP-13; it does not close every OP-01–17 criterion or the full
goal. The [capability roadmap](../operating-partner-roadmap.md) retains the original scope.

The September 29 [peer-source review](../research/operating-partner/07-peer-evidence-review.md)
adds verified SS&C statements to the existing selected cohort. All four candidates
now have mapped public sources; broader context changes while strict medians
remain withheld. This does not establish normalized profitability or sized savings.
