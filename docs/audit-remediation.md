# September 27 audit remediation

> **For current status, see [STATUS.md](STATUS.md).** This file is kept as the September 27 audit remediation ledger; where it differs from STATUS.md, STATUS.md is right.

This ledger records implementation and verification after the repository audit of commit `0ad7e7fa380aeed38b12794c370651de7497575c`, on branch `build/roadmap`. Five specialist implementation agents worked in two waves, with coordinator integration and independent checks. The work is local and uncommitted; no push, merge, AWS apply, production deployment or paid model evaluation was performed.

All 23 numbered audit findings have code or configuration remedies. A clean runtime build exposed a further dependency defect, A24, which was also fixed. Local regression evidence and target-environment acceptance are distinct: infrastructure configuration and simulated model tests do not certify a production deployment or a live model.

## Finding closure ledger

| Finding | Implemented remedy | Verification / remaining acceptance |
|---|---|---|
| A01: CSV path escape and rejected foreign evidence | Canonical tenant IDs, resolved path confinement, tenant validation of every raw row before parsing, and staged publication across all datasets. Fixture and warehouse ingestion follow the same isolation rule. | Security regressions cover traversal, malformed foreign rows and rejection after an earlier valid dataset. Windows symlink creation is privilege-limited; the symlink case remains covered for CI on Linux. |
| A02: interactive MCP bypasses business validation | Proposal, draft and submission share sufficiency, eligibility, freshness, citation, numeric-claim and overlap checks. Duplicate/overlapping opportunities are explicitly rejected. Aggregate ARR contains its pricing sub-baselines. | MCP and model-remediation regressions; tool schema updated to 22 tools. |
| A03: row-order-dependent discounted ARR | Compute latest invoice periods at customer/product grain, aggregate split lines, then gross up the matching ARR. Unmatched positive ARR and fully discounted positive ARR fail explicitly. | Permutation, split-line, future-period and unavailable-baseline tests. |
| A04: repeated changes create endless rewinds | Persist consumed approval IDs and create a fresh pending request for every review round, even when plan content and comments repeat. | Three identical consecutive changes pause once each and produce four distinct requests, on memory and PostgreSQL repositories. |
| A05: queued leases and stale-owner writes | Sequential workers claim one immediately executable job. Every attempt has a unique owner; repository operations check and lock current ownership/freshness. Heartbeat failure cancels the running attempt. | Memory/PostgreSQL stale-write, wrong-owner release, capacity and cancellation regressions. |
| A06: permissive model gate/eligibility | Model and interactive proposals must pass deterministic policy screening. Evaluation includes negative outcomes and precision, rather than counting any proposal as success. | Healthy-company and unsupported-proposal rejection tests; live model acceptance remains open. |
| A07: ALB cannot reach OIDC provider | Explicit outbound HTTPS for ALB OIDC token and user-info exchange. | Terraform configuration and mocked assertions; actual IdP login requires staging. |
| A08: ECS starts before ALB attachment | Services depend on listener/rule creation. | Terraform validation/mocked assertions; first AWS apply remains open. |
| A09: OTel exports raw exception content | Disable automatic exception events/status descriptions; record exception type only. | Exported-span regression checks that secret message, stack and status text are absent. |
| A10: numeric guardrail lexical/provenance gaps | Typed source quantities bind metric, value, unit, company, period and evidence. Models use `{{quantity:KEY}}` references rendered by the server. Arbitrary document strings/IDs cannot authorize values; scientific notation and leading decimals are checked. | Guardrail, source-catalog and narrator-injection regressions. This restricts quantitative prose; it does not claim semantic proof of all qualitative statements. |
| A11: initiatives without KPIs | Complete KPI mapping for every supported lever/baseline pair; approval requires a monitorable KPI for every initiative. | Registry-wide parametrized coverage and missing-KPI approval rejection. |
| A12: multi-product renewals missed | Renewal comparisons run independently per customer/product and aggregate same-date split invoice lines. | Multi-product renewal permutation regression. |
| A13: duplicate digest every tick | Stable daily/content notification identity, persisted delivery claims and delivered-state deduplication across workers. | Retry, repeated tick, replica and next-day tests on both repositories. |
| A14: escalation marked before delivery | Mark escalation after delivery acknowledgment; retain failed messages for retry. Webhooks receive stable idempotency keys. | Failure-then-success regression. Delivery is at least once; a destination must honor the key to prevent a duplicate after send-before-ack crashes. |
| A15: crashed RUNNING jobs never reclaimed | Reclaim expired running leases as well as queued work; reject expired-owner renewal and writes. | Memory/PostgreSQL expiration and replacement-owner regressions. |
| A16: deployment can select an older unscanned artifact | Content-address ECR tags by the scanned image ID, bind saved artifacts to the build run/attempt, verify loaded/pulled image identity, and require the production manifest digest to match staging. | Shell tests and static validation; real ECR promotion remains open. |
| A17: CD races CI | Release workflow waits for successful CI on the exact main-branch SHA before building/deploying. | Workflow lint and mocked gate scenarios. Repository required checks/environment reviewers still need configuration. |
| A18: health/smoke misses dependency failures | Separate `/readyz` probes for database schema/runtime privileges/forced RLS and evidence reachability. Non-dev wiring requires a database. Worker heartbeat checks process and age. Authenticated synthetic smoke checks MCP, evidence, worker pause, API review/decision and resume. | Readiness regressions and runtime import smoke. Live smoke requires scoped tokens and a deployed synthetic tenant; S3 readiness lists a permitted prefix, while smoke verifies actual evidence I/O/KMS. |
| A19: validation scripts change shared role passwords | Tests/load/restore scripts create disposable login roles inheriting `pvc_app`; migration round trip uses a unique disposable database and requires an explicit test URL. | Isolated PostgreSQL tests, migration round trip and restore drill; no shared role password reset. |
| A20: live eval omits narrator; nightly does not gate all cases | Model-mode harness uses proposer and narrator. Nightly runs `--suite all --proposer model --gate` with usage, behavior and narrator metrics. | Offline evaluator/narrator tests and full deterministic gate. Historical proposer-only live reports are explicitly qualified; a fresh paid run remains open. |
| A21: model cost omits caches/retries/rejections | Per-call scoped durable audit includes normal input, cache reads, cache creation including one-hour cache, output, narrator and rejected responses. Missing pricing/usage fails the gate. | Usage and concurrent-scope tests. Dollar totals are rate-card estimates, not provider invoice reconciliation. |
| A22: incomplete load/restore acceptance | Load reports include step percentiles; restore seeds every tenant table, compares every public table and tests scoped reads/writes plus append-only audit grants. | Fresh local load/restore results below. Target hardware, RDS PITR and real RPO/RTO remain open. |
| A23: empty eval gate succeeds | Empty selections, unknown cases and absent required score fields fail closed. | Evaluator regressions. |
| A24: server-only package cannot import HTTP entrypoints | Declare `httpx` in the HTTP runtime extra instead of relying on the development extra; refresh lockfile and add container entrypoint import smoke. | Fresh isolated server-only dependency installation and wheel import checks; local Docker is unavailable. |

## Additional audit concerns

- **Snapshot consistency:** source data are serialized once into immutable evidence, referenced by hash from checkpoints and restored with typed contracts; policy is pinned in run state. Normal resume does not re-read a changed export. `pvc resume RUN --refresh-inputs --reason ...` creates a new linked run and preserves the original evidence and decisions. Legacy checkpoints with an inline snapshot remain readable.
- **Approval atomicity:** decision, durable resume enqueue, audit, plan finalization and interactive KPI activation use one repository transaction. Tests inject failure after KPI writes and verify complete rollback before a successful retry.
- **Edited plans:** removing an initiative removes its KPIs, risks, milestone entries, dependencies and approval text; stale narrative is discarded and totals recomputed.
- **Transport and identity:** canonical IDs reject separators/ambiguous scope strings, JWT arrays are shape-checked, JWKS redirects pass through checked HTTP, and credentialed vendor pagination cannot switch origin. AWS SDK/OTel transport exceptions and infrastructure controls are documented explicitly.
- **Evidence races:** S3 original writes use conditional creation; a concurrent winner is checked for identical content. Bucket policy permits default KMS encryption when headers are absent and rejects explicitly non-KMS uploads; the normal application path supplies the configured KMS key.
- **Document privacy:** `PVC_MODEL_DOCUMENT_EXCLUDED_COMPANIES` excludes management documents from prompts for selected tenants or `*`; it is an operator configuration control, not a replacement for legal/provider review.
- **Operational monitoring:** a Compose observability profile supplies collector, Prometheus, Grafana, Tempo and Alertmanager configuration; production TLS/network/routing and paging acceptance remain deployment tasks.
- **Contract coverage:** persisted run, approval, plan, KPI alert, notification and company profile schemas join the contract snapshots.
- **Release truth:** README, handoff and roadmap distinguish engineering, environment and human acceptance. PVC-070's unperformed human skill session is reopened. Pilot entry, approval to provision production and final launch approval no longer depend cyclically on each other. Policy/SLO/retention acceptance remains explicit.
- **Skill distribution:** pin a detached approved release tag/full SHA before installing the relative marketplace source. The marketplace does not itself resolve a tag. Skills describe the numeric-reference mutation contract.

## Fresh verification

Executed September 27 on Windows with Python 3.14.5 and a dedicated PostgreSQL 18 cluster on loopback port 54330. The existing developer cluster on 54329 was not used. No test role reset a shared application password. The original 337-test green CI run predates this work and does not validate these changes.

| Check | Result |
|---|---|
| Full pytest with PostgreSQL | **449 passed, 1 skipped**, 147.05 seconds. The skip requires Windows symlink privilege; traversal and foreign-row rejection checks passed. |
| Ruff lint and formatting | Passed; 127 Python files formatted. |
| Mypy | Passed; 85 source files. |
| Frozen dependency lock | `uv lock --check` passed; 111 packages resolved. |
| Deterministic evaluation gate | **39/39 passed**: 29 golden, 10 adversarial; all six safety/behavior dimensions 1.0. Golden run p95 1,343.6 ms; adversarial p95 862.4 ms. |
| Skill contracts/examples | Skill lint: zero problems. All six worked examples regenerated through MCP successfully; these are automated sessions. |
| Migration round trip | Upgrade/downgrade/upgrade passed at head `0003` in a disposable database. |
| Distribution build | Wheel and source distribution built successfully. Server-only dependencies installed in a fresh environment; MCP/API/worker imports and packaged policy, role SQL, migration and readiness assets verified outside the checkout. |
| Current runtime dependency audit | `pip-audit` on the exported pinned server requirements: no known vulnerabilities. This is not an image/OS scan. |
| Worker load | 40 runs, four workers: 1.7 runs/s; run p95 3.29 s; measured step p95 1.143 s against a 5 s gate; zero double claims. 30 awaiting approval, 10 needs evidence. |
| MCP load | 20 sessions, 600 calls: 52.8 calls/s, tool p95 446 ms, zero call errors. Windows connection-reset callback messages occurred during cleanup; no client/tool failures were recorded. |
| Restore drill | 399 rows, 99 KB dump; dump 0.21 s, restore 0.26 s. All 17 public table counts matched; scoped read/write isolation checked on all 16 tenant tables, including append-only audit privileges. |
| Authenticated integration smoke | Passed against separate local MCP, API and worker processes with staging authentication, generated RSA tokens with separate audiences, and a dedicated synthetic PostgreSQL database. Both readiness endpoints, evidence persistence/download, worker approval pause, review, rejection and resume passed. Test processes/database/role were removed. |
| Terraform | Module/staging/production validation and seven mocked tests passed; no apply. |
| Workflow/shell/monitoring checks | Actionlint, ShellCheck and Terraform recursive format passed; promtool validated all nine alert rules. Compose/observability YAML and Grafana JSON parsed. Container services remain unexecuted locally. |
| Diff whitespace | `git diff --check` passed. |

Core commands (PowerShell; executables are under `.venv/Scripts` unless stated):

```powershell
$env:PVC_ENV='dev'
$env:PVC_TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:54330/postgres'
python -m pytest -q
ruff check .
ruff format --check .
mypy src
uv lock --check
pvc eval --suite all --proposer rules --gate --report C:\pvc-audit-20260927\final-eval-report.json
python -m pe_value_os.skills_lint
python -m pe_value_os.db.migrate_check
python -m build --no-isolation --outdir C:\pvc-audit-20260927\dist
pip-audit -r C:\pvc-audit-20260927\runtime-requirements.txt --disable-pip --no-deps --format json --output C:\pvc-audit-20260927\dependency-audit.json
$env:PVC_ADMIN_DATABASE_URL=$env:PVC_TEST_DATABASE_URL
$env:PVC_PG_BIN="$env:LOCALAPPDATA\pvc-dev\pgsql\bin"
python scripts/restore_drill.py
python scripts/load_test.py --runs 40 --workers 4
python scripts/mcp_load_test.py --sessions 20 --rounds 5
actionlint
shellcheck infra/scripts/deploy.sh infra/scripts/smoke.sh infra/scripts/verify-ci.sh
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/modules/pvc test
promtool check rules ops/observability/prometheus-alerts.yaml
```

Build/uv use a separate temporary build-tools environment; server-only import verification uses `C:\pvc-audit-20260927\runtime`. Static infrastructure executables are under `%LOCALAPPDATA%\pvc-dev\bin`; Terraform initialized backend-disabled module/staging/production directories with separate temporary data directories before validation. The authenticated smoke command was `python infra/scripts/smoke_authenticated.py` with ephemeral local URLs and generated tokens supplied through environment variables; credentials are not retained in the report.

The evaluation JSON, dependency-audit JSON and distribution artifacts remain under `C:\pvc-audit-20260927`. Adversarial model token/cost fields are synthetic test-double estimates, not paid API usage. Fresh load and restore entries are retained in [load results](load_test.md) and the [restore log](runbooks/restore-drill-log.md).

## Upgrade notes

1. Apply migration `0003` before rolling out this code; readiness deliberately rejects a schema missing notification claim columns.
2. Update interactive clients/skills to call `get_numeric_sources` and bind quantitative prose with the returned references. Free numeric claims previously accepted will now be rejected. The tool catalog has 22 tools.
3. Company IDs must match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`. Inventory existing tenant IDs before rollout; punctuation/whitespace outside that grammar needs an explicit migration, not silent normalization.
4. New runs pin source and policy snapshots. Pre-remediation runs that never captured a snapshot cannot retroactively prove their historical inputs; create a linked refresh with a stated reason before using them for a new decision.
5. Configure scoped smoke tokens, worker heartbeat storage, telemetry endpoint/authentication and destination webhook idempotency as described in [deployment](deployment.md). Keep live-model nightly execution disabled until its provider/budget acceptance is complete.

## Remaining build and release acceptance

The [roadmap](../ROADMAP.md) retains all 111 tickets and their acceptance criteria: **78 Done, 14 Built, 19 Blocked** after reopening overstated acceptance. These labels are not a production-completion percentage. Open items are not silently closed by this remediation:

- **Built, acceptance open:** PVC-030, 072, 093, 094, 096, 103, 130, 131, 132, 133, 135, 136, 142, 143.
- **Blocked on identified input, review or acceptance:** PVC-001, 006, 055, 070, 071, 083, 090, 097, 110, 111, 113, 116, 140, 144, 147, 148, 153, 154, 155.

| Work | Required next evidence |
|---|---|
| Repository protection and release workflow | CI on the resulting commit, required checks, protected main and configured production reviewers. |
| Docker/Compose | Build the final image and run startup, role bootstrap, migrations, MCP/API/worker and the observability profile on a Docker host. |
| Staging infrastructure | Confirm AWS accounts/state, certificates/DNS, IdP, secrets, synthetic smoke users and approved egress; apply/bootstrap/deploy; verify auth, RLS, evidence/KMS, lease recovery and rollback. |
| Model acceptance | Approved provider/data policy, credentials and explicit budget; run all current proposer/narrator cases with the repaired gate and retain usage evidence. |
| Domain and human acceptance | Finance review of policy/benchmark values, security/threat-model review and an actual human MCP/approval session. Policy remains `2026.09.1-placeholder`. |
| Pilot source integration | Selected company/source strategy, credentials, real-data conformance/reconciliation and approved benchmark licensing. Finance automation still needs measured process volume and unit cost. |
| Operations | Routed test page, staffed on-call, accepted SLO/retention targets, two-week staging observation, target-hardware load and timed RDS restore/PITR with RPO/RTO evidence. |
| Production release | External security/legal review, completed pilot and signed provisioning decision, production validation, second-company onboarding and separate launch authorization. |

These are prerequisites for production acceptance, not claims of a verified deployment. No real customer data or live provider calls were used in local validation.

Subsequent showcase planning found an additional distribution gap: although installed-wheel imports passed above, `pvc demo` outside the checkout failed because its fixture adapter assumed a source-tree path. The follow-up packaged synthetic fixtures and evaluation data, then passed the installed demo and all 39 eval cases outside the checkout. See [container acceptance](container-acceptance.md) for this G02 repair, successful core Compose workflow and the newly measured strict image-scan failure. Presentation, current CI and remaining deployment acceptance stay open in the [portfolio finalization roadmap](portfolio-finalization-roadmap.md). The 23 original findings and A24 retain their recorded verification scope.
