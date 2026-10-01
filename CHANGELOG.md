# Changelog

## 0.2.0 — 2026-09-30 (tag `v0.2.0`)

Everything merged since `v0.1.0` (PRs #14 to #61).

**Public and constructed diligence**
- Public Progress Software diligence: earnings reconciliation, quarterly and peer views, restatement comparison, acquisition vintages and a historical valuation bridge, with unsupported measures withheld.
- Constructed underwriting, capacity scheduling, case revisions with lineage, and the realization and attribution ledger.
- Permissioned private chain (PRs #41 to #51): processing grants, intake, financial snapshots, underwriting, capacity plans, reviewed baselines, observations, execution, attribution with separate finance review, and the executive review screen.

**Fixes from the September 30 reviews (PRs #53 and #54)**
- Recurring costs must be posted for every month through the horizon; a single row is rejected instead of silently understating later months.
- Approving with every initiative removed, or requesting changes that exclude every initiative, is refused.
- KPI readings for periods before a plan started are shown and treated as baselines, not progress, on the KPI page, in alerts, in the daily digest and in the demo summary.
- Browsers get sign-in or an HTML error page instead of raw JSON; JSON decisions and case writes require an explicit bearer token, with no fallback from an empty header to the browser session; the production ALB sign-in rule covers `/`.
- The decision desk counts earlier assessments that still await a decision.
- Money rounds half-up with consistent whole-unit and compact formats; identifiers, segment names, evidence-gap text and screening reasons read as text.

**Maintenance**
- PyJWT 2.15.1 (CVE-2026-101918) and batched dependency and GitHub Actions updates (#61).
- A nightly dependency audit on `main`; broader `.gitignore` coverage for credentials and Terraform variables.
- The project MCP configuration starts outside the plugin loader.
- Shared helpers replace duplicated record-chain and repository logic.
- One current status file, `docs/STATUS.md`; roadmap tickets closed from CI evidence or recorded as won't-do for portfolio scope.

This is not a production acceptance or realized financial-impact claim. Nothing is deployed beyond the static site, and no company pilot has run.

## 0.1.0 — 2026-09-28 (tag `v0.1.0`)

- Executive PE workspace: current portfolio priorities, investment memos, scenario and evidence disclosures, human decision controls, and plan-specific operating scorecards.
- Approval receipts and edited totals update immediately; form recovery retains reviewer input; historical KPI views preserve their approved plan scope.
- Public application captures and genuine Chromium screenshots, with desktop/tablet/phone rendering and keyboard checks in CI.
- Evidence-backed portfolio diagnostics, deterministic low/base/high value cases and human-reviewed 100-day plans over synthetic company fixtures.
- Durable workflow checkpoints, controlled missing-evidence and failure paths, approval decisions, KPI activation and tenant-scoped repositories/MCP tools.
- Audit remediation for numeric grounding, model usage accounting, source handling, approval state, evidence boundaries, worker claims, deployment promotion and operational verification.
- Installed-package fixture/evaluation assets, out-of-checkout smoke checks and a scanned Alpine application image.
- Local Docker showcase setup, browser sign-in/workspace, isolated demo tokens and loopback-only services.
- Infrastructure validation in CI and explicit cloud-delivery opt-in.
- Apache-2.0 licensing and portfolio review/maintenance documentation.

This is not a production acceptance or realized financial-impact claim. Current limitations and outstanding human/deployment gates are recorded in the portfolio roadmap.
