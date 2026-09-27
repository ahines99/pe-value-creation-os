# Portfolio acceptance record

Primary audience confirmed by Alex: technical hiring managers and applied-AI leaders. Showcase first; production acceptance remains a separate milestone.

## Engineering evidence

All ten CI jobs passed at `48459ba`: 453 tests per Python version, full evaluations, installed-package and Compose smoke, infrastructure and clean application/database scans. See [the versioned evidence index](../releases/0.1.0/evidence.md), [container acceptance](../container-acceptance.md), [audit remediation](../audit-remediation.md) and [the execution roadmap](../portfolio-finalization-roadmap.md). The current work remains a candidate until the remaining gates below are complete.

## Human session — awaiting actual performance

Do not mark this complete based on automated tests or an agent-authored walkthrough.

| Field | Actual result to record |
|---|---|
| Participant / date | Pending |
| Reviewed commit / client version | Pending |
| Install plugin from detached checkout | Pending |
| Run diagnostic skill against Beacon | Pending |
| Verify all eight diagnostic output sections and cited evidence | Pending |
| Inspect one deterministic value case and its assumptions | Pending |
| Review and approve or request changes in the browser | Pending |
| Observe worker resume and KPI consequence | Pending |
| Inspect Delta controlled failure | Pending |
| Desktop / narrow-screen / keyboard usability | Pending |
| Feedback and repairs | Pending |

Suggested client prompt: “Use the PE value creation diagnostic skill for beacon-pricing. Cite tool evidence, distinguish modeled opportunity from realized results, and stop at human approval.” Then repeat for `delta-broken` to inspect missing-data handling.

## Publication and ownership

Alex confirmed publication rights and authorized a public Apache-2.0 release. LICENSE, NOTICE, package, plugin and image metadata are aligned. Secret scans of history and the publication candidate passed. Domain sign-off, security certification and launch approval remain independent gates.

## Current interaction limitation

The browser connector exposed no surfaces. A native Chrome fallback was discovered, but Computer Use stopped because it could not determine the current Windows browser URL reliably enough to enforce policy. No further UI input was issued after that stop. HTTP acceptance and captured read-only HTML are available; rendered screenshots, keyboard/narrow-screen inspection and the actual human session remain missing evidence.
