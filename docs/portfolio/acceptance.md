# Portfolio acceptance record

Primary audience confirmed by Alex: technical hiring managers and applied-AI leaders. Showcase first; production acceptance remains a separate milestone.

## Engineering evidence

All ten CI jobs passed at `9f9b95f`: 453 tests per Python version, full evaluations, installed-package and Compose smoke, infrastructure and clean application/database scans. See [the versioned evidence index](../releases/0.1.0/evidence.md), [container acceptance](../container-acceptance.md), [audit remediation](../audit-remediation.md) and [the execution roadmap](../portfolio-finalization-roadmap.md). The current work remains a candidate until the remaining gates below are complete.

## Human session — partially performed

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
| Desktop / narrow-screen / keyboard usability | Pending |
| Feedback and repairs | Invalid-token error recovery fixed and verified; additional session feedback pending |

Suggested client prompt: “Use the PE value creation diagnostic skill for beacon-pricing. Cite tool evidence, distinguish modeled opportunity from realized results, and stop at human approval.” Then repeat for `delta-broken` to inspect missing-data handling.

Initial human feedback exposed an unhelpful raw JSON response for an invalid local token. The saved token matched the running API and succeeded in an HTTP check; Alex subsequently confirmed successful browser sign-in. The fix keeps unsuccessful sign-in on the HTML form, renews its CSRF challenge, explains token retrieval and ignores surrounding paste whitespace. It passed all ten CI checks in [run 36361279297](https://github.com/ahines99/pe-value-creation-os/actions/runs/36361279297) and merged in PR #10.

Alex then supplied Beacon's plan review with the recorded approval. The pasted page still showed `awaiting_approval`, reflecting its state before the worker completed. A subsequent read-only check found the run complete with its approved plan, five active KPI definitions and five fixture-derived observations. [The recorded repository evidence](human-approval-evidence.json) ties those results to this run; prior automated approvals of other runs are not counted as Alex's session. This establishes the browser decision and engineering verification of its consequence, not completion of the pending MCP, evidence-link or usability checks.

## Publication and ownership

Alex confirmed publication rights and authorized a public Apache-2.0 release. The repository is now public, with a [portfolio site](https://ahines99.github.io/pe-value-creation-os/). LICENSE, NOTICE, package, plugin and image metadata are aligned. Main requires all ten checks with administrator enforcement; private vulnerability reporting is enabled. Secret scans of history and the publication candidate passed. Domain sign-off, security certification and launch approval remain independent gates.

## Current interaction limitation

The browser connector exposes no surfaces. An earlier native Chrome attempt stopped because Computer Use could not determine its URL reliably. After Alex opened the workspace in VS Code's integrated browser, native inspection successfully exposed the rendered workspace and its accessibility tree. Input targeting then failed, and a later attempt detected Alex's active input; the preview was left under Alex's control. No IDE screenshot containing unrelated panels is published. Clean portfolio screenshots, keyboard/narrow-screen inspection and the remaining human MCP session are still pending.
