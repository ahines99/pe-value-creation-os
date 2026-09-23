# Roadmap to Production

Ticketed plan that takes the PE Portfolio Value Creation Operating System from the current scaffold to a production service. The design it implements is in [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md).

## Conventions

- **ID:** `PVC-###`. Numbers are grouped by milestone (M3 → `PVC-03x`) and never reused.
- **Priority:** P0 is required for the release. P1 should ship in the release but can slip one release with a written reason. P2 is nice to have.
- **Size:** S ≈ 1 ideal engineer-day, M ≈ 2–3, L ≈ 5. Sizes are pre-calibration guesses. Re-estimate after M0–M1 using observed velocity.
- **Release:** the release gate the ticket belongs to (R0.1, R0.5, R1.0).
- **Deps:** tickets that must be done first.
- **Done when:** acceptance criteria. A ticket is done when every box is checked and CI is green.

Track status by checking boxes here, or import the tickets into an issue tracker and treat this file as the source of scope.

## Status

As of 2026-09-23. CI is green on GitHub (PR #1): lint, types, 335 tests on Python 3.12, 3.13 and 3.14 against PostgreSQL, the eval gate at 100%, pip-audit, gitleaks, and an image build with a Trivy scan. Nothing has been applied to AWS yet. An internal audit (code, security and status reviews) found 4 high-severity security, 3 high-severity correctness and several medium issues, and showed that some tickets had been marked Done too early. All findings are fixed with regression tests; the statuses below reflect the audit.

| Status | Tickets | Meaning |
|---|---|---|
| Done | 84 | Every acceptance criterion is met and was verified by running it. CI re-checks it on every push. |
| Built, not yet run in its target environment | 11 | The code or configuration is complete and statically validated. It still has to run on Docker Compose or AWS. |
| Blocked on a person, decision, or pilot company | 16 | The engineering part is done. What remains needs a named person (domain expert, security reviewer, pen tester, legal, on-call), a decision from the project owner, or the pilot company. |

| Release gate | State |
|---|---|
| R0.1 Vertical slice | All exit criteria verified locally. Three R0.1 tickets are still open: PVC-001 and PVC-006 (branch protection needs GitHub Pro) and PVC-030 (`docker compose` run, which needs Docker). |
| R0.5 Pilot-ready | Engineering complete. Needs staging applied, threat-model sign-off, the model data-handling review, a live-model eval (API key), and pilot data. |
| R1.0 Production | Needs the pilot, go decision, pen test, production drill, on-call rotation, and a second onboarded company. |

Each ticket below has a **Status** line. Checked boxes are criteria met now. Unchecked boxes say in the status line what is missing.

## Release gates

### R0.1: Vertical slice (local, fixture data)
One lever (pricing) end to end on synthetic data: intake → sufficiency → diagnostics → sizing → evidence review → prioritization → plan → approval gate. No LLM inside the workflow; the MCP tools and the diagnostic Skill are used interactively from an MCP client such as Claude Code.

Exit criteria:
- [x] `pytest` passes from a clean checkout with one setup command.
- [x] A seeded demo shows a success path, a `NEEDS_EVIDENCE` pause, and survival of an injected tool failure.
- [x] A run pauses at `AWAITING_APPROVAL`, survives a process restart, and resumes after a decision through the approval API.
- [x] Every value number in the output traces to `size_value_case` with an `inputs_hash` and evidence ids.
- [x] R0.1 items in the handoff's acceptance checklist are checked.

### R0.5: MVP / pilot-ready (staging, one real portco)
All four diagnostic levers, real data adapters for one portco, model reasoning at judgment steps, authentication and tenant isolation, an eval gate in CI, and a staging deployment. This is "MVP complete" as defined in the handoff.

Exit criteria:
- [x] Golden dataset (≥25 cases) and adversarial suite pass their thresholds in CI.
- [x] Cross-company access attempts fail closed in tests at both the tool layer and the database layer.
- [ ] Staging is deployed from CI with migrations, and passes smoke tests.
- [ ] Threat model reviewed; model-provider data handling approved.
- [ ] The pilot portco's data loads through adapters that pass the conformance suite.

### R1.0: Production
Multi-portco production service with KPI monitoring, SLOs, runbooks, tested backups, external security review, and a completed pilot with a go decision.

Exit criteria:
- [ ] Pilot retrospective has a signed-off go decision (PVC-154).
- [ ] SLOs are defined, and dashboards and alerts are live for 2 weeks in staging without a false-page storm.
- [ ] A backup restore drill met the RPO/RTO targets.
- [ ] Pen-test critical and high findings are closed.
- [ ] The portco onboarding playbook has been used for at least one company besides the pilot.

## Effort summary

| Release | Tickets | Ideal engineer-days (S=1, M=2.5, L=5) |
|---|---|---|
| R0.1 | 43 | ~88 |
| R0.5 | 44 | ~108 |
| R1.0 | 24 | ~55, plus pilot elapsed time (~4–6 weeks) |
| **Total** | **111** | **~250** |

These are unadjusted ideal days. A coding agent speeds up implementation more than review, integration, or stakeholder time. Calendar time depends on team size and the pilot portco's data-access lead time, which is usually the longest pole.

## Critical path

```text
PVC-002/003 ─► PVC-010/011 ─► PVC-020/028 ─► PVC-031 ─► PVC-040/041 ─► PVC-043 ─► PVC-053 ─► PVC-061 ─► PVC-150  (R0.1)
                                         └─► PVC-012/013 ─► PVC-035 ──┘
R0.1 ─► PVC-110 ─► PVC-111/113 ─► PVC-072 ─► PVC-080/081 ─► PVC-091/092 ─► PVC-131/133 ─► staging (R0.5)
R0.5 ─► PVC-147 ─► PVC-153 pilot ─► PVC-154 go/no-go ─► PVC-136 prod ─► R1.0
```

Start data-access conversations with the pilot portco (inputs to PVC-111/113) during R0.1. They take longer than the engineering.

---

## M0: Repository foundation

### PVC-001: Initialize version control
`P0 · S · R0.1 · deps: —`

**Status: Blocked on a person, decision, or pilot company.** Private remote created (github.com/ahines99/pe-value-creation-os) and pushed; work is in PR #1. GitHub refuses branch protection on private repositories under the free plan (HTTP 403). It needs GitHub Pro, or the repository made public; that decision is the project owner's.

At the start the project was not a git repository.
- [x] `git init`, a Python `.gitignore` (venv, caches, `.env`), and an initial commit of the current scaffold.
- [ ] Remote repository created, with branch protection on `main`.

### PVC-002: Fix test configuration
`P0 · S · R0.1 · deps: PVC-001`

**Status: Done.**

Plain `pytest` fails with `ModuleNotFoundError: src.mcp_server`. Two async test plugins are configured.
- [x] `pytest` and `python -m pytest` both pass from the repo root.
- [x] `pytest-asyncio` and `asyncio_mode` removed. Tests use `pytestmark = pytest.mark.anyio`.
- [x] The healthcheck test asserts `structured_content == {"status": "ok", "version": "0.1.0"}`.

### PVC-003: Package layout
`P0 · S · R0.1 · deps: PVC-002`

**Status: Done.**

Move `src/*` into `src/pe_value_os/` and add a hatchling build system, following the handoff's package skeleton.
- [x] `pip install -e .` works; imports are `pe_value_os.*`.
- [x] Tests import `from pe_value_os.mcp_server import mcp`.

### PVC-004: Dependency management
`P0 · S · R0.1 · deps: PVC-003`

**Status: Done.**

- [x] `uv` project with a committed `uv.lock`. `uv sync --extra dev` sets up a working environment.
- [x] Core dependencies are only `mcp[cli]>=2.2,<3` and `pydantic`. Postgres, HTTP and observability dependencies are in extras.
- [x] README quick start updated to the `uv` workflow.

### PVC-005: Lint, format, type-check
`P1 · S · R0.1 · deps: PVC-004`

**Status: Done.**

- [x] `ruff check`, `ruff format --check`, and `mypy --strict` on `pe_value_os.domain` all pass.
- [x] Pre-commit config runs ruff and checks for merge markers and large files.

### PVC-006: Continuous integration
`P0 · S · R0.1 · deps: PVC-004`

**Status: Blocked on a person, decision, or pilot company.** CI runs lint, types and tests on Python 3.12, 3.13 and 3.14 with a PostgreSQL service, and is green on PR #1 (250 tests on each version). Requiring it for merges needs branch protection. GitHub refuses branch protection on private repositories under the free plan (HTTP 403). It needs GitHub Pro, or the repository made public; that decision is the project owner's.

- [x] A GitHub Actions workflow runs lint, types, and tests on Python 3.12, 3.13, and 3.14.
- [ ] CI is required for merges to `main`.

### PVC-007: Architecture decision records
`P2 · S · R0.1 · deps: PVC-001`

**Status: Done.**

- [x] `docs/adr/` with a template.
- [x] ADRs recorded for: one MCP process with modules, an explicit state machine over Temporal for now, `Decimal` for money, and no model-callable approval.

## M1: Contracts and fixtures

### PVC-010: Core domain models
`P0 · M · R0.1 · deps: PVC-003`

**Status: Done.**

Implement `Confidence`, `EvidenceRef`, `Finding`, and `AuditEvent` exactly as in the handoff.
- [x] Field names and types match the SQL schema. A test compares model fields with table columns.
- [x] `Finding` references evidence by id.

### PVC-011: Project models
`P0 · M · R0.1 · deps: PVC-010`

**Status: Done.**

`Lever`, `ScenarioInputs`, `Opportunity`, and `ValueCase`.
- [x] Rates are rejected outside `[0, 1]`. Scenario ordering is validated. `evidence_ids` has at least one item.
- [x] Currency and rates are `Decimal`. JSON round-trip preserves precision.

### PVC-012: Source data schemas
`P0 · M · R0.1 · deps: PVC-010`

**Status: Done.**

Pydantic schemas for fixture and adapter inputs: monthly P&L, customer subscriptions (ARR ledger), invoice lines and price books, support tickets, and product usage.
- [x] Each schema has required fields, units, currency, and an `as_of` timestamp.
- [x] Validation errors name the file, row, and field.

### PVC-013: Synthetic fixture companies
`P0 · L · R0.1 · deps: PVC-012`

**Status: Done.** The planted findings are in each company's `PLANTED.md` (with machine-readable `planted.json`), not `README.md`.

Seeded generator for three fictional portcos: *Healthy*, *Pricing leak* (high discount dispersion, legacy price books), and *Churn problem* (front-loaded churn in one segment). Add one deliberately broken dataset with missing months, duplicate customers, stale `as_of`, and a document containing a prompt-injection string.
- [x] Generator is deterministic from a seed. Output is committed under `tests/fixtures/`.
- [x] Each company has a README listing the "planted" findings the system should discover.

### PVC-014: Data contracts documentation
`P1 · S · R0.1 · deps: PVC-011, PVC-012`

**Status: Done.**

- [x] `docs/data_contracts.md` covers every contract, units, and the schema-versioning policy (additive changes bump the minor version; breaking changes need a migration and ADR).

### PVC-015: Contract snapshot tests
`P2 · S · R0.5 · deps: PVC-014`

**Status: Done.**

- [x] JSON Schema for each contract is exported and snapshot-tested. CI fails on unreviewed breaking changes.

## M2: Deterministic calculation core

### PVC-020: Value-case sizing service
`P0 · M · R0.1 · deps: PVC-011`

**Status: Done.**

Implement `services.size_value_case` as in the handoff.
- [x] Golden tests hand-verify at least 10 cases, including zero realization, run cost exceeding benefit (negative EBITDA), and an EV multiple.
- [x] `calc_version` and `inputs_hash` are populated. Identical inputs give an identical hash.

### PVC-023: Price waterfall service
`P0 · M · R0.1 · deps: PVC-012`

**Status: Done.** Audit fix: the renewal realization ratio compared every renewal with only the contracted ones (5.5 instead of 1.0 in a test case). It now compares matched renewals, and free prior periods no longer divide by zero.

List → invoice → pocket price, with leakage by layer and discount dispersion by segment.
- [x] Planted leakage in the *Pricing leak* fixture is recovered exactly.
- [x] Output includes the evidence ids of the invoice and price-book sources used.

### PVC-024: Data-sufficiency checker
`P0 · M · R0.1 · deps: PVC-012`

**Status: Done.** Audit fix: staleness was judged only from the extract date. A fresh extract of old months now raises a `stale_series` gap, and rows in another currency raise `currency_mismatch`.

For each analysis (`unit_economics`, `pricing`, `retention`, `ai_opportunity`), check required fields, minimum history, and freshness.
- [x] Returns SUFFICIENT/INSUFFICIENT with a machine-readable gap list.
- [x] The broken fixture produces the expected gaps. Stale data is flagged using the freshness window from policy config.

### PVC-025: Prioritization and value phasing
`P0 · M · R0.1 · deps: PVC-020`

**Status: Done.**

A deterministic priority score from base EBITDA, confidence, time to value, and one-time cost, with weights in policy config. Add in-year phasing, computed separately from run-rate.
- [x] Ties are broken deterministically. Changing weights changes the ranking predictably (tested).
- [x] In-year value never exceeds run-rate value (property test).

### PVC-026: Policy and scope module
`P0 · S · R0.1 · deps: PVC-010`

**Status: Done.**

`check_action`, `require_citations`, and `scope.require(company_id)`, with the allowed set taken from `PVC_ALLOWED_COMPANIES` for now.
- [x] An out-of-scope company raises a typed error. An uncited value claim raises `PolicyViolation`.

### PVC-028: Baseline and flow-through derivation
`P0 · M · R0.1 · deps: PVC-012, PVC-026`

**Status: Done.**

Server-side lookup that turns `(company_id, lever, baseline_metric)` into `baseline_value` and `ebitda_flow_through`, using company data and a policy table of flow-through rules by lever.
- [x] Unknown metric names are rejected with the list of valid names.
- [x] Every derived value carries the evidence ids it came from.

### PVC-021: SaaS metrics service
`P0 · L · R0.5 · deps: PVC-012`

**Status: Done.** Audit fix: zero S&M spend crashed the metrics (and with them any run using gross-margin flow-through); non-positive margins, a partial current quarter and an empty ledger gave wrong values. All now return None with a note. See `tests/test_audit_fixes.py`.

ARR bridge, GRR, NRR, CAC payback, LTV/CAC, magic number, burn multiple, Rule of 40, and subscription gross margin, using the definitions in the `saas-unit-economics` skill.
- [x] Each metric reports its variant and period. Periods are aligned or it raises an error.
- [x] Planted values in all three fixture companies are recovered exactly.

### PVC-022: Retention cohort service
`P0 · M · R0.5 · deps: PVC-012`

**Status: Done.**

Logo and dollar retention by cohort, split into voluntary and involuntary churn.
- [x] The *Churn problem* fixture's planted segment and cohort pattern is recovered.
- [x] GRR never exceeds 100% (property test).

### PVC-027: Property-based calculation tests
`P2 · S · R0.5 · deps: PVC-020, PVC-021`

**Status: Done.**

- [x] Hypothesis tests cover sizing monotonicity, ARR bridge identity, and GRR ≤ NRR.

## M3: Persistence and audit

### PVC-030: Postgres and migrations
`P0 · M · R0.1 · deps: PVC-004`

**Status: Built, not yet run in its target environment.** Alembic creates every table. The upgrade/downgrade round trip runs green in CI against a PostgreSQL 18 service. `docker compose up db` hasn't been run because this machine has no Docker.

- [ ] `docker compose up db` starts Postgres. The Alembic migration creates every table in the handoff's data model.
- [x] Upgrade and downgrade are tested in CI against a Postgres service container.

### PVC-031: Repository layer
`P0 · L · R0.1 · deps: PVC-010, PVC-011, PVC-030`

**Status: Done.**

A repository interface with in-memory and Postgres implementations, selected by `get_repository()` from `DATABASE_URL`.
- [x] One shared contract test suite runs against both implementations.
- [x] Every query is filtered by `company_id`. A test proves one company can't read another's rows through the API.

### PVC-032: Evidence store
`P0 · M · R0.1 · deps: PVC-031`

**Status: Done.**

Immutable originals, with derived text stored separately. Content-hash deduplication per company. Local filesystem backend now, object storage later.
- [x] Re-ingesting the same file returns the existing `evidence_id`.
- [x] Originals can't be overwritten through the API.

### PVC-033: Append-only audit log
`P0 · S · R0.1 · deps: PVC-030`

**Status: Done.**

- [x] The application database role has only INSERT and SELECT on `audit_events`. A test proves UPDATE and DELETE fail.
- [x] `audit.emit` is used by the workflow runner and every mutating tool.

### PVC-035: Fixture source adapter
`P0 · M · R0.1 · deps: PVC-013, PVC-032`

**Status: Done.**

Loads fixture companies as if they were source systems and registers each file as evidence.
- [x] Loading a fixture company gives the same `evidence_id`s on every run.
- [x] Malformed rows produce a sufficiency gap, not a crash.

### PVC-034: Row-level security
`P1 · M · R0.5 · deps: PVC-031`

**Status: Done.**

- [x] Postgres RLS policies on every company-scoped table, keyed on a session variable set per request.
- [x] A test with RLS on and a deliberately unfiltered query still returns only in-scope rows.

## M4: Workflow engine

### PVC-040: Checkpointing workflow runner
`P0 · M · R0.1 · deps: PVC-031, PVC-033`

**Status: Done.**

`run_steps`, `RunState`, and the `StateStore`/`AuditSink` protocols, as in the handoff, with a Postgres-backed state store.
- [x] State is saved after every step. Every step emits start, complete, or fail audit events.

### PVC-041: Resume and idempotent reruns
`P0 · M · R0.1 · deps: PVC-040`

**Status: Done.**

- [x] Killing the process mid-run and calling `resume(run_id)` completes without re-executing finished steps (tested).
- [x] Starting a run with an existing `idempotency_key` returns the existing run.

### PVC-042: Parallel diagnostics step
`P0 · S · R0.1 · deps: PVC-040`

**Status: Done.**

- [x] Branches run concurrently. One failed branch is recorded as a gap; if every branch fails, the step fails.

### PVC-043: Primary workflow on fixtures
`P0 · L · R0.1 · deps: PVC-020, PVC-023, PVC-024, PVC-025, PVC-028, PVC-035, PVC-041, PVC-042`

**Status: Done.**

Wire every step to domain services. Opportunities are proposed by deterministic rules (for example, discount dispersion above the policy threshold proposes a discount-governance opportunity), with no LLM.
- [x] The *Pricing leak* fixture produces the planted opportunity, sized, prioritized, and in a draft plan.
- [x] The broken fixture pauses with `NEEDS_EVIDENCE` and lists its gaps.

### PVC-045: Command-line interface
`P1 · S · R0.1 · deps: PVC-043`

**Status: Done.** Verified against PostgreSQL 18 as the RLS-bound `pvc_app` role.

- [x] `pvc run --company <id>`, `pvc resume <run_id>`, and `pvc status <run_id>` work against Postgres.

### PVC-046: Failure injection harness
`P0 · S · R0.1 · deps: PVC-035`

**Status: Done.**

A fault-injecting adapter wrapper that can time out, raise, or return malformed data on a chosen call.
- [x] Tests cover one failed diagnostic branch (run continues), a failure in value modeling (run fails cleanly), and resume after the fault clears.

### PVC-044: Timeouts and retries
`P1 · M · R0.5 · deps: PVC-041`

**Status: Done.** Audit fix: a timed-out attempt's thread kept running beside its retry and could write after the run failed. Each attempt now works on a state copy behind a repository guard, and plan ids are deterministic.

- [x] Per-step timeouts (`anyio.fail_after`) and bounded retries with backoff, for adapter errors marked transient only.
- [x] Retries are audited. Non-transient errors are not retried.

### PVC-047: Workflow engine decision record
`P2 · S · R0.5 · deps: PVC-044`

**Status: Done.**

- [x] ADR: stay on the explicit state machine or move to Temporal/Prefect, based on the timer, retry, and worker needs seen by R0.5.

## M5: MCP surface

### PVC-050: MCP server module structure
`P0 · S · R0.1 · deps: PVC-003`

**Status: Done.**

- [x] One `MCPServer`, with tools registered from modules per capability boundary (`portco_financials`, `crm`, `product_analytics`, `support`, `pricing`, `benchmark`, `value_model`, `workflow`).

### PVC-051: Intake tools
`P0 · S · R0.1 · deps: PVC-024, PVC-050`

**Status: Done.**

`get_company_profile` and `check_data_sufficiency`.
- [x] Typed Pydantic outputs, with a `scope.require` check first in each tool.

### PVC-052: Price waterfall tool
`P0 · S · R0.1 · deps: PVC-023, PVC-050`

**Status: Done.**

- [x] `price_waterfall(company_id, period, segment=None)` returns the typed waterfall with evidence ids.

### PVC-053: Value-model tools
`P0 · L · R0.1 · deps: PVC-020, PVC-025, PVC-028, PVC-031, PVC-050`

**Status: Done.**

`record_finding`, `propose_opportunity`, `size_value_case`, `list_evidence`, and `prioritize_opportunities`.
- [x] `propose_opportunity` rejects any caller-supplied baseline or flow-through. The server fills them in.
- [x] `record_finding` enforces `require_citations`.
- [x] Each mutating tool writes an audit event.

### PVC-054: Workflow tools
`P0 · S · R0.1 · deps: PVC-041, PVC-050`

**Status: Done.**

`get_run_status` and `request_approval`.
- [x] A test asserts that no registered tool can record an approval decision.

### PVC-055: Resources, prompts, and policy configuration
`P0 · M · R0.1 · deps: PVC-050`

**Status: Done.**

Turn `project://policies` into a structured policy config: freshness window, screening thresholds used by the skills, flow-through rules, and prioritization weights. Add `company://{company_id}/data-inventory`, `run://{run_id}/summary`, and the `review_run` prompt.
- [x] Policy config is versioned in the repo, loaded at startup, and its version appears in audit events.

### PVC-056: MCP integration tests
`P0 · M · R0.1 · deps: PVC-051 to PVC-055`

**Status: Done.** Audit follow-up: every run- and company-scoped tool now has an out-of-scope test, and every tool an invalid-argument test (`tests/test_mcp.py`).

- [x] Every tool has in-process `Client` tests for success, invalid arguments, and an out-of-scope `company_id`.
- [x] Five golden end-to-end tests drive the vertical slice through MCP.

### PVC-057: Source data tools
`P0 · M · R0.5 · deps: PVC-110`

**Status: Done.**

`get_financials`, `get_usage_metrics`, and `get_support_metrics`.
- [x] Typed outputs with evidence ids and scope checks, plus tests.

### PVC-058: Metric tools
`P0 · S · R0.5 · deps: PVC-021, PVC-022`

**Status: Done.**

`compute_saas_metrics` and `compute_retention_cohorts`.
- [x] Typed outputs report the metric variant and period, plus tests.

### PVC-059: Tool description and schema review
`P2 · S · R0.5 · deps: PVC-058`

**Status: Done.**

- [x] Every tool description says what it does, what it won't do, and its units. Tool schemas are snapshot-tested.

## M6: Human approval

### PVC-060: Approval API
`P0 · M · R0.1 · deps: PVC-031`

**Status: Done.** Audit fix: the API accepted MCP-client tokens. It now verifies its own audience (`PVC_API_AUDIENCE`) and requires `pvc.approve` on an allowed approval-UI client.

A FastAPI endpoint, `POST /runs/{run_id}/approvals`, served separately from the MCP surface.
- [x] Requires an authenticated human principal (a local dev token in R0.1; OAuth in R0.5).
- [x] Rationale is required for `rejected` and `changes_requested`. Every decision is audited.

### PVC-061: Approval gate step
`P0 · M · R0.1 · deps: PVC-041, PVC-060`

**Status: Done.**

- [x] No decision → `AWAITING_APPROVAL`. Approved → `COMPLETE`. Rejected → `REJECTED`.
- [x] `changes_requested` re-opens prioritization and later steps, with the reviewer's notes attached, and the run resumes from there (tested).

### PVC-062: Approval review view
`P1 · L · R0.5 · deps: PVC-060`

**Status: Done.**

A minimal server-rendered page showing the plan, value cases with inputs, evidence links, and gaps, with approve, reject, and request-changes actions.
- [x] Evidence links open the stored original. The page works without JavaScript frameworks.

### PVC-063: Human-override tracking
`P1 · S · R0.5 · deps: PVC-061`

**Status: Done.**

- [x] A diff between the proposed plan and the approved plan is stored and audited. An "override rate" metric is exposed.

### PVC-064: Approval expiry and escalation
`P2 · S · R1.0 · deps: PVC-061, PVC-134`

**Status: Done.**

- [x] Runs awaiting approval longer than the policy limit notify the escalation contact. Nothing is auto-approved.

## M7: Skills and model reasoning

### PVC-070: Diagnostic skill validated end to end
`P0 · M · R0.1 · deps: PVC-056`

**Status: Done.** Session run on 2026-09-23 against the Cedar fixture over the plugin's MCP stdio server, with Claude as the analyst making every judgment. The output meets all 8 items of the output contract ([docs/skill-sessions/2026-09-23-cedar-diagnostic.md](docs/skill-sessions/2026-09-23-cedar-diagnostic.md)). The session found and fixed an evidence-registration bug in `record_finding`. A repeat by a team member in Claude Code is still recommended before the domain-expert review (PVC-071).

- [x] `pe-value-creation-diagnostic` has a worked example in `references/` from the *Pricing leak* fixture run.
- [x] A manual session in an MCP client, using the skill, produces output that meets its output contract.

### PVC-075: Skill lint
`P1 · S · R0.1 · deps: PVC-050`

**Status: Done.**

- [x] A CI check validates skill frontmatter (name matches directory, description present).
- [x] Every MCP tool a skill names must exist in the tool catalog. Planned tools are allowed only if listed with a ticket id.

### PVC-071: Lever skills completed and reviewed
`P1 · M · R0.5 · deps: PVC-058`

**Status: Blocked on a person, decision, or pilot company.** Every lever skill has a generated worked example. Waiting on domain-expert review and sign-off.

- [x] Each lever skill has a `references/` worked example from a fixture run.
- [ ] A domain expert (operating partner or VCP lead) reviewed the definitions and diagnostic trees. Their sign-off is recorded.

### PVC-072: Model reasoning at judgment steps
`P0 · L · R0.5 · deps: PVC-043, PVC-080`

**Status: Blocked on a person, decision, or pilot company.** ADRs 0005 and 0006 exist. The no-new-numbers guardrail is enforced and hardened (words, scale words, multipliers, signs), but it has only been exercised with a scripted model. The criterion needs a live-model eval (`pvc eval --proposer model`), which needs an `ANTHROPIC_API_KEY` from the project owner.

Replace the rule-based opportunity proposals, and add evidence synthesis and plan narrative, using Claude through the Anthropic SDK with structured outputs validated by Pydantic.
- [x] One ADR per model-dependent decision explains why a rule isn't enough and names its eval.
- [ ] Model outputs never contain numbers that aren't copied from tool results (checked in eval).

### PVC-073: Prompt-injection defences
`P0 · M · R0.5 · deps: PVC-072`

**Status: Done.**

- [x] Retrieved text is passed as delimited data. Each step has a tool allowlist.
- [x] Injected instructions in the broken fixture are recorded as `suspicious_content` and not followed (adversarial eval).

### PVC-074: Model outage fallback
`P1 · S · R0.5 · deps: PVC-072`

**Status: Done.**

- [x] If the model is unavailable, the run pauses at `NEEDS_EVIDENCE` with reason `model_unavailable` and can be resumed.

### PVC-076: Skill distribution
`P1 · S · R0.5 · deps: PVC-071`

**Status: Done.**

- [x] Documented, versioned way to install the skills in the MCP clients the team uses, such as a Claude Code plugin or project skills directory.

## M8: Evaluation

### PVC-080: Evaluation harness
`P0 · L · R0.5 · deps: PVC-056`

**Status: Done.**

- [x] `evals/` runner scores the seven dimensions in the handoff and writes a per-run report.

### PVC-081: Golden dataset
`P0 · L · R0.5 · deps: PVC-080`

**Status: Done.** Audit follow-up: 25 of 29 golden cases now carry value ranges (base-case EBITDA per opportunity and plan total). They are regression bands around reviewed results (see `value_ranges_basis` in `evals/golden.json`), for the domain expert to confirm under PVC-071.

- [x] At least 25 cases across the four levers and three fixture companies, each with expected findings, opportunities, and value ranges.

### PVC-082: Adversarial suite
`P0 · M · R0.5 · deps: PVC-080`

**Status: Done.**

- [x] Cases cover prompt injection, stale data, duplicate entities, contradictory evidence, missing required fields, and a cross-portco lure. Every case fails closed.

### PVC-083: CI evaluation gate
`P1 · M · R0.5 · deps: PVC-081, PVC-082`

**Status: Blocked on a person, decision, or pilot company.** The eval gate runs green in CI against `evals/thresholds.toml`. `nightly-evals.yml` has never run: scheduled workflows run from the default branch, so it starts once PR #1 merges. Blocking merges on the gate needs branch protection. GitHub refuses branch protection on private repositories under the free plan (HTTP 403). It needs GitHub Pro, or the repository made public; that decision is the project owner's.

- [ ] Merges are blocked when scores drop below thresholds recorded in the repo. The full suite runs nightly.

### PVC-084: Cost and latency reporting
`P2 · S · R0.5 · deps: PVC-080, PVC-101`

**Status: Done.**

- [x] The eval report includes tokens, cost, and latency per run and per step.

## M9: Security and tenancy

### PVC-090: Threat model
`P0 · M · R0.5 · deps: PVC-060`

**Status: Blocked on a person, decision, or pilot company.** `docs/threat_model.md` has the STRIDE analysis, with mitigations linked to tickets. Waiting on a security reviewer's sign-off.

- [ ] `docs/threat_model.md` has a STRIDE analysis of the MCP surface, approval API, adapters, and model calls. It is reviewed, and each mitigation is linked to a ticket.

### PVC-091: MCP authentication
`P0 · L · R0.5 · deps: PVC-050`

**Status: Done.**

- [x] The Streamable HTTP MCP endpoint requires OAuth 2.1 bearer tokens, following the MCP authorization spec, behind the ASGI app. Unauthenticated calls are rejected.

### PVC-092: Company-scope authorization
`P0 · M · R0.5 · deps: PVC-034, PVC-091`

**Status: Done.**

- [x] `scope.require` reads allowed companies from token claims, and the same principal sets the RLS session variable.
- [x] The environment-variable allow-list is removed outside dev.

### PVC-093: Secrets management
`P0 · S · R0.5 · deps: PVC-006`

**Status: Built, not yet run in its target environment.** Dev uses environment variables. Terraform reads staging and prod secrets from Secrets Manager (verified by `terraform test`, not applied). gitleaks is in CI and pre-commit, and a test checks that skills, prompts and policy contain no secrets.

- [ ] Secrets come from the environment in dev and a cloud secret manager in staging and prod. CI runs secret scanning. No secrets in skills or prompts.

### PVC-095: Log redaction
`P1 · S · R0.5 · deps: PVC-100`

**Status: Done.**

- [x] A test asserts that logs contain no raw financial values, customer names, or document text; only ids and hashes.

### PVC-096: Dependency and container scanning
`P1 · S · R0.5 · deps: PVC-130`

**Status: Done.** `pip-audit` and a Trivy scan of the built image run green in CI. HIGH/CRITICAL findings with a fix fail the build; unfixed ones are listed by a non-blocking step, because rebuilding cannot fix them. The project owner should confirm this reading of the criterion. Actions are pinned by SHA and base images by digest, with Dependabot updates.

- [x] `pip-audit` and a container scan run in CI. High and critical findings fail the build.

### PVC-094: Egress controls
`P1 · S · R1.0 · deps: PVC-136`

**Status: Built, not yet run in its target environment.** Application egress allow-list on every HTTP client (tested). AWS Network Firewall rules are in Terraform, not applied. No tool can send email or write to source systems.

- [ ] A network egress allow-list for production covers the model provider, data sources, and telemetry. No tool can send email or write to source systems.

### PVC-097: External penetration test
`P1 · M · R1.0 · deps: PVC-136`

**Status: Blocked on a person, decision, or pilot company.** Scope is in `docs/security/pentest_scope.md`. Needs a third-party tester and a deployed environment.

- [ ] A third-party test of the MCP endpoint, approval API, and tenancy isolation. Critical and high findings are fixed and retested.

## M10: Observability

### PVC-100: Structured logging
`P0 · S · R0.5 · deps: PVC-004`

**Status: Done.**

- [x] structlog JSON logs carry `run_id`, `company_id`, `step`, and `tool_name` context.

### PVC-101: Tracing
`P1 · M · R0.5 · deps: PVC-100`

**Status: Done.** Audit fix: the providers were only configured in tests, so nothing was exported. The MCP server, API and worker now install OTLP export at startup when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (tested).

- [x] OpenTelemetry spans for run → step → tool → model call, exported over OTLP. Traces link to audit events by `run_id`.

### PVC-102: Metrics
`P1 · M · R1.0 · deps: PVC-101`

**Status: Done.** Audit fix: see PVC-101; the metrics are now exported. Scope denials from every surface are counted in `pvc.access.denied`.

- [x] Metrics for run outcomes, step latency, tool error rate, model tokens and cost, approval turnaround, and human-override rate.

### PVC-103: Dashboards and alerts
`P1 · M · R1.0 · deps: PVC-102, PVC-140`

**Status: Built, not yet run in its target environment.** Grafana dashboard (13 panels) and 9 Prometheus alert rules (promtool-valid). They can now fire, because export is wired (PVC-101). The probing alert covers denials from every surface and id lookups. Routing to on-call and 2 weeks live need staging and PVC-148.

- [ ] SLO dashboards, plus alerts on SLO burn, stuck runs, adapter failures, and eval regressions, routed to on-call.

## M11: Real data integrations

### PVC-110: Adapter contract and conformance suite
`P0 · M · R0.5 · deps: PVC-035`

**Status: Blocked on a person, decision, or pilot company.** Every adapter implements one interface and passes the conformance suite. ADR 0008 chooses warehouse-first, but the criterion asks for the decision for the pilot company, which has not been chosen.

- [x] Every adapter implements one interface and must pass a shared conformance suite using recorded responses.
- [ ] ADR: a warehouse-first path (read from the portco's warehouse or dbt models) versus per-system APIs, decided for the pilot portco.

### PVC-111: Financials adapter
`P0 · L · R0.5 · deps: PVC-110`

**Status: Blocked on a person, decision, or pilot company.** Warehouse and CSV-export adapters pass the conformance suite. Waiting on the pilot company's source.

- [ ] Monthly P&L from the pilot portco's source (warehouse, ERP export, or accounting system) passes conformance. Every load is registered as evidence.

### PVC-113: Billing and invoice adapter
`P0 · L · R0.5 · deps: PVC-110`

**Status: Blocked on a person, decision, or pilot company.** Stripe adapter passes conformance against a simulated API. Waiting on the pilot company's billing system.

- [ ] Invoice lines, price books, and subscriptions from the pilot's billing system pass conformance. This feeds pricing and ARR.

### PVC-112: CRM adapter
`P1 · L · R0.5 · deps: PVC-110`

**Status: Done.** HubSpot adapter, read-only, passes conformance against a simulated API. If the pilot uses Salesforce, that needs a new adapter.

- [x] Customers, opportunities, renewals, and churn reason codes (for example, Salesforce or HubSpot) pass conformance, read-only.

### PVC-117: Customer entity resolution
`P1 · M · R0.5 · deps: PVC-112, PVC-113`

**Status: Done.**

- [x] Deterministic matching of customers across CRM and billing, with a review queue for ambiguous matches. The duplicate-entity adversarial case passes.

### PVC-118: Data freshness monitoring
`P1 · S · R0.5 · deps: PVC-111`

**Status: Done.**

- [x] Each source's latest `as_of` is tracked. Stale sources show up in sufficiency checks and alerts.

### PVC-114: Product analytics adapter
`P2 · L · R1.0 · deps: PVC-110`

**Status: Done.** Usage comes through the warehouse and CSV adapters, which pass conformance.

- [x] Usage and feature adoption data passes conformance.

### PVC-115: Support adapter
`P2 · M · R1.0 · deps: PVC-110`

**Status: Done.** Zendesk adapter passes conformance against a simulated API.

- [x] Ticket volume, categories, handle time, and CSAT pass conformance.

### PVC-116: Benchmark data and tool
`P2 · M · R1.0 · deps: PVC-110`

**Status: Blocked on a person, decision, or pilot company.** `get_benchmarks` is built, with a minimum peer count and no portco-level values, on a synthetic peer set with provenance. The real data source and licence are an open decision.

- [ ] A licensed or anonymized peer dataset is ingested with its provenance, and the `get_benchmarks` tool is exposed. Portco-level values are never returned.

## M12: KPI monitoring

### PVC-120: KPI definitions from approved plans
`P0 · M · R1.0 · deps: PVC-061`

**Status: Done.**

- [x] Approval of a plan persists its KPIs (metric, baseline, targets, cadence, source). Unmonitorable KPIs are rejected at approval time.

### PVC-121: Scheduled KPI refresh and status tool
`P0 · M · R1.0 · deps: PVC-120, PVC-134`

**Status: Done.**

- [x] A worker job refreshes KPIs on their cadence. The `get_kpi_status(company_id)` tool returns plan-vs-actual with evidence.

### PVC-122: Variance detection
`P0 · S · R1.0 · deps: PVC-121`

**Status: Done.**

- [x] Deterministic off-track rules (threshold and trend) have configurable tolerances and are audited.

### PVC-123: KPI digests
`P1 · M · R1.0 · deps: PVC-122`

**Status: Done.**

- [x] A read-only digest to an approved channel lists off-track KPIs with links. The channel is configured by a human; the model can't send messages.

### PVC-124: Plan-vs-actual view
`P2 · M · R1.0 · deps: PVC-121, PVC-062`

**Status: Done.**

- [x] A page per company shows KPI history, targets, and the linked initiatives.

## M13: Deployment and infrastructure

### PVC-130: Container images
`P0 · S · R0.5 · deps: PVC-004`

**Status: Built, not yet run in its target environment.** The multi-stage image (non-root, uid 10001) builds in CI and passes the Trivy scan. `docker compose up` for the full local stack hasn't been run because this machine has no Docker.

- [ ] A multi-stage Dockerfile with a non-root user. `docker compose up` runs db, MCP server, approval API, and worker locally.

### PVC-131: Staging environment as code
`P0 · L · R0.5 · deps: PVC-130`

**Status: Built, not yet run in its target environment.** Terraform for AWS (VPC, ECS Fargate, RDS, Secrets Manager, S3 with Object Lock, KMS, ALB) passes fmt, validate and `terraform test`. Not applied. The cloud choice is an open decision.

- [ ] Terraform (or equivalent) for staging networking, compute, Postgres, secrets, and object storage in the chosen cloud.

### PVC-132: Managed Postgres
`P0 · M · R0.5 · deps: PVC-131`

**Status: Built, not yet run in its target environment.** RDS with KMS encryption, PITR, automated backups and forced TLS (`verify-full`). Roles come from the bootstrap task, which sends SCRAM verifiers so no password reaches the DDL log. Not applied.

- [ ] Encryption at rest, point-in-time recovery, automated backups, and least-privilege roles (application, migration, read-only).

### PVC-133: Continuous delivery
`P0 · M · R0.5 · deps: PVC-131, PVC-096`

**Status: Built, not yet run in its target environment.** `cd.yml` builds, scans, migrates, deploys and smoke-tests; production needs a manual approval. It deploys only from `main`. The deploy role can run only `migrate`, not `bootstrap` or `offboard`. It needs AWS credentials and has never run.

- [ ] Pipeline: build, scan, migrate, deploy, and smoke test. Staging deploys automatically; production needs a manual approval.

### PVC-134: Worker process
`P1 · M · R0.5 · deps: PVC-044`

**Status: Done.** `pvc worker` runs as a separate ECS service. Tests cover queued-run execution and escalation, and the load test found no double claims. Run state lives in PostgreSQL, so the MCP server holds none.

- [x] Workflow execution and scheduled jobs run in a worker process separate from the MCP server. Restarting the MCP server doesn't interrupt runs.

### PVC-135: Ingress and TLS
`P0 · S · R0.5 · deps: PVC-131`

**Status: Built, not yet run in its target environment.** ALB with a TLS 1.3 policy, HTTP to HTTPS redirect, WAF rate limiting and body-size limits. Access logs go to a dedicated bucket. OIDC sign-in is available for the review UI. Forwarded headers are trusted only from the VPC. Not applied.

- [ ] TLS everywhere, rate limiting, and request size limits on the MCP and approval endpoints.

### PVC-136: Production environment
`P0 · M · R1.0 · deps: PVC-131, PVC-154`

**Status: Built, not yet run in its target environment.** The production env reuses the staging module with separate state and credentials. Not applied. It depends on the go decision (PVC-154).

- [ ] Production is provisioned from the same code as staging, with separate accounts or projects and credentials.

## M14: Production readiness

### PVC-145: Calculation versioning policy
`P1 · S · R0.5 · deps: PVC-020`

**Status: Done.**

- [x] Changing a calculation bumps `calc_version`. Stored value cases keep their version. Recomputing requires an explicit, audited action.

### PVC-147: Model provider data-handling review
`P0 · S · R0.5 · deps: PVC-072`

**Status: Blocked on a person, decision, or pilot company.** `docs/model_data_handling.md` lists the data classes and settings. Waiting on legal and data-processing review.

- [ ] Data-processing terms and retention settings for the model provider are confirmed, and the portco data classes sent to the model are documented and approved *before* pilot data reaches a model.

### PVC-140: Service level objectives
`P0 · S · R1.0 · deps: PVC-102`

**Status: Done.**

- [x] SLOs are defined for API availability, p95 run duration by step, and eval score floors.

### PVC-141: Runbooks
`P0 · M · R1.0 · deps: PVC-103`

**Status: Done.**

- [x] `docs/runbooks/` covers stuck or failed runs, adapter outage, model outage, a bad calculation release (rollback and recompute), a suspected cross-company data exposure, and database restore.

### PVC-142: Backup restore drill
`P0 · S · R1.0 · deps: PVC-132`

**Status: Built, not yet run in its target environment.** RPO and RTO are set in `docs/slo.md`. A local drill passed (`docs/runbooks/restore-drill-log.md`). The restore runbook now matches the infrastructure: explicit restore flags, identifier swap, state re-import, re-offboarding. The drill on RDS needs the environment applied (PVC-132).

- [ ] RPO and RTO targets are set. A restore to a fresh instance is performed and timed, and the results are recorded.

### PVC-143: Load test
`P1 · M · R1.0 · deps: PVC-134`

**Status: Done.** Both halves run against PostgreSQL on developer hardware (`docs/load_test.md`). Runs: 4 workers, 40 runs, no double claims. MCP sessions: 20 concurrent Streamable HTTP sessions, 600 calls, 0 errors, p95 752 ms. The MCP test found an evidence-store race, now fixed. Repeat on staging hardware.

- [x] Target concurrency (runs and MCP sessions) is sustained within SLOs. Bottlenecks are documented.

### PVC-144: Data retention and deletion
`P0 · M · R1.0 · deps: PVC-032`

**Status: Done.** Audit fix: offboarding now deletes evidence before database rows and records failures. It runs as an operator-only `offboard` task whose role alone may delete evidence versions under Object Lock (`docs/data_retention.md`). Not yet run in AWS.

- [x] A retention policy per data class. Portco offboarding deletes that company's data and evidence, verified by a test, while audit records are kept as the policy requires.

### PVC-146: Access review and audit export
`P1 · M · R1.0 · deps: PVC-092`

**Status: Done.**

- [x] Quarterly access-review report and audit-log export per company, aligned with the fund's compliance requirements (for example, SOC 2 controls).

### PVC-148: On-call and incident process
`P1 · S · R1.0 · deps: PVC-103`

**Status: Blocked on a person, decision, or pilot company.** Severity levels, incident template and post-incident review are in `docs/runbooks/oncall.md`. The rotation needs named people.

- [ ] On-call rotation, severity levels, incident template, and a post-incident review process.

## M15: Demo, pilot, and general availability

### PVC-150: One-command seeded demo
`P0 · M · R0.1 · deps: PVC-043, PVC-046, PVC-061`

**Status: Done.** `uv run pvc demo`, covered by `tests/test_demo.py`.

- [x] `make demo` (or `uv run pvc demo`) seeds fixtures and shows the success path, the `NEEDS_EVIDENCE` pause, an injected failure, and approval and resume.

### PVC-151: Architecture diagram and README
`P1 · S · R0.1 · deps: PVC-150`

**Status: Done.** `docs/architecture.md` and the README.

- [x] `docs/architecture.md` has a layer and data-flow diagram. The README is updated with the demo and the "Why this is not just a chatbot" section.

### PVC-152: Demo script
`P2 · S · R0.1 · deps: PVC-150`

**Status: Done.** `docs/pilot/demo-script.md`.

- [x] A 3-minute recorded-demo script covering one success path and one controlled failure.

### PVC-153: Pilot with one portfolio company
`P0 · L · R1.0 · deps: R0.5 gate, PVC-147`

**Status: Blocked on a person, decision, or pilot company.** The plan is in `docs/pilot/pilot-plan.md`. Needs the R0.5 gate, PVC-147, and a pilot company.

Run on the pilot portco's real data in staging, read-only, with the deal team and operating partner as approvers.
- [ ] At least two complete diagnostic runs are reviewed by humans. The override rate and reviewer feedback are recorded.
- [ ] Every opportunity the reviewers dispute has a root cause (data, calculation, skill, or model) and a ticket.

### PVC-154: Pilot retrospective and go/no-go
`P0 · S · R1.0 · deps: PVC-153`

**Status: Blocked on a person, decision, or pilot company.** The template is in `docs/pilot/go-no-go.md`. Needs the pilot.

- [ ] A written retrospective and a signed go/no-go decision, with conditions for production.

### PVC-155: Portco onboarding playbook
`P0 · M · R1.0 · deps: PVC-154`

**Status: Blocked on a person, decision, or pilot company.** The playbook is in `docs/pilot/onboarding-playbook.md`, and `pvc onboard-check` is its readiness check. It hasn't yet been used to onboard a second company.

- [ ] Checklist covering data-access agreements, adapter setup, sufficiency baseline, approver setup, and KPI cadence. It has been used to onboard a second company.

---

## Roadmap risks

| Risk | Effect | Mitigation |
|---|---|---|
| Pilot portco data access is slow | R0.5 slips | Start access requests during R0.1; warehouse-first adapter ADR (PVC-110) |
| Model output drifts toward inventing numbers | Loss of trust in value cases | Server-side baselines, no-new-numbers eval (PVC-072), citation enforcement |
| Metric definitions disputed by deal teams | Rework of M2 | Domain-expert sign-off on skills (PVC-071) before pilot; definitions versioned in policy |
| Scope creep into more levers or sources | R0.1 never closes | R0.1 is pricing only; new levers need a ticket in R0.5+ |
| Tenancy bug leaks cross-portco data | Severe | Scope checks plus RLS (PVC-031/034/092), adversarial lure case (PVC-082), pen test (PVC-097) |

## Open decisions for the project owner

1. **Pilot portco** and its source systems, which determine PVC-111/112/113.
2. **Cloud and identity provider**, for PVC-091 and PVC-131.
3. **Approvers:** who may approve plans, and the escalation contact (PVC-060, PVC-064).
4. **Policy values:** freshness window, screening thresholds, flow-through rules, and prioritization weights (PVC-055). These should come from the fund's operating team, not engineering.
5. **Benchmark data source** and its licence terms (PVC-116).
