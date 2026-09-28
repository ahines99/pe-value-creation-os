# Portfolio finalization: execution and owner roadmap

## Published engineering verification

**Current candidate:** `31ebfe9938d6fe92232749632eba5224c0eaffaa` passed all ten
[main-branch CI checks](https://github.com/ahines99/pe-value-creation-os/actions/runs/36367128767):
499 tests on each Python version, 39 evaluations and 18 rendered browser checks,
plus package, Compose, infrastructure and security checks. The draft release now
contains matching packages, source, screenshots, reports, manifest and checksums.
See the [current evidence index](releases/0.1.0/evidence.md). Human acceptance and
final promotion remain open. Earlier verification below is retained as history.

The [private public-company research pilot](pilot/public-company-research.md) is
also implemented and tested. It adds source lineage, accounting reconciliation,
peer context and a diligence memo without manufacturing monthly operating data.
Licensed inputs and outputs stay private. Independent financial review, peer
acceptance and period-aware LSEG cross-checks remain open; this study does not
close the real operating-company production pilot.

All ten [redesign CI checks](https://github.com/ahines99/pe-value-creation-os/actions/runs/36363935682) passed at `c5d4739`: **479 tests on each of Python 3.12, 3.13 and 3.14**, **39/39 evaluations**, **18 rendered browser checks**, installed-package and Compose acceptance, infrastructure validation, and security/container scans. [PR #11](https://github.com/ahines99/pe-value-creation-os/pull/11) merged as `3a5c7a9`.

Prepared September 27, 2026 from the current worktree, [audit remediation](audit-remediation.md), [ticket roadmap](../ROADMAP.md), implementation, packaging and deployment configuration.

**Assessment:** the executive UI redesign is implemented and undergoing renewed acceptance. Alex rejected the earlier visuals. The current worktree passed 478 tests with one Windows symlink-privilege skip, 39 targeted API/UI tests and 39/39 deterministic evaluations. PostgreSQL was enabled in a disposable test database; these are local results, not new CI. Rendered engineering checks and authentic screenshots now exist for six pages at desktop/tablet/mobile widths. Human new-design/MCP acceptance remains open; all ten redesign CI checks passed at `c5d4739`. Production remains a separate, unaccepted milestone.

**Your selected priority: polished showcase first, production roadmap afterward.** The immediate target is P1: an executive-facing PE value-creation workspace that operating partners and portfolio-company leaders can evaluate through decisions, economics, evidence and execution. The current audience direction supersedes the earlier hiring-manager/applied-AI positioning. Technical diligence remains available. Alex previously authorized public Apache-2.0 publication after confirming rights. P2 is an optional intermediate demonstration; P3 retains all real-company production gaps. Public source publication is now authorized; purchases, paid model runs and cloud deployment remain separately gated. No ticket is closed merely by appearing here.

“My actions” means implementation, analysis, automation, configuration and evidence collection I can carry out. “Your actions” means choices, account access, spending authorization, publication rights, actual human use, and obtaining accountable specialist sign-offs. Once access and decisions are supplied, technical execution remains my responsibility.

## Current execution update: executive redesign

The redesign adds an executive portfolio overview with one current assessment per company, separate currency totals and historical links; plan briefs with modeled EBITDA and workstream contributions; technical value-case/source disclosures; decision forms with preserved input and HTML error recovery; and run-specific operating scorecards. Functional repairs include authoritative edited-plan totals before and after worker processing, request-change exclusions, forged-selection rejection, permission-aligned controls, escaped evidence previews and metric-specific units.

[Functional evidence](portfolio/executive-functional-audit.md): **39 targeted tests passed**, including real fixture workflows and an independent portfolio integration review; **39/39 deterministic evaluations passed**. The local Windows full suite passed **478 tests, one symlink-privilege skip, in 176.21 seconds**, with PostgreSQL enabled. Ruff checked 135 files and mypy checked 90 source files successfully. Read-only local Docker HTTP checks returned 200/no-store for the portfolio, approved Beacon review, exact-run KPIs, Delta and evidence preview; local links/anchors passed across 15 HTML captures. These are current-worktree results, not an exact-release CI certificate or rendered screenshots. Isolated Linux Chromium in Docker subsequently passed 18 rendered checks across six pages at 1440/768/375 pixels, including collapsed/expanded overflow, skip-link focus and keyboard disclosures. [Screenshots and browser results](portfolio/acceptance.md#rendered-evidence) are retained and were inspected by the coordinator. Native Windows capture no longer blocks engineering rendering. Human new-design approval/MCP acceptance remains pending; all ten redesign CI checks passed at `c5d4739`; no final release or production launch is claimed.

### Historical public showcase candidate

September 27, 2026: [PR #1](https://github.com/ahines99/pe-value-creation-os/pull/1) merged after all ten checks passed on `9f9b95f`. The repository is public under Apache-2.0, and [GitHub Pages](https://ahines99.github.io/pe-value-creation-os/) serves the static portfolio. Main requires all ten checks with administrator enforcement; force pushes/deletion are disabled. Private vulnerability reporting is enabled. No independent peer approval is claimed.

- **G01/G02/G04/G05 repaired:** committed candidate, installed wheel/fresh checkout, loopback-only Compose and expanded CI. Linux Python 3.12/3.13/3.14 each passed 453 tests; 39/39 deterministic evaluations passed. Evidence is linked in the [versioned index](releases/0.1.0/evidence.md).
- **F04 core complete:** fresh startup, migrations, synthetic seeds, approvals, evidence, worker/KPI consequence, shutdown and restart recovery pass. A PostgreSQL stale-pool recovery defect was found and fixed. Application and local database scans report zero HIGH/CRITICAL findings.
- **Optional telemetry verified with limitations:** metrics, traces, dashboard provisioning and a synthetic Prometheus alert reaching local Alertmanager and resolving were exercised. Optional Grafana (104 HIGH), Tempo (12 HIGH) and Alertmanager (2 HIGH) findings remain; Collector and Prometheus scans were clean. These optional images are not production-approved.
- **F05/F07/F08/F09 implemented:** browser entry/login/review flow, actual captured synthetic HTML/evidence, static portfolio, case study, walkthrough, Apache license/notices, contribution/security policy and changelog exist. Rendered screenshots and keyboard/narrow-screen review were pending at that historical stage; the current rendered evidence is recorded above.
- **Decisions at that stage:** public Apache-2.0 rights, Docker and repository access were supplied; the audience was then technical hiring/applied-AI. The current executive audience and rejection of the former visuals reopen design acceptance. Engineering handles implementation, regression and rendered verification; Alex performs and accepts the human journey.
- **Cloud/paid-model delivery stays opt-in:** the first main CD run skipped. No AWS deployment or paid provider run is required for P1.

### Remaining actions, in execution order

| Step | My action | Your action | Completion evidence |
|---|---|---|---|
| 1. Finalize build evidence — complete | Retained exact-commit CI and refreshed the draft bundle for `31ebfe9`. | None. | 499 tests per Linux Python version, 39/39 evals, 18 browser checks; matching release assets and checksums. |
| 2. Executive design acceptance (F05/F08) | Retain the 18 passing Linux Chromium checks and inspected screenshots; address human feedback and remaining live-form usability. | Review and accept the new executive visual direction. | Rendered screenshots/browser report now exist; human acceptance remains separate. |
| 3. Human acceptance (F05/F06) | Support the seeded workflow, preserve prior human results accurately and repair new feedback. | Complete the remaining MCP/browser session and explicitly accept the redesign. | Dated client/build record, evidence inspection, Delta controlled failure and decision/KPI consequence. |
| 4. P1 candidate and release (F07/F10) | Candidate assets and exact-commit CI are complete. Promote after the actual human acceptance record is complete. | Accept the executive journey and complete the human MCP/browser session; publication rights are already supplied. | Draft `v0.1.0` targets `31ebfe9` with verified assets; final human acceptance remains open. |
| 5. Optional P2 | Prepare hosting/IdP/budget/teardown and an optional bounded live-model plan before execution. | Choose hosting and authorize specific costs/access if desired. | Deployed synthetic acceptance under F11/F12. |
| 6. P3 production | Execute F13-F16 and applicable remaining acceptance tickets below. | Provide real-company owners/data, reviewers, operating targets, on-call and launch decisions. | Signed domain/security/pilot/operations acceptance. |

The initial gap table below is preserved as audit history; this execution update supersedes its original descriptions of missing implementation and access. The detailed F01-F16 specifications remain the acceptance contract.

## 1. Three explicit finish lines

| Milestone | What finished means | What may remain open |
|---|---|---|
| **P1: Portfolio showcase** | A reviewed release that an unfamiliar person can install and run; working synthetic demo and approval journey; current CI/scans; human MCP session; concise case study, screenshots/video and evidence; clear ownership/license and limitations. | AWS, customer data, external pen test, production on-call and business/legal acceptance can remain clearly labeled future work. Optional model behavior must be labeled unverified unless current live evidence exists. |
| **P2: Hosted synthetic demonstration** | P1 plus an authenticated deployed environment, real browser sign-in, observable services, tested persistence/restart/rollback, controlled access/spend and verified teardown. If advertised as a live-AI demo, current proposer/narrator evaluation also passes. | Real customer integration, production availability claims, external business acceptance and production rollout. |
| **P3: Real-company production release** | Reviewed policy/data handling, real adapters and benchmarks, successful pilot, security/recovery/load acceptance, staffed operations, separate production environment, second-company onboarding and signed launch decision. | Only explicitly accepted noncritical follow-up work with an owner and due date. |

P1 is a legitimate completed portfolio project. P1 does not mean the existing R0.5/R1.0 production acceptance boxes are complete. Recommend finishing P1 first; select P2 when a live service materially strengthens the audience's evaluation. P3 is a business operating commitment.

## 2. Verified baseline and newly identified gaps

The preceding remediation recorded **449 passing tests, one Windows symlink-privilege skip, 39/39 deterministic eval cases, clean lint/types, a wheel/source build, local authenticated multi-process smoke, load tests and a full-table restore drill**. These were local September 27 results preceding the historical candidate CI above. They are not verification of the executive redesign. At that planning point the roadmap contained: **111 tickets: 78 Done, 14 Built, 19 Blocked**. This is the initial audit baseline; candidate remediation subsequently passed the exact-build CI linked above. The new UI requires its own acceptance.

| Gap | Evidence found in this review | Consequence / planned work |
|---|---|---|
| **G01: No published current baseline** | Remediation remains modified/untracked locally; current release CI is pending. | Preserve and review the diff, commit a coherent candidate, run current CI, then release from its verified SHA. F01/F03/F10. |
| **G02: Installed-wheel demo fails** | Reproduced `C:\pvc-audit-20260927\runtime\Scripts\pvc.exe demo --quiet` from outside the checkout: exit 1, `SourceError`, missing `runtime/Lib/tests/fixtures/companies`. `FixtureAdapter.DEFAULT_ROOT` assumes a source checkout. Prior import-only smoke did not exercise this path. | Package supported synthetic assets through package resources, remove demo dependence on checkout layout, and run actual installed demo tests outside the repository. Test container demo too: `run_demo` constructs `FixtureAdapter()` directly. F02. |
| **G03: Container/Compose acceptance missing** | Current image scan and complete Compose profile have not run on a Docker host. Default `.env.example` has no approval token, and Compose loads that file directly. | Establish an exact configuration/seed/start/review/reset path and verify both basic and observability profiles. F04. |
| **G04: Local demo exposure needs tightening** | Compose publishes database, MCP and API ports without a loopback address while loading development authentication/default database credentials. | Bind local-only services to loopback by default; document deliberate remote access separately. This is a configuration exposure, not a reproduced remote exploit. F04. |
| **G05: Automated checks omit infrastructure release checks** | CI runs Python, evals, secret/dependency/image scans, but no Terraform validation/mocks, Actionlint/ShellCheck, promtool, complete Compose smoke or installed-wheel demo. These were manual local checks. | Add repeatable CI jobs for supported checks and retain artifacts. Pin the tools used by those jobs. F03/F04. |
| **G06: GitHub deployment approval entitlement needs a verified choice** | The deployment guide implied Pro/Team was sufficient for private-repository required production reviewers. Current GitHub docs distinguish branch protection from environment required reviewers; the guide is corrected in this planning pass. | Verify actual account/visibility capabilities before purchase/configuration; prove the chosen production approval boundary with a blocked test deployment. Never rely only on `environment: production`. F01/F11. |
| **G07: Human client acceptance absent** | Six examples were replayed by scripts; the recorded September 23 session was not performed by a human. | Fresh tagged/detached client installation, actual human diagnostic/review and a dated record. F06. |
| **G08: Presentation assets absent** | Demo script exists, but no committed screenshots, recording or project case study were found. The script ends with a real-data safety claim stronger than current acceptance supports. | Capture real output, revise narration, write a case study and provide a first-click route through the project. F07/F08. |
| **G09: Browser usability acceptance absent** | API has per-run review and per-company KPI pages; no root/index route appears in the API route list. No browser acceptance record was found. | Provide a discoverable seeded entry point and inspect keyboard, narrow-screen, evidence, loading/error and decision flows. Reuse the existing pages; a new SPA is not a prerequisite. F05. |
| **G10: Release ownership/materials incomplete** | No root license file, changelog, contribution guide or security reporting policy was found. Plugin manifest says `Proprietary`; package and plugin are version `0.1.0`. | You choose publication rights/license; I implement consistent metadata, notices, maintainer instructions, changelog and a versioned release bundle. F09/F10. |
| **G11: Evidence is not a portable release bundle** | Detailed eval JSON, dependency audit and wheels are under `C:\pvc-audit-20260927`; several documents refer to local paths/historical checks. | Attach sanitized reports to a release/CI run, record SHA/image digest/tool versions, remove machine-specific references from the evaluator's path. F07/F10. |
| **G12: Full current live-AI acceptance missing** | Historical live subset tested proposer only; new numeric contract, narrator, negative outcomes and complete usage accounting have not had current provider acceptance. | Run a budgeted synthetic live gate, repair behavior if needed, retain traceable estimated cost and limits. If deferred, label the live path experimental and show the deterministic demo honestly. F12. |
| **G13: Production inputs and operational evidence absent** | Policy/SLO/retention placeholders; no deployed AWS acceptance, real pilot reconciliation, real benchmark approval, human sign-offs or production drills. | Preserve and execute all 33 open PVC tickets through F11–F16 below. |

GitHub policy check on September 27: protected branches are available for public Free repositories and private repositories on supported paid plans. Environment required reviewers on Free/Pro/Team are available only for public repositories. A private production approval design therefore needs a supported enterprise capability or a separately designed, reviewed gate. These are different decisions. Sources: [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [deployment required reviewers](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#required-reviewers). Confirm actual account capabilities at execution; no subscription price or upgrade is assumed here.

## 3. Ordered execution plan: my actions and your actions

The work-package descriptions below preserve the original plan; current completion and remaining work are recorded in the execution update above. Dependencies are explicit to keep account/review waits from blocking independent repository work. Effort estimates are engineering planning ranges, not promises about elapsed agent runtime; revise after the first clean container build.

### F01 — Agree the release boundary and preserve the work

**Required for:** P1/P2/P3. **Depends on:** your audience/visibility decision. **Effort:** small, roughly half a focused workday plus your decision time.

**My actions:** inventory and preserve the existing uncommitted changes; group implementation, infrastructure and docs for review; check tracked/untracked assets; draft a coherent PR description and release checklist. Inspect actual repository/environment permissions when account access is available. Prepare a main-merge strategy that prevents an unconfigured CD run: the current workflow attempts staging and then production on main pushes, so make deployment opt-in/fail-closed before a showcase-only merge. Correct the GitHub entitlement guidance.

**Your actions:** P1-first, the PE executive audience, public Apache-2.0 rights and repository access are already selected. Provide feedback on the new executive journey; no repeat publication-rights or audience decision is required.

**Done when:** scope and publication decision are recorded; no existing work is lost; a concrete change set is reviewable; merging a portfolio release cannot accidentally initiate an unapproved cloud release.

### F02 — Make installation and distribution genuinely reproducible

**Required for:** P1/P2/P3. **Depends on:** none for implementation. **Effort:** medium, roughly 0.5–1.5 workdays.

**My actions:** repair the reproduced fixture-packaging problem using supported package resources; define which commands need the server extra; inspect other checkout-relative paths, including eval data, skill references and benchmarks. Build wheel and sdist, install into a clean environment outside the repository, and exercise `pvc demo`, supported CLI entrypoints and packaged data. Test the documented fresh-clone route separately. Add a meaningful regression that would have caught G02. Confirm report/output paths and repeat-run cleanup behavior.

**Your actions:** identify the primary reviewer platform/client; if no preference is supplied, I will keep Windows and Linux setup documented and verify the supported CI platforms. No credential or cloud account is needed for the synthetic path.

**Done when:** a fresh checkout and the advertised installed distribution each complete the documented synthetic demo without relying on the developer's source tree or state. Any source-only command is clearly identified.

### F03 — Make CI certify the actual release candidate

**Required for:** P1/P2/P3. **Depends on:** F02 for package smoke; F01/access for remote execution. **Effort:** medium, roughly 0.5–1.5 workdays plus runner time.

**My actions:** add installed-package smoke, infrastructure formatting/validation/mock tests, workflow/shell lint and monitoring validation to CI. Keep the PostgreSQL test matrix, migration round trip, skills/snapshots, eval gate, secret audit and strict image scan. Retain machine-readable reports and image identity. Verify the skipped Windows symlink case executes on Linux. Repair failures without silently weakening acceptance. Configure required checks where available and verify nightly deterministic execution after merge.

**Your actions:** provide repository access with the needed settings permissions; make the visibility/plan decision from F01; identify a reviewer if review protection is required. Review the final PR/release candidate. I handle the Git and settings operations once authorized.

**Done when:** fresh checks on the candidate SHA pass; required-check enforcement is demonstrated or its portfolio limitation explicitly recorded; release evidence links to that SHA rather than the historical build.

### F04 — Finish the local container experience

**Required for:** P1/P2/P3. **Depends on:** Docker-capable runtime, F02. **Effort:** medium, roughly 0.5–2 workdays; image findings may add work.

**My actions:** test build, first boot, migrations through `0003`, seeding, readiness and worker execution; make `.env` override behavior explicit; supply a clearly local synthetic approver setup; bind development ports to loopback. Verify approval, rejection, requested changes, evidence links, KPI activation and controlled failures. Restart MCP/worker/database independently and verify expected persistence/recovery. Exercise the observability profile, confirm metrics/traces/alerts reach their local destinations, and document shutdown plus deliberately scoped data reset. Scan the actual release image and operational images used in the demo.

**Your actions:** make a Docker-capable machine or runner available; perform any OS installation/virtualization prompts that require your interaction. Alternatively, provide access to an existing disposable Docker runner; a new always-on cloud stack is not necessary for this gate.

**Done when:** documented commands bring a clean system up, complete the synthetic journey, survive the tested restarts and shut it down. No undocumented terminal edits, missing tokens or hidden fixture files are required.

### F05 - Deliver the executive decision workflow and technical diligence

**Required for:** P1/P2/P3. **Depends on:** F04 for service path; can design earlier. **Effort:** medium, roughly 0.5–1.5 workdays.

**My actions:** implement the requested executive portfolio, plan, evidence and KPI redesign; preserve deeper technical diligence and truthful modeled-value labels. Exercise all existing decision paths and fix financial-scope, history, authorization and error-recovery gaps. Inspect rendered pages in a browser at desktop and narrow widths; check keyboard navigation, labels, empty/error states, long evidence/numeric-reference text and successful/failed form submissions. Make synthetic data and dev authentication clear. Keep technical metadata available without dominating the reviewer journey. Verify that the model cannot approve, unauthenticated approval is rejected and the authorized human path is understandable.

**Your actions:** review the redesigned flow as a PE operating partner or executive, identify confusing decisions or evidence, and explicitly accept or reject the new visual direction.

**Done when:** a reviewer can find a run, understand one evidence-backed value case, make a decision and inspect its KPI consequence without source-code knowledge.

### F06 — Complete an actual human MCP and approval session

**Required for:** P1/P2/P3. **Depends on:** F02 and candidate skill version; F05 for UI portion. **Effort:** short engineering setup plus approximately 30–60 minutes of your active use.

**My actions:** prepare client installation instructions for a reviewed SHA; verify the 22-tool catalog, numeric-reference contract and six skills; provide a session checklist and expected output contract. Observe/debug the session, preserve sanitized evidence and repair any client friction. Separate your actions from scripted setup in the record.

**Your actions:** install/connect the supported MCP client, personally run the diagnostic skill, review a value case and perform the approval/change-request flow. Record your name/date/client version and actual feedback. You can be the portfolio user tester; domain/security expert acceptance is a separate role.

**Done when:** a dated human session meets the output contract, including one controlled failure, and the record accurately attributes who performed it. This closes PVC-070 only when its criterion is met.

### F07 - Build the executive case study and technical evidence pack

**Required for:** P1/P2/P3. **Depends on:** baseline results now; final artifacts after F03–F06. **Effort:** medium, roughly 0.5–1 workday.

**My actions:** lead the case study with the PE operating problem, modeled value, approval decisions and accountable execution. Provide inputs/outputs, deterministic/model boundary, tenancy, tradeoffs, corrected defects and limitations as technical diligence. Show one complete synthetic value case with evidence and one failure/recovery example. Publish reproducible test/eval/load methodology alongside measurements; identify hardware/environment and synthetic costs. Build a release evidence index with commit, package version, image digest, commands and reports. Link detailed internals rather than forcing a reviewer through the handoff first.

**Your actions:** confirm your role/contributions and review the wording about collaboration and outcomes. The PE executive audience is already selected. Supply any real impact evidence you want to claim. Without it, outputs remain simulated opportunities, not realized customer EBITDA or pilot success.

**Done when:** an unfamiliar reviewer can understand the problem and inspect both implementation and measured evidence in a few minutes; all claims have a source and scope.

### F08 — Produce the visual walkthrough and portfolio entry

**Required for:** P1. Also useful for P2/P3. **Depends on:** F05/F07. **Effort:** medium, roughly 0.5–1 workday plus your review/recording.

**My actions:** capture actual application screenshots; revise the existing three-minute script to match current output and remove unsupported real-data safety claims; create a short walkthrough/storyboard and captions. Prepare the portfolio-page copy, repository description, architecture image/diagram and links. Include a static fallback so a reviewer can evaluate the project if no live service is running. I can prepare recording assets and assemble the walkthrough where the environment supports recording.

**Your actions:** record narration/presentation if you want your voice or face; approve attribution, branding and publication destination. Review the final screenshots/video for accidental credentials or private browser content.

**Done when:** the package shows input → findings → deterministic value case → human decision → KPI, plus one controlled failure; no screenshot substitutes invented output for the real application.

### F09 — Establish ownership, reuse terms and maintenance expectations

**Required for:** P1/P2/P3. **Depends on:** your publication/license decision. **Effort:** small.

**My actions:** inventory bundled code/data/assets and third-party notices; align package, plugin and repository metadata with your selected terms. Prepare the license/notice file, concise contribution/setup guidance, security-reporting route and maintenance/support statement. Inventory files/history for secrets or private content before public release; flag any required remediation rather than merely hiding the latest copy.

**Your actions:** choose proprietary/viewable-source or an approved open-source license; confirm rights and any employer/client restrictions; provide the public contact/security-reporting destination. Obtain legal advice if ownership or reuse terms are uncertain. I will not choose an open-source grant on your behalf.

**Done when:** a visitor knows who owns the work, what reuse is permitted, how to report a problem and what support is actually offered.

### F10 — Publish and independently accept the portfolio release

**Required for:** P1/P2/P3. **Depends on:** F01–F09; F12 only if claiming current live-AI acceptance. **Effort:** small to medium plus CI/reviewer time.

**My actions:** synchronize package/plugin versions, write changelog and migration notes, prepare a release tag and checksummed artifacts from the verified candidate, update README navigation and status, and assemble publication changes for your review. After authorized publication, verify all links and repeat the advertised install/demo from a separate directory or machine. Correct broken links/setup before declaring P1 complete.

**Your actions:** approve the concrete publication package and destination; review the portfolio page and actual demo. Confirm the finish-line checklist below. A public launch, repository visibility change or license grant is your decision; I execute the technical publication steps once authorized.

**Done when:** P1 acceptance passes against the released SHA and an independent reviewer can access the intended materials. Production items remain open and discoverable.

### F11 — Provision and validate an authenticated synthetic deployment

**Required for:** P2/P3. **Depends on:** F03/F04, hosting/identity/access/budget decisions. **Effort:** large, typically several engineering sessions; first-apply defects and account waits are uncertain.

**My actions:** prepare region-specific resource/cost estimates, an explicit lifetime/teardown plan and Terraform plan for review before apply. Use the existing AWS design unless you choose another target; a cheaper showcase host is a separate architecture change with its own validation, not proof of the AWS deployment. Configure remote state, DNS/TLS, identity audiences/claims, least-privilege secrets, approved egress and a verified deployment gate. Bootstrap roles, migrate, deploy one scanned digest, provision the dedicated synthetic fixture and run authenticated smoke. Test browser OIDC, negative scope checks, S3/KMS evidence, worker recovery, credential rotation and rollback. Establish health monitoring, budget alerts and restricted demo access. Verify deletion/retention implications before provisioning Object Lock resources.

**Your actions:** choose host/account/region, domain/IdP and demo availability window; approve a concrete spend limit and plan; supply account access securely; create/approve identities as required by the provider; name the person who can approve production deployment. Decide whether the demo is invitation-only or public read-only. Public anonymous model execution requires an additional abuse/spend design.

**Done when:** actual deployed acceptance evidence exists, the access boundary works, operating cost is understood, and teardown/retention steps are tested or explicitly scheduled. Do not publish development tokens or expose dev authentication as the hosted demo.

### F12 — Validate the current live model path

**Required for:** P2/P3 when model reasoning is enabled or claimed as validated. Optional for a clearly labeled deterministic P1. **Depends on:** F03, synthetic provider access and explicit budget; real data additionally requires F13 data-handling approval. **Effort:** medium, with provider-dependent repair risk.

**My actions:** prepare an estimated-cost run plan and stop conditions; run all current golden/adversarial cases using `--proposer model --gate`; exercise proposer and narrator, healthy-company rejection, grounded quantity references, unsupported evidence, injection and provider failure behavior. Record exact model identifier, configuration, accepted/rejected output and token/cache categories. Repair failures and rerun relevant checks. Separate application rate-card estimates from provider billing, and document limits. Keep paid nightly execution opt-in and within the agreed operating budget.

**Your actions:** supply a provider account/API key through the configured secret mechanism; approve the synthetic run budget and the intended model/data policy. Approve recurring scheduled spend separately from a one-time evaluation. No real-company documents enter a model before approved data handling.

**Done when:** the strengthened live gate passes for a recorded model/version and the advertised behavior matches actual output. A failing run produces a repair ticket, not a weakened threshold or a claim based on the old proposer-only subset.

### F13 — Resolve domain, source-data and governance inputs

**Required for:** P3. **Depends on:** named pilot and accountable reviewers; can start while P1/P2 runs.

**My actions:** prepare policy/skill/metric review packets; collect disputed definitions and implement approved versioned changes. Preserve synthetic/demo labels until acceptance. Map pilot datasets, choose the agreed warehouse/CSV/API path, implement missing mappings/adapters, run conformance on approved recorded responses, reconcile financial/billing outputs and resolve entities. Check permitted benchmark use and provenance. Reconcile retention proposals with Terraform Object Lock/log settings. Implement any exclusions/redactions required by provider/security/legal review. Surface finance automation's measured-volume/unit-cost gap instead of inventing savings.

**Your actions:** select the pilot company, source systems and data owners; secure read-only access and permission to use the data; provide authorized finance/domain, security and legal reviewers; select/license benchmark data; nominate approvers and escalation contact; approve policy, data classes, retention and recovery objectives through the relevant accountable people.

**Done when:** every selected source reconciles, domain decisions are signed/versioned, provider/retention terms are accepted and remaining source gaps are explicit. HubSpot/Zendesk simulators do not certify a different vendor or a real pilot feed.

### F14 — Complete operational and independent security acceptance

**Required for:** P3; selected checks also support P2. **Depends on:** F11, approved objectives from F13, named operations/security owners.

**My actions:** connect collector/backend/dashboard/alert routing; generate controlled faults and verify receipt/escalation/recovery. Repeat worker/MCP load on target hardware; exercise restart/lease/failure paths. Perform a timed RDS restore/PITR into a separate instance, check all tenant read/write boundaries and reapply offboarding before service restoration. Verify evidence/version deletion, retained audit and backup expiry against approved policy. Prepare external-test access, fix findings and retain retest evidence. Collect the required two-week staging observation window and report any paging/latency defects.

**Your actions:** appoint the operations/on-call owner and backups; approve alert destinations and actual paging tests; commission the independent security reviewer/tester; approve SLO/RPO/RTO values and residual findings. Participate in an incident/restore tabletop and accept measured results.

**Done when:** objectives have measurements, a test page reaches an accountable person, restore meets approved targets, retention behavior is verified, and critical/high external findings are fixed and retested. The two-week observation period is elapsed time, not an engineering task that can be checked off immediately.

### F15 — Conduct the real pilot and decide whether to provision production

**Required for:** P3. **Depends on:** staging readiness, F12 if using the model, approved source/data/domain/security boundaries from F13 and the required operational checks.

**My actions:** support at least two complete read-only diagnostic runs; retain evidence and human decisions; measure override rate/usefulness and classify disputes as data, calculation, skill or model defects. Fix/retest defects; prepare retrospective, remaining conditions and the production provisioning plan. Do not treat estimated value as realized business benefit.

**Your actions:** have the deal team/operating partner review both runs; provide concrete feedback; sign GO, GO WITH CONDITIONS or NO-GO for provisioning, with named condition owners. This decision does not yet authorize production traffic.

**Done when:** PVC-153/154 have actual pilot evidence and a signed decision, with no unresolved defect hidden by a narrative summary.

### F16 — Validate production and authorize launch

**Required for:** P3. **Depends on:** F15 provisioning decision; remaining F14 conditions must pass before launch.

**My actions:** provision separate production accounts/state/credentials from reviewed IaC; promote the verified artifact through a proven approval gate; test production auth, evidence, backup/restore, egress and rollback; close the owned release conditions. Use the onboarding playbook for a second company and incorporate discovered gaps. Prepare the final evidence index, ownership/runbook handoff and maintenance calendar.

**Your actions:** approve the production plan/spend, arrange second-company access and reviewers, ensure operational staffing, and sign the separate launch authorization after evidence review. Retain a named service owner after launch.

**Done when:** production conditions and second-company onboarding pass, launch is signed, and ongoing access/dependency/eval/restore reviews have owners. This is the point at which P3 and the applicable R1.0 gate can close.

## 4. Original crosswalk of the 33 open repository tickets

This crosswalk preserves the ticket gaps when the plan was created; subsequent candidate evidence and the current execution update above supersede completed publication/container/CI tasks. It is not a freshly counted list of open tickets. These ticket scopes are distinct from the new executive design acceptance. “You” can designate an accountable specialist; it does not mean you must personally be the legal, finance and security reviewer.

| PVC | State at original planning | Original remaining action | Original owner input | Plan / gate |
|---|---|---|---|---|
| 001 | Blocked | Configure and verify main protection. | Visibility/plan/access decision. | F01/F03; P1 |
| 006 | Blocked | Run current CI and enforce required checks. | Settings access; accept review rules. | F03; P1 |
| 030 | Built | Execute Compose database and migration acceptance. | Docker-capable environment. | F04; P1 |
| 055 | Blocked | Implement/version approved screening and policy values. | Operating-team sign-off. | F13; P3; demo remains labeled |
| 070 | Blocked | Prepare/debug/record current human MCP session. | Personally use the skill and review output. | F06; P1 |
| 071 | Blocked | Incorporate expert review of all lever skills. | Domain expert and signed review. | F13; P3 |
| 072 | Built | Run full current live proposer/narrator gate and fix failures. | Provider secret and bounded spend approval. | F12; live-AI claim |
| 083 | Blocked | Require eval check and verify actual nightly execution. | Repository permissions; opt in to paid nightly separately. | F03/F12 |
| 090 | Blocked | Update threat model with deployment and residual-risk evidence. | Independent security/owner review. | F13/F14; P3 |
| 093 | Built | Verify deployed secret injection/rotation and current secret scan. | Account access and secret provisioning. | F03/F11; P2/P3 |
| 094 | Built | Test deployed allow/deny egress including SDK/telemetry paths. | Approve required destinations. | F11/F16; P3 production scope |
| 096 | Built | Scan current image/dependencies and preserve digest/report. | Docker/runner availability; no blanket exception assumed. | F03/F04; P1 |
| 097 | Blocked | Prepare test target; fix and retest findings. | Commission third-party test and accept report. | F14/F16; P3 |
| 103 | Built | Deploy telemetry, inject faults, verify alerts and observe. | Select backend/routing and recipients. | F04 local; F14 deployed |
| 110 | Blocked | Pilot source architecture/mapping and recorded-data conformance. | Choose company/systems; obtain access. | F13; P3 |
| 111 | Blocked | Load/reconcile actual monthly financials with evidence. | Finance data owner and approved read-only data. | F13; P3 |
| 113 | Blocked | Load/reconcile actual invoices/subscriptions/price books. | Billing access and mapping review. | F13; P3 |
| 116 | Blocked | Ingest approved peers with provenance/privacy checks. | Choose/approve dataset and reuse rights. | F13; P3 |
| 130 | Built | Build/scan/start complete image stack. | Docker-capable environment. | F04; P1 |
| 131 | Built | Plan/apply and validate staging IaC. | Account/region/cloud choice and spend approval. | F11; P2/P3 |
| 132 | Built | Validate deployed RDS encryption, roles, backups and TLS. | Account access and recovery requirements. | F11/F14; P2/P3 |
| 133 | Built | Run exact-SHA CI→scan→deploy→smoke; prove production gate. | Supported approval capability and reviewer. | F11/F16; P2/P3 |
| 135 | Built | Prove TLS/OIDC/routing/rate/body limits in target environment. | Domain/certificate/IdP setup access. | F11; P2/P3 |
| 136 | Built | Provision isolated production and validate. | Signed provisioning decision and budget. | F16; P3 |
| 140 | Blocked | Measure accepted SLO/RPO/RTO targets. | Operating/operations approval of targets. | F13/F14; P3 |
| 142 | Built | Execute timed RDS recovery and tenant revalidation. | Recovery objective acceptance/drill authorization. | F14/F16; P3 |
| 143 | Built | Run target concurrency and document bottlenecks/fixes. | Agree workload and provide staging capacity. | F14; P3 |
| 144 | Blocked | Align configuration with policy; test deletion/retention. | Legal/operations approval of periods and legal basis. | F13/F14; P3 |
| 147 | Blocked | Implement accepted model-data controls and evidence. | Legal/provider data-processing approval. | F13; before real-data model use |
| 148 | Blocked | Configure routes/runbooks and conduct controlled exercises. | Named rotation, backups and response commitment. | F14; P3 |
| 153 | Blocked | Support two real pilot runs and repair disputes. | Pilot team participation and human reviews. | F15; P3 |
| 154 | Blocked | Prepare retrospective and owned provisioning conditions. | Signed GO/conditional GO/NO-GO. | F15; P3 |
| 155 | Blocked | Execute/refine playbook with second company. | Second-company access, team and approvers. | F16; P3 |

Additional conditional scope: a pilot using Salesforce or an unsupported finance/product system may need a new adapter. Finance automation requires measured process volume/unit cost. These are source-dependent implementation gaps, not prerequisites to finishing the synthetic portfolio showcase.

## 5. Your decision and access checklist

| When needed | What you supply or decide | What I prepare/do with it |
|---|---|---|
| Current direction | P1-first; PE operating partners and executives primary, technical diligence available. | Implement and verify the redesign; preserve P2/P3 as follow-on gates. |
| Before publication | Public/private source, license/ownership, name/contact and destination. | Produce reviewable notices, release, case study and publishing changes. |
| For current release CI | Repository/settings access and chosen protection route. | Configure/check CI, required checks and safe CD activation. |
| For local runtime | Docker-capable host/runner. | Install/configure where permitted, run the stack, fix integration and retain evidence. |
| During P1 acceptance | 30–60 minutes for a real client/review session; publication review. | Provide script, setup, expected output and repair support. |
| Only for live AI | Provider secret, approved one-time budget; separate recurring budget choice. | Prepare and run bounded synthetic eval, report results and usage. |
| Only for hosting | Account/region/domain/IdP, availability window, approved cost and access. | Present a concrete plan/cost/teardown package, then deploy and verify after authorization. |
| Before real pilot | Company/data owners/read-only access; named finance/security/legal reviewers; approved benchmarks and approvers. | Source integration, reconciliation, control changes and reviewer packets. |
| Before production | On-call ownership, independent test, provisioning and launch decisions. | Drills, retests, production configuration and final evidence bundle. |

Supply credentials through the existing secret manager or local ignored configuration, not in the roadmap or a public issue. I will ask for the specific missing item when it becomes the next dependency; you do not need to gather all production inputs to begin P1.

## 6. Suggested sequence and planning horizon

| Work block | My parallelizable work | Your action during the block | Exit |
|---|---|---|---|
| A: Candidate foundation | F01–F03: preserve diff, repair installed demo, extend CI, draft release controls. | Choose audience/visibility; enable repository and Docker access. | Reproducible candidate and current checks. |
| B: Reviewer journey | F04–F06: container flow, browser walkthrough, human-client support. Draft F07/F09 concurrently. | Perform actual user session; choose license/contact. | Usable end-to-end synthetic experience. |
| C: Portfolio release | F07–F10: evidence pack, visuals, case study, publication candidate and independent install check. | Review narration/claims and approve publication. | **P1 complete.** |
| D: Optional hosted/live proof | F11/F12 after credentials/budget; prepare F13 review packets in parallel if P3 is intended. | Hosting/IdP/model choices and bounded budget. | **P2 complete** for chosen scope. |
| E: Business acceptance | F13 source/domain/governance work, F14 operations/security, F15 pilot. Start staging observation once instrumentation is stable. | Reviewers, real data, actual pilot participation and provision decision. | Pilot accepted with owned production conditions. |
| F: Production acceptance | F16 plus remaining F14 conditions and second-company onboarding. | Production and launch decisions; operational ownership. | **P3 complete.** |

P1 planning allowance: approximately **4–8 focused engineering workdays**, with tasks overlapping, plus access and human-review waits. This is a scope estimate rather than a promised delivery date; new image/Compose/client failures may change it. P2 needs a separate estimate after the hosting/cost decision. P3 cannot be dated responsibly before pilot data and reviewers are assigned, and includes the existing **two-week staging observation** requirement plus external review/pilot elapsed time. Adding task estimates is not a calendar forecast.

Critical path for P1: reproducible package → current CI/container proof → human/browser acceptance → approved case study/assets/license → release and independent installation. Cloud provisioning is not on that path. For P3, account/IdP decisions, real data, specialist review and elapsed operational/pilot evidence become the limiting dependencies.

## 7. Acceptance checklist and evidence locations

For each completed item, record owner, date, exact SHA/version, command or session, result, evidence link and any residual issue. The versioned evidence index links the completed engineering work; human evidence remains pending.

**P1 portfolio release:**

- [x] Installed-wheel demo and fresh-clone instructions pass outside the development checkout.
- [x] Historical candidate `9f9b95f` passed CI, strict release-image scan and Linux symlink coverage with retained reports.
- [x] Local research-candidate regression passes: 498 tests, one Windows symlink-privilege skip, with PostgreSQL enabled.
- [x] Candidate `31ebfe9` passes exact-SHA CI and artifact scans: 499 tests per Linux Python version, 39 evaluations, 18 browser checks and clean application/database scans.
- [x] Clean Compose startup/migration/seed/approval/KPI/restart/shutdown sequence passes.
- [x] Six captured pages pass rendered desktop/tablet/mobile, overflow, skip-link and disclosure checks in isolated Chromium.
- [ ] The human accepts the redesigned executive workflow and completes the remaining MCP/browser session.
- [x] Actual current-design screenshots and a machine-readable browser report are available.
- [ ] Final case study/walkthrough and release assets receive human acceptance.
- [x] README leads directly to the demo, architecture, evidence, limitations and release.
- [x] License/ownership, security reporting, setup/contribution guidance and changelog are consistent.
- [ ] Release tag, package/plugin version and artifact checksums identify the reviewed code.
- [x] Your publication approval and a detached-checkout/isolated-wheel install check are recorded (agent-performed; independent human acceptance remains above).
- [x] Synthetic/model/production boundaries are accurate; no realized ROI, legal acceptance or production claim is fabricated.

**P2 additional acceptance:** deployed auth/browser OIDC, scoped smoke, storage/KMS, worker recovery, dashboards, rollback, current model gate if enabled, controlled access/spend and lifecycle/teardown evidence.

**P3 additional acceptance:** every applicable row in the 33-ticket crosswalk satisfies its original acceptance criterion; domain/legal/security decisions are signed; pilot and second-company evidence exist; measured operations/recovery meet approved targets; launch is separately authorized.

Suggested deliverables: `docs/portfolio/case-study.md`, `docs/portfolio/media/`, `docs/portfolio/acceptance.md`, a dated `docs/skill-sessions/` human record, and `docs/releases/<version>/evidence.md` pointing to retained CI/release artifacts. Existing source-of-truth records remain [ROADMAP.md](../ROADMAP.md), [deployment](deployment.md), [SLOs](slo.md), [retention](data_retention.md), [threat model](threat_model.md), [model handling](model_data_handling.md) and the [pilot documents](pilot/).

## 8. Immediate next work

The verified candidate and release evidence are assembled. Alex next reviews the executive design, completes the remaining actual MCP/browser session and accepts the case study/walkthrough. Engineering addresses that feedback and promotes the existing verified draft after the acceptance record is complete. Earlier human decisions do not stand in for review of the redesigned flow. Publication rights and the implementation direction are already supplied. The separate research pilot needs independent financial review and peer acceptance. Production remains scheduled after the showcase with the owner inputs in sections 4-6.
