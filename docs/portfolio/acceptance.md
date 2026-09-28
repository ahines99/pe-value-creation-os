# Portfolio acceptance record

Current primary audience: PE operating partners and portfolio-company executives. Technical reviewers retain access to assumptions, evidence, contracts and engineering diligence. This supersedes the earlier hiring-manager/applied-AI positioning. Showcase acceptance and production acceptance remain separate milestones.

## Current redesign acceptance (open)

Alex explicitly rejected the previous visuals and requested a substantial redesign plus functionality review. The current implementation introduces a portfolio decision desk, executive plan briefs, workstream contribution views, governed approve/reject/change-request forms, escaped evidence previews and historical/current operating scorecards. Technical detail is available without dominating the executive decision path.

The combined API, executive UI and independent portfolio integration suites passed **39 tests**, and the deterministic gate passed **39/39 cases**. The full local Windows suite passed **478 tests, with one symlink-privilege skip, in 176.21 seconds**, using PostgreSQL through an isolated disposable test database. Ruff checks across 135 files and mypy checks across 90 source files passed. These results cover the current worktree and are not a new CI or release certification. [The functional audit](executive-functional-audit.md) describes the tested invariants and limits. These HTTP/domain results do not establish visual quality or human acceptance.

- [x] Inspect rendered public landing, portfolio, Beacon review, Delta, evidence and KPI captures at desktop/narrow widths in isolated Linux Chromium.
- [x] Verify skip-link focus and native disclosures by keyboard; repair the main-focus target.
- [ ] Complete human login/decision-form keyboard and error-recovery usability review.
- [x] Capture authentic screenshots of the six rendered pages; retain the page/viewport report.
- [ ] Obtain Alex's acceptance of the new executive visual direction and complete the remaining human MCP/browser session.
- [x] Complete the current-worktree local regression: 478 passed, one Windows symlink-privilege skip; PostgreSQL enabled.
- [ ] Attach successful exact-build CI/release evidence before promotion.

Read-only checks against the running local Docker stack returned HTTP 200 and `Cache-Control: no-store` for the portfolio, approved Beacon review, exact-run KPI page, Delta review and evidence preview. Local links and anchors were validated across 15 HTML captures. These captures are application output, not screenshots.

## Rendered evidence

Isolated Linux Chromium 153.0.8010.12 in Docker passed **18 checks: six pages at 1440, 768 and 375 pixels**. There was no horizontal overflow with disclosures collapsed or expanded. Keyboard checks verified skip-link focus and native disclosure activation; the main element was made focusable to fix the skip-link target. The coordinator inspected screenshots of the workspace, Beacon memo, mobile views, evidence, Delta, KPIs and public landing.

See [browser-checks.json](screenshots/browser-checks.json), [desktop workspace](screenshots/workspace-1440.png), [mobile workspace](screenshots/workspace-375.png), [plan memo](screenshots/memo-1440.png), [evidence detail](screenshots/memo-evidence-detail.png) and [operating performance](screenshots/performance-1440.png). These are rendered application captures, not mockups. They do not record a new human approval or a live browser decision.

The native Windows connector remains unreliable, but it no longer blocks rendered testing. Human acceptance of the new design and the remaining MCP session are still pending. The new PR's ten CI checks are pending; no final release is recorded.

## Historical exact-build engineering evidence

All ten CI jobs passed at `9f9b95f`: 453 tests per Python version, full evaluations, installed-package and Compose smoke, infrastructure and clean application/database scans. See [the versioned evidence index](../releases/0.1.0/evidence.md), [container acceptance](../container-acceptance.md), [audit remediation](../audit-remediation.md) and [the execution roadmap](../portfolio-finalization-roadmap.md). These historical results remain tied to that candidate; they do not certify the redesigned worktree. The current work remains a candidate until the redesign gates above and the remaining human gates below are complete.

## Historical human session (partially performed)

Do not mark this complete based on automated tests or an agent-authored walkthrough.

| Field | Actual result to record |
|---|---|
| Participant / date | Alex, September 27, 2026 (America/New_York): browser sign-in and Beacon approval demonstrated; full MCP session pending |
| Local browser sign-in | Passed: Alex confirmed the saved token worked and supplied the authenticated workspace output showing Beacon awaiting approval and Delta needing evidence |
| Reviewed commit / client version | Pending |
| Install plugin from detached checkout | Pending |
| Run diagnostic skill against Beacon | Pending |
| Verify all eight diagnostic output sections and cited evidence | Pending |
| Inspect one deterministic value case and its assumptions | Pending |
| Review and approve or request changes in the browser | Passed: Alex supplied Beacon's review page with a recorded approval by `human:showcase`; run `b799f792-3a31-4808-ae8a-890918201b66` |
| Observe worker resume and KPI consequence | Agent verified `complete`, an approved plan, five active KPIs and five fixture-derived observations for this exact run; Alex's own KPI inspection is still pending |
| Inspect Delta controlled failure | Pending |
| Desktop / narrow-screen / keyboard usability | Engineering Chromium viewport/skip-link/disclosure checks passed; human live-form usability remains pending |
| Feedback and repairs | Earlier invalid-token recovery was fixed. Alex rejected the old visuals; substantial executive redesign and functional repairs are implemented, with rendered Chromium checks passed and human new-design acceptance pending |

Suggested client prompt: “Use the PE value creation diagnostic skill for beacon-pricing. Cite tool evidence, distinguish modeled opportunity from realized results, and stop at human approval.” Then repeat for `delta-broken` to inspect missing-data handling.

Initial human feedback exposed an unhelpful raw JSON response for an invalid local token. The saved token matched the running API and succeeded in an HTTP check; Alex subsequently confirmed successful browser sign-in. The fix keeps unsuccessful sign-in on the HTML form, renews its CSRF challenge, explains token retrieval and ignores surrounding paste whitespace. It passed all ten CI checks in [run 36361279297](https://github.com/ahines99/pe-value-creation-os/actions/runs/36361279297) and merged in PR #10.

Alex then supplied Beacon's plan review with the recorded approval. The pasted page still showed `awaiting_approval`, reflecting its state before the worker completed. A subsequent read-only check found the run complete with its approved plan, five active KPI definitions and five fixture-derived observations. [The recorded repository evidence](human-approval-evidence.json) ties those results to this run; prior automated approvals of other runs are not counted as Alex's session. This establishes the browser decision and engineering verification of its consequence, not completion of the pending MCP, evidence-link or usability checks.

## Publication and ownership

Alex confirmed publication rights and authorized a public Apache-2.0 release. The repository is now public, with a [portfolio site](https://ahines99.github.io/pe-value-creation-os/). LICENSE, NOTICE, package, plugin and image metadata are aligned. Main requires all ten checks with administrator enforcement; private vulnerability reporting is enabled. Secret scans of history and the publication candidate passed. Domain sign-off, security certification and launch approval remain independent gates.

## Current interaction limitation

The browser connector exposes no surfaces. An earlier native Chrome attempt stopped because Computer Use could not determine its URL reliably. After Alex opened the workspace in VS Code's integrated browser, native inspection successfully exposed the rendered workspace and its accessibility tree. Input targeting then failed, and a later attempt detected Alex's active input; the preview was left under Alex's control. No IDE screenshot containing unrelated panels is published. Engineering visual checks were performed separately in isolated Linux Chromium in Docker, as recorded above. The human MCP session and live interaction acceptance remain pending.


The earlier sign-in and Beacon decision are retained as actual historical actions. They are not acceptance of the new visual system, other runs, or the unfinished MCP/keyboard/narrow-screen checks. Do not close the redesign based on those prior actions or on captured HTML alone.
