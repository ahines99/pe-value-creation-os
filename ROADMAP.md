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

## Release gates

### R0.1: Vertical slice (local, fixture data)
One lever (pricing) end to end on synthetic data: intake → sufficiency → diagnostics → sizing → evidence review → prioritization → plan → approval gate. No LLM inside the workflow; the MCP tools and the diagnostic Skill are used interactively from an MCP client such as Claude Code.

Exit criteria:
- [ ] `pytest` passes from a clean checkout with one setup command.
- [ ] A seeded demo shows a success path, a `NEEDS_EVIDENCE` pause, and survival of an injected tool failure.
- [ ] A run pauses at `AWAITING_APPROVAL`, survives a process restart, and resumes after a decision through the approval API.
- [ ] Every value number in the output traces to `size_value_case` with an `inputs_hash` and evidence ids.
- [ ] R0.1 items in the handoff's acceptance checklist are checked.

### R0.5: MVP / pilot-ready (staging, one real portco)
All four diagnostic levers, real data adapters for one portco, model reasoning at judgment steps, authentication and tenant isolation, an eval gate in CI, and a staging deployment. This is "MVP complete" as defined in the handoff.

Exit criteria:
- [ ] Golden dataset (≥25 cases) and adversarial suite pass their thresholds in CI.
- [ ] Cross-company access attempts fail closed in tests at both the tool layer and the database layer.
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
The project isn't a git repository.
- [ ] `git init`, a Python `.gitignore` (venv, caches, `.env`), and an initial commit of the current scaffold.
- [ ] Remote repository created, with branch protection on `main`.

### PVC-002: Fix test configuration
`P0 · S · R0.1 · deps: PVC-001`
Plain `pytest` fails with `ModuleNotFoundError: src.mcp_server`. Two async test plugins are configured.
- [ ] `pytest` and `python -m pytest` both pass from the repo root.
- [ ] `pytest-asyncio` and `asyncio_mode` removed. Tests use `pytestmark = pytest.mark.anyio`.
- [ ] The healthcheck test asserts `structured_content == {"status": "ok", "version": "0.1.0"}`.

### PVC-003: Package layout
`P0 · S · R0.1 · deps: PVC-002`
Move `src/*` into `src/pe_value_os/` and add a hatchling build system, following the handoff's package skeleton.
- [ ] `pip install -e .` works; imports are `pe_value_os.*`.
- [ ] Tests import `from pe_value_os.mcp_server import mcp`.

### PVC-004: Dependency management
`P0 · S · R0.1 · deps: PVC-003`
- [ ] `uv` project with a committed `uv.lock`. `uv sync --extra dev` sets up a working environment.
- [ ] Core dependencies are only `mcp[cli]>=2.2,<3` and `pydantic`. Postgres, HTTP and observability dependencies are in extras.
- [ ] README quick start updated to the `uv` workflow.

### PVC-005: Lint, format, type-check
`P1 · S · R0.1 · deps: PVC-004`
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` on `pe_value_os.domain` all pass.
- [ ] Pre-commit config runs ruff and checks for merge markers and large files.

### PVC-006: Continuous integration
`P0 · S · R0.1 · deps: PVC-004`
- [ ] A GitHub Actions workflow runs lint, types, and tests on Python 3.12, 3.13, and 3.14.
- [ ] CI is required for merges to `main`.

### PVC-007: Architecture decision records
`P2 · S · R0.1 · deps: PVC-001`
- [ ] `docs/adr/` with a template.
- [ ] ADRs recorded for: one MCP process with modules, an explicit state machine over Temporal for now, `Decimal` for money, and no model-callable approval.

## M1: Contracts and fixtures

### PVC-010: Core domain models
`P0 · M · R0.1 · deps: PVC-003`
Implement `Confidence`, `EvidenceRef`, `Finding`, and `AuditEvent` exactly as in the handoff.
- [ ] Field names and types match the SQL schema. A test compares model fields with table columns.
- [ ] `Finding` references evidence by id.

### PVC-011: Project models
`P0 · M · R0.1 · deps: PVC-010`
`Lever`, `ScenarioInputs`, `Opportunity`, and `ValueCase`.
- [ ] Rates are rejected outside `[0, 1]`. Scenario ordering is validated. `evidence_ids` has at least one item.
- [ ] Currency and rates are `Decimal`. JSON round-trip preserves precision.

### PVC-012: Source data schemas
`P0 · M · R0.1 · deps: PVC-010`
Pydantic schemas for fixture and adapter inputs: monthly P&L, customer subscriptions (ARR ledger), invoice lines and price books, support tickets, and product usage.
- [ ] Each schema has required fields, units, currency, and an `as_of` timestamp.
- [ ] Validation errors name the file, row, and field.

### PVC-013: Synthetic fixture companies
`P0 · L · R0.1 · deps: PVC-012`
Seeded generator for three fictional portcos: *Healthy*, *Pricing leak* (high discount dispersion, legacy price books), and *Churn problem* (front-loaded churn in one segment). Add one deliberately broken dataset with missing months, duplicate customers, stale `as_of`, and a document containing a prompt-injection string.
- [ ] Generator is deterministic from a seed. Output is committed under `tests/fixtures/`.
- [ ] Each company has a README listing the "planted" findings the system should discover.

### PVC-014: Data contracts documentation
`P1 · S · R0.1 · deps: PVC-011, PVC-012`
- [ ] `docs/data_contracts.md` covers every contract, units, and the schema-versioning policy (additive changes bump the minor version; breaking changes need a migration and ADR).

### PVC-015: Contract snapshot tests
`P2 · S · R0.5 · deps: PVC-014`
- [ ] JSON Schema for each contract is exported and snapshot-tested. CI fails on unreviewed breaking changes.

## M2: Deterministic calculation core

### PVC-020: Value-case sizing service
`P0 · M · R0.1 · deps: PVC-011`
Implement `services.size_value_case` as in the handoff.
- [ ] Golden tests hand-verify at least 10 cases, including zero realization, run cost exceeding benefit (negative EBITDA), and an EV multiple.
- [ ] `calc_version` and `inputs_hash` are populated. Identical inputs give an identical hash.

### PVC-023: Price waterfall service
`P0 · M · R0.1 · deps: PVC-012`
List → invoice → pocket price, with leakage by layer and discount dispersion by segment.
- [ ] Planted leakage in the *Pricing leak* fixture is recovered exactly.
- [ ] Output includes the evidence ids of the invoice and price-book sources used.

### PVC-024: Data-sufficiency checker
`P0 · M · R0.1 · deps: PVC-012`
For each analysis (`unit_economics`, `pricing`, `retention`, `ai_opportunity`), check required fields, minimum history, and freshness.
- [ ] Returns SUFFICIENT/INSUFFICIENT with a machine-readable gap list.
- [ ] The broken fixture produces the expected gaps. Stale data is flagged using the freshness window from policy config.

### PVC-025: Prioritization and value phasing
`P0 · M · R0.1 · deps: PVC-020`
A deterministic priority score from base EBITDA, confidence, time to value, and one-time cost, with weights in policy config. Add in-year phasing, computed separately from run-rate.
- [ ] Ties are broken deterministically. Changing weights changes the ranking predictably (tested).
- [ ] In-year value never exceeds run-rate value (property test).

### PVC-026: Policy and scope module
`P0 · S · R0.1 · deps: PVC-010`
`check_action`, `require_citations`, and `scope.require(company_id)`, with the allowed set taken from `PVC_ALLOWED_COMPANIES` for now.
- [ ] An out-of-scope company raises a typed error. An uncited value claim raises `PolicyViolation`.

### PVC-028: Baseline and flow-through derivation
`P0 · M · R0.1 · deps: PVC-012, PVC-026`
Server-side lookup that turns `(company_id, lever, baseline_metric)` into `baseline_value` and `ebitda_flow_through`, using company data and a policy table of flow-through rules by lever.
- [ ] Unknown metric names are rejected with the list of valid names.
- [ ] Every derived value carries the evidence ids it came from.

### PVC-021: SaaS metrics service
`P0 · L · R0.5 · deps: PVC-012`
ARR bridge, GRR, NRR, CAC payback, LTV/CAC, magic number, burn multiple, Rule of 40, and subscription gross margin, using the definitions in the `saas-unit-economics` skill.
- [ ] Each metric reports its variant and period. Periods are aligned or it raises an error.
- [ ] Planted values in all three fixture companies are recovered exactly.

### PVC-022: Retention cohort service
`P0 · M · R0.5 · deps: PVC-012`
Logo and dollar retention by cohort, split into voluntary and involuntary churn.
- [ ] The *Churn problem* fixture's planted segment and cohort pattern is recovered.
- [ ] GRR never exceeds 100% (property test).

### PVC-027: Property-based calculation tests
`P2 · S · R0.5 · deps: PVC-020, PVC-021`
- [ ] Hypothesis tests cover sizing monotonicity, ARR bridge identity, and GRR ≤ NRR.

## M3: Persistence and audit

### PVC-030: Postgres and migrations
`P0 · M · R0.1 · deps: PVC-004`
- [ ] `docker compose up db` starts Postgres. The Alembic migration creates every table in the handoff's data model.
- [ ] Upgrade and downgrade are tested in CI against a Postgres service container.

### PVC-031: Repository layer
`P0 · L · R0.1 · deps: PVC-010, PVC-011, PVC-030`
A repository interface with in-memory and Postgres implementations, selected by `get_repository()` from `DATABASE_URL`.
- [ ] One shared contract test suite runs against both implementations.
- [ ] Every query is filtered by `company_id`. A test proves one company can't read another's rows through the API.

### PVC-032: Evidence store
`P0 · M · R0.1 · deps: PVC-031`
Immutable originals, with derived text stored separately. Content-hash deduplication per company. Local filesystem backend now, object storage later.
- [ ] Re-ingesting the same file returns the existing `evidence_id`.
- [ ] Originals can't be overwritten through the API.

### PVC-033: Append-only audit log
`P0 · S · R0.1 · deps: PVC-030`
- [ ] The application database role has only INSERT and SELECT on `audit_events`. A test proves UPDATE and DELETE fail.
- [ ] `audit.emit` is used by the workflow runner and every mutating tool.

### PVC-035: Fixture source adapter
`P0 · M · R0.1 · deps: PVC-013, PVC-032`
Loads fixture companies as if they were source systems and registers each file as evidence.
- [ ] Loading a fixture company gives the same `evidence_id`s on every run.
- [ ] Malformed rows produce a sufficiency gap, not a crash.

### PVC-034: Row-level security
`P1 · M · R0.5 · deps: PVC-031`
- [ ] Postgres RLS policies on every company-scoped table, keyed on a session variable set per request.
- [ ] A test with RLS on and a deliberately unfiltered query still returns only in-scope rows.

## M4: Workflow engine

### PVC-040: Checkpointing workflow runner
`P0 · M · R0.1 · deps: PVC-031, PVC-033`
`run_steps`, `RunState`, and the `StateStore`/`AuditSink` protocols, as in the handoff, with a Postgres-backed state store.
- [ ] State is saved after every step. Every step emits start, complete, or fail audit events.

### PVC-041: Resume and idempotent reruns
`P0 · M · R0.1 · deps: PVC-040`
- [ ] Killing the process mid-run and calling `resume(run_id)` completes without re-executing finished steps (tested).
- [ ] Starting a run with an existing `idempotency_key` returns the existing run.

### PVC-042: Parallel diagnostics step
`P0 · S · R0.1 · deps: PVC-040`
- [ ] Branches run concurrently. One failed branch is recorded as a gap; if every branch fails, the step fails.

### PVC-043: Primary workflow on fixtures
`P0 · L · R0.1 · deps: PVC-020, PVC-023, PVC-024, PVC-025, PVC-028, PVC-035, PVC-041, PVC-042`
Wire every step to domain services. Opportunities are proposed by deterministic rules (for example, discount dispersion above the policy threshold proposes a discount-governance opportunity), with no LLM.
- [ ] The *Pricing leak* fixture produces the planted opportunity, sized, prioritized, and in a draft plan.
- [ ] The broken fixture pauses with `NEEDS_EVIDENCE` and lists its gaps.

### PVC-045: Command-line interface
`P1 · S · R0.1 · deps: PVC-043`
- [ ] `pvc run --company <id>`, `pvc resume <run_id>`, and `pvc status <run_id>` work against Postgres.

### PVC-046: Failure injection harness
`P0 · S · R0.1 · deps: PVC-035`
A fault-injecting adapter wrapper that can time out, raise, or return malformed data on a chosen call.
- [ ] Tests cover one failed diagnostic branch (run continues), a failure in value modeling (run fails cleanly), and resume after the fault clears.

### PVC-044: Timeouts and retries
`P1 · M · R0.5 · deps: PVC-041`
- [ ] Per-step timeouts (`anyio.fail_after`) and bounded retries with backoff, for adapter errors marked transient only.
- [ ] Retries are audited. Non-transient errors are not retried.

### PVC-047: Workflow engine decision record
`P2 · S · R0.5 · deps: PVC-044`
- [ ] ADR: stay on the explicit state machine or move to Temporal/Prefect, based on the timer, retry, and worker needs seen by R0.5.

## M5: MCP surface

### PVC-050: MCP server module structure
`P0 · S · R0.1 · deps: PVC-003`
- [ ] One `MCPServer`, with tools registered from modules per capability boundary (`portco_financials`, `crm`, `product_analytics`, `support`, `pricing`, `benchmark`, `value_model`, `workflow`).

### PVC-051: Intake tools
`P0 · S · R0.1 · deps: PVC-024, PVC-050`
`get_company_profile` and `check_data_sufficiency`.
- [ ] Typed Pydantic outputs, with a `scope.require` check first in each tool.

### PVC-052: Price waterfall tool
`P0 · S · R0.1 · deps: PVC-023, PVC-050`
- [ ] `price_waterfall(company_id, period, segment=None)` returns the typed waterfall with evidence ids.

### PVC-053: Value-model tools
`P0 · L · R0.1 · deps: PVC-020, PVC-025, PVC-028, PVC-031, PVC-050`
`record_finding`, `propose_opportunity`, `size_value_case`, `list_evidence`, and `prioritize_opportunities`.
- [ ] `propose_opportunity` rejects any caller-supplied baseline or flow-through. The server fills them in.
- [ ] `record_finding` enforces `require_citations`.
- [ ] Each mutating tool writes an audit event.

### PVC-054: Workflow tools
`P0 · S · R0.1 · deps: PVC-041, PVC-050`
`get_run_status` and `request_approval`.
- [ ] A test asserts that no registered tool can record an approval decision.

### PVC-055: Resources, prompts, and policy configuration
`P0 · M · R0.1 · deps: PVC-050`
Turn `project://policies` into a structured policy config: freshness window, screening thresholds used by the skills, flow-through rules, and prioritization weights. Add `company://{company_id}/data-inventory`, `run://{run_id}/summary`, and the `review_run` prompt.
- [ ] Policy config is versioned in the repo, loaded at startup, and its version appears in audit events.

### PVC-056: MCP integration tests
`P0 · M · R0.1 · deps: PVC-051 to PVC-055`
- [ ] Every tool has in-process `Client` tests for success, invalid arguments, and an out-of-scope `company_id`.
- [ ] Five golden end-to-end tests drive the vertical slice through MCP.

### PVC-057: Source data tools
`P0 · M · R0.5 · deps: PVC-110`
`get_financials`, `get_usage_metrics`, and `get_support_metrics`.
- [ ] Typed outputs with evidence ids and scope checks, plus tests.

### PVC-058: Metric tools
`P0 · S · R0.5 · deps: PVC-021, PVC-022`
`compute_saas_metrics` and `compute_retention_cohorts`.
- [ ] Typed outputs report the metric variant and period, plus tests.

### PVC-059: Tool description and schema review
`P2 · S · R0.5 · deps: PVC-058`
- [ ] Every tool description says what it does, what it won't do, and its units. Tool schemas are snapshot-tested.

## M6: Human approval

### PVC-060: Approval API
`P0 · M · R0.1 · deps: PVC-031`
A FastAPI endpoint, `POST /runs/{run_id}/approvals`, served separately from the MCP surface.
- [ ] Requires an authenticated human principal (a local dev token in R0.1; OAuth in R0.5).
- [ ] Rationale is required for `rejected` and `changes_requested`. Every decision is audited.

### PVC-061: Approval gate step
`P0 · M · R0.1 · deps: PVC-041, PVC-060`
- [ ] No decision → `AWAITING_APPROVAL`. Approved → `COMPLETE`. Rejected → `REJECTED`.
- [ ] `changes_requested` re-opens prioritization and later steps, with the reviewer's notes attached, and the run resumes from there (tested).

### PVC-062: Approval review view
`P1 · L · R0.5 · deps: PVC-060`
A minimal server-rendered page showing the plan, value cases with inputs, evidence links, and gaps, with approve, reject, and request-changes actions.
- [ ] Evidence links open the stored original. The page works without JavaScript frameworks.

### PVC-063: Human-override tracking
`P1 · S · R0.5 · deps: PVC-061`
- [ ] A diff between the proposed plan and the approved plan is stored and audited. An "override rate" metric is exposed.

### PVC-064: Approval expiry and escalation
`P2 · S · R1.0 · deps: PVC-061, PVC-134`
- [ ] Runs awaiting approval longer than the policy limit notify the escalation contact. Nothing is auto-approved.

## M7: Skills and model reasoning

### PVC-070: Diagnostic skill validated end to end
`P0 · M · R0.1 · deps: PVC-056`
- [ ] `pe-value-creation-diagnostic` has a worked example in `references/` from the *Pricing leak* fixture run.
- [ ] A manual session in an MCP client, using the skill, produces output that meets its output contract.

### PVC-075: Skill lint
`P1 · S · R0.1 · deps: PVC-050`
- [ ] A CI check validates skill frontmatter (name matches directory, description present).
- [ ] Every MCP tool a skill names must exist in the tool catalog. Planned tools are allowed only if listed with a ticket id.

### PVC-071: Lever skills completed and reviewed
`P1 · M · R0.5 · deps: PVC-058`
- [ ] Each lever skill has a `references/` worked example from a fixture run.
- [ ] A domain expert (operating partner or VCP lead) reviewed the definitions and diagnostic trees. Their sign-off is recorded.

### PVC-072: Model reasoning at judgment steps
`P0 · L · R0.5 · deps: PVC-043, PVC-080`
Replace the rule-based opportunity proposals, and add evidence synthesis and plan narrative, using Claude through the Anthropic SDK with structured outputs validated by Pydantic.
- [ ] One ADR per model-dependent decision explains why a rule isn't enough and names its eval.
- [ ] Model outputs never contain numbers that aren't copied from tool results (checked in eval).

### PVC-073: Prompt-injection defences
`P0 · M · R0.5 · deps: PVC-072`
- [ ] Retrieved text is passed as delimited data. Each step has a tool allowlist.
- [ ] Injected instructions in the broken fixture are recorded as `suspicious_content` and not followed (adversarial eval).

### PVC-074: Model outage fallback
`P1 · S · R0.5 · deps: PVC-072`
- [ ] If the model is unavailable, the run pauses at `NEEDS_EVIDENCE` with reason `model_unavailable` and can be resumed.

### PVC-076: Skill distribution
`P1 · S · R0.5 · deps: PVC-071`
- [ ] Documented, versioned way to install the skills in the MCP clients the team uses, such as a Claude Code plugin or project skills directory.

## M8: Evaluation

### PVC-080: Evaluation harness
`P0 · L · R0.5 · deps: PVC-056`
- [ ] `evals/` runner scores the seven dimensions in the handoff and writes a per-run report.

### PVC-081: Golden dataset
`P0 · L · R0.5 · deps: PVC-080`
- [ ] At least 25 cases across the four levers and three fixture companies, each with expected findings, opportunities, and value ranges.

### PVC-082: Adversarial suite
`P0 · M · R0.5 · deps: PVC-080`
- [ ] Cases cover prompt injection, stale data, duplicate entities, contradictory evidence, missing required fields, and a cross-portco lure. Every case fails closed.

### PVC-083: CI evaluation gate
`P1 · M · R0.5 · deps: PVC-081, PVC-082`
- [ ] Merges are blocked when scores drop below thresholds recorded in the repo. The full suite runs nightly.

### PVC-084: Cost and latency reporting
`P2 · S · R0.5 · deps: PVC-080, PVC-101`
- [ ] The eval report includes tokens, cost, and latency per run and per step.

## M9: Security and tenancy

### PVC-090: Threat model
`P0 · M · R0.5 · deps: PVC-060`
- [ ] `docs/threat_model.md` has a STRIDE analysis of the MCP surface, approval API, adapters, and model calls. It is reviewed, and each mitigation is linked to a ticket.

### PVC-091: MCP authentication
`P0 · L · R0.5 · deps: PVC-050`
- [ ] The Streamable HTTP MCP endpoint requires OAuth 2.1 bearer tokens, following the MCP authorization spec, behind the ASGI app. Unauthenticated calls are rejected.

### PVC-092: Company-scope authorization
`P0 · M · R0.5 · deps: PVC-034, PVC-091`
- [ ] `scope.require` reads allowed companies from token claims, and the same principal sets the RLS session variable.
- [ ] The environment-variable allow-list is removed outside dev.

### PVC-093: Secrets management
`P0 · S · R0.5 · deps: PVC-006`
- [ ] Secrets come from the environment in dev and a cloud secret manager in staging and prod. CI runs secret scanning. No secrets in skills or prompts.

### PVC-095: Log redaction
`P1 · S · R0.5 · deps: PVC-100`
- [ ] A test asserts that logs contain no raw financial values, customer names, or document text; only ids and hashes.

### PVC-096: Dependency and container scanning
`P1 · S · R0.5 · deps: PVC-130`
- [ ] `pip-audit` and a container scan run in CI. High and critical findings fail the build.

### PVC-094: Egress controls
`P1 · S · R1.0 · deps: PVC-136`
- [ ] A network egress allow-list for production covers the model provider, data sources, and telemetry. No tool can send email or write to source systems.

### PVC-097: External penetration test
`P1 · M · R1.0 · deps: PVC-136`
- [ ] A third-party test of the MCP endpoint, approval API, and tenancy isolation. Critical and high findings are fixed and retested.

## M10: Observability

### PVC-100: Structured logging
`P0 · S · R0.5 · deps: PVC-004`
- [ ] structlog JSON logs carry `run_id`, `company_id`, `step`, and `tool_name` context.

### PVC-101: Tracing
`P1 · M · R0.5 · deps: PVC-100`
- [ ] OpenTelemetry spans for run → step → tool → model call, exported over OTLP. Traces link to audit events by `run_id`.

### PVC-102: Metrics
`P1 · M · R1.0 · deps: PVC-101`
- [ ] Metrics for run outcomes, step latency, tool error rate, model tokens and cost, approval turnaround, and human-override rate.

### PVC-103: Dashboards and alerts
`P1 · M · R1.0 · deps: PVC-102, PVC-140`
- [ ] SLO dashboards, plus alerts on SLO burn, stuck runs, adapter failures, and eval regressions, routed to on-call.

## M11: Real data integrations

### PVC-110: Adapter contract and conformance suite
`P0 · M · R0.5 · deps: PVC-035`
- [ ] Every adapter implements one interface and must pass a shared conformance suite using recorded responses.
- [ ] ADR: a warehouse-first path (read from the portco's warehouse or dbt models) versus per-system APIs, decided for the pilot portco.

### PVC-111: Financials adapter
`P0 · L · R0.5 · deps: PVC-110`
- [ ] Monthly P&L from the pilot portco's source (warehouse, ERP export, or accounting system) passes conformance. Every load is registered as evidence.

### PVC-113: Billing and invoice adapter
`P0 · L · R0.5 · deps: PVC-110`
- [ ] Invoice lines, price books, and subscriptions from the pilot's billing system pass conformance. This feeds pricing and ARR.

### PVC-112: CRM adapter
`P1 · L · R0.5 · deps: PVC-110`
- [ ] Customers, opportunities, renewals, and churn reason codes (for example, Salesforce or HubSpot) pass conformance, read-only.

### PVC-117: Customer entity resolution
`P1 · M · R0.5 · deps: PVC-112, PVC-113`
- [ ] Deterministic matching of customers across CRM and billing, with a review queue for ambiguous matches. The duplicate-entity adversarial case passes.

### PVC-118: Data freshness monitoring
`P1 · S · R0.5 · deps: PVC-111`
- [ ] Each source's latest `as_of` is tracked. Stale sources show up in sufficiency checks and alerts.

### PVC-114: Product analytics adapter
`P2 · L · R1.0 · deps: PVC-110`
- [ ] Usage and feature adoption data passes conformance.

### PVC-115: Support adapter
`P2 · M · R1.0 · deps: PVC-110`
- [ ] Ticket volume, categories, handle time, and CSAT pass conformance.

### PVC-116: Benchmark data and tool
`P2 · M · R1.0 · deps: PVC-110`
- [ ] A licensed or anonymized peer dataset is ingested with its provenance, and the `get_benchmarks` tool is exposed. Portco-level values are never returned.

## M12: KPI monitoring

### PVC-120: KPI definitions from approved plans
`P0 · M · R1.0 · deps: PVC-061`
- [ ] Approval of a plan persists its KPIs (metric, baseline, targets, cadence, source). Unmonitorable KPIs are rejected at approval time.

### PVC-121: Scheduled KPI refresh and status tool
`P0 · M · R1.0 · deps: PVC-120, PVC-134`
- [ ] A worker job refreshes KPIs on their cadence. The `get_kpi_status(company_id)` tool returns plan-vs-actual with evidence.

### PVC-122: Variance detection
`P0 · S · R1.0 · deps: PVC-121`
- [ ] Deterministic off-track rules (threshold and trend) have configurable tolerances and are audited.

### PVC-123: KPI digests
`P1 · M · R1.0 · deps: PVC-122`
- [ ] A read-only digest to an approved channel lists off-track KPIs with links. The channel is configured by a human; the model can't send messages.

### PVC-124: Plan-vs-actual view
`P2 · M · R1.0 · deps: PVC-121, PVC-062`
- [ ] A page per company shows KPI history, targets, and the linked initiatives.

## M13: Deployment and infrastructure

### PVC-130: Container images
`P0 · S · R0.5 · deps: PVC-004`
- [ ] A multi-stage Dockerfile with a non-root user. `docker compose up` runs db, MCP server, approval API, and worker locally.

### PVC-131: Staging environment as code
`P0 · L · R0.5 · deps: PVC-130`
- [ ] Terraform (or equivalent) for staging networking, compute, Postgres, secrets, and object storage in the chosen cloud.

### PVC-132: Managed Postgres
`P0 · M · R0.5 · deps: PVC-131`
- [ ] Encryption at rest, point-in-time recovery, automated backups, and least-privilege roles (application, migration, read-only).

### PVC-133: Continuous delivery
`P0 · M · R0.5 · deps: PVC-131, PVC-096`
- [ ] Pipeline: build, scan, migrate, deploy, and smoke test. Staging deploys automatically; production needs a manual approval.

### PVC-134: Worker process
`P1 · M · R0.5 · deps: PVC-044`
- [ ] Workflow execution and scheduled jobs run in a worker process separate from the MCP server. Restarting the MCP server doesn't interrupt runs.

### PVC-135: Ingress and TLS
`P0 · S · R0.5 · deps: PVC-131`
- [ ] TLS everywhere, rate limiting, and request size limits on the MCP and approval endpoints.

### PVC-136: Production environment
`P0 · M · R1.0 · deps: PVC-131, PVC-154`
- [ ] Production is provisioned from the same code as staging, with separate accounts or projects and credentials.

## M14: Production readiness

### PVC-145: Calculation versioning policy
`P1 · S · R0.5 · deps: PVC-020`
- [ ] Changing a calculation bumps `calc_version`. Stored value cases keep their version. Recomputing requires an explicit, audited action.

### PVC-147: Model provider data-handling review
`P0 · S · R0.5 · deps: PVC-072`
- [ ] Data-processing terms and retention settings for the model provider are confirmed, and the portco data classes sent to the model are documented and approved *before* pilot data reaches a model.

### PVC-140: Service level objectives
`P0 · S · R1.0 · deps: PVC-102`
- [ ] SLOs are defined for API availability, p95 run duration by step, and eval score floors.

### PVC-141: Runbooks
`P0 · M · R1.0 · deps: PVC-103`
- [ ] `docs/runbooks/` covers stuck or failed runs, adapter outage, model outage, a bad calculation release (rollback and recompute), a suspected cross-company data exposure, and database restore.

### PVC-142: Backup restore drill
`P0 · S · R1.0 · deps: PVC-132`
- [ ] RPO and RTO targets are set. A restore to a fresh instance is performed and timed, and the results are recorded.

### PVC-143: Load test
`P1 · M · R1.0 · deps: PVC-134`
- [ ] Target concurrency (runs and MCP sessions) is sustained within SLOs. Bottlenecks are documented.

### PVC-144: Data retention and deletion
`P0 · M · R1.0 · deps: PVC-032`
- [ ] A retention policy per data class. Portco offboarding deletes that company's data and evidence, verified by a test, while audit records are kept as the policy requires.

### PVC-146: Access review and audit export
`P1 · M · R1.0 · deps: PVC-092`
- [ ] Quarterly access-review report and audit-log export per company, aligned with the fund's compliance requirements (for example, SOC 2 controls).

### PVC-148: On-call and incident process
`P1 · S · R1.0 · deps: PVC-103`
- [ ] On-call rotation, severity levels, incident template, and a post-incident review process.

## M15: Demo, pilot, and general availability

### PVC-150: One-command seeded demo
`P0 · M · R0.1 · deps: PVC-043, PVC-046, PVC-061`
- [ ] `make demo` (or `uv run pvc demo`) seeds fixtures and shows the success path, the `NEEDS_EVIDENCE` pause, an injected failure, and approval and resume.

### PVC-151: Architecture diagram and README
`P1 · S · R0.1 · deps: PVC-150`
- [ ] `docs/architecture.md` has a layer and data-flow diagram. The README is updated with the demo and the "Why this is not just a chatbot" section.

### PVC-152: Demo script
`P2 · S · R0.1 · deps: PVC-150`
- [ ] A 3-minute recorded-demo script covering one success path and one controlled failure.

### PVC-153: Pilot with one portfolio company
`P0 · L · R1.0 · deps: R0.5 gate, PVC-147`
Run on the pilot portco's real data in staging, read-only, with the deal team and operating partner as approvers.
- [ ] At least two complete diagnostic runs are reviewed by humans. The override rate and reviewer feedback are recorded.
- [ ] Every opportunity the reviewers dispute has a root cause (data, calculation, skill, or model) and a ticket.

### PVC-154: Pilot retrospective and go/no-go
`P0 · S · R1.0 · deps: PVC-153`
- [ ] A written retrospective and a signed go/no-go decision, with conditions for production.

### PVC-155: Portco onboarding playbook
`P0 · M · R1.0 · deps: PVC-154`
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
