# 01. PE Portfolio Value Creation Operating System

## Implementation-agent handoff

> **Revision 3 (2026-09-23).** The system described here is now built and verified locally; see [Current state](#current-state-verified-2026-09-23). Revision 2 fixed the design gaps found in review and moved milestone planning to [ROADMAP.md](ROADMAP.md), which carries the per-ticket status. See [Changes in this revision](#changes-in-this-revision) at the end.

### Mission
Turn portfolio-company operating data into evidence-backed value-creation initiatives, deterministic economic cases, 100-day plans, and KPI monitoring.

### Definition of done (MVP)
A credible MVP is not a chat demo. It must expose typed MCP capabilities, persist workflow state, preserve evidence/provenance, stop at approval boundaries, include at least one Agent Skill with real domain procedure, and ship with integration tests. The demonstration should show a complete end-to-end run with both a successful path and a controlled failure/review path.

Production readiness criteria are defined in [ROADMAP.md](ROADMAP.md#release-gates).

### Non-goals for v0.1
- Do not build autonomous irreversible actions.
- Do not let the LLM become the system of record.
- Do not hide deterministic calculations inside prompts.
- Do not create a generalized multi-agent framework before the primary workflow works.
- Do not optimize UI before evidence, contracts, and tests are stable.

## Current state (verified 2026-09-23)

The specification below is implemented in `src/pe_value_os/` and verified on this machine. It has not yet run in GitHub Actions or on AWS, because no remote repository or cloud account is connected yet. [ROADMAP.md](ROADMAP.md#status) has the per-ticket status. [docs/architecture.md](docs/architecture.md) has the architecture as built.

| Area | State |
|---|---|
| Contracts, fixtures, deterministic core (sizing, metrics, retention, pricing, sufficiency, prioritization, baselines) | Built. Golden, property-based and snapshot tests. |
| PostgreSQL schema, repository, RLS, append-only audit, evidence store (filesystem and S3) | Built. The contract suite runs against both the in-memory and PostgreSQL 18 implementations. |
| Workflow engine and primary workflow | Built: checkpoints, resume, rewind, parallel diagnostics, timeouts, transient-only retries, fault injection |
| MCP server | 21 tools, 3 resources, 1 prompt. OAuth bearer auth, company scope from token claims, strict arguments, DNS-rebinding protection. |
| Approval API and review UI | Built. Human principals only, CSRF, override diff and rate, expiry escalation. |
| Model layer | Claude proposer and narrator with JSON-schema output, the no-new-numbers guardrail, delimited untrusted text, and a pause when the model is unavailable. Covered by scripted-model tests. **Not yet run against the live API.** |
| Evals | 29 golden and 9 adversarial cases, 7 dimensions. The gate passes at 100%. Per-step latency and model cost are reported. |
| Adapters | Fixture, CSV export, warehouse, Stripe, HubSpot, Zendesk, and composite with entity resolution. Vendor adapters are tested against simulated APIs. None has run against a real portfolio company's systems. |
| KPI monitoring, worker, notifications | Built |
| Observability | structlog JSON with allow-list redaction, OpenTelemetry traces and metrics, a Grafana dashboard and Prometheus alerts (promtool-valid) |
| Ops tooling | `pvc recompute`, `offboard`, `access-review`, `audit-export`, `onboard-check`. Restore drill and load test run locally. |
| Container, Terraform (AWS), CD | Written. Terraform passes `fmt`, `validate` and `test`. Workflows pass actionlint. **Image not yet built. Nothing applied.** |
| Sign-offs, pen test, legal, on-call, pilot | Not started. They need named people or a pilot company (ROADMAP "Open decisions"). |

Verification on 2026-09-23 (Python 3.14, `mcp` 2.2.0, PostgreSQL 18):

- `uv sync --extra dev && uv run pytest`: 250 passed with `PVC_TEST_DATABASE_URL` set. From a clean clone without a database: 227 passed, and the 23 PostgreSQL tests are skipped.
- `ruff check`, `ruff format --check`, `mypy` and the skills lint are clean. `pip-audit` finds no known vulnerabilities in the locked runtime dependencies.
- `pvc eval --suite all --gate` passes. `pvc demo` runs all five scenarios. `python -m pe_value_os.db.migrate_check` round-trips.
- `pvc run`, `status` and `resume` work against PostgreSQL as the row-level-security-bound `pvc_app` role.

## Reference architecture

Use a four-layer design:

1. **Data and capability layer**: source systems, deterministic calculation services, document/evidence stores, and domain APIs.
2. **MCP boundary**: small servers that expose typed tools, resources, and user-selectable prompts. MCP is the capability contract, not the business logic layer.
3. **Skill layer**: Agent Skills package procedural knowledge, review checklists, reference material, and scripts. A Skill should teach *how to perform the work*, not become a hidden database or hard-coded workflow engine.
4. **Workflow/orchestration layer**: state machine or durable workflow service coordinates steps, approvals, retries, parallel branches, and audit events.

**Why this split**
- Deterministic services own arithmetic, portfolio math, joins, permissions, and irreversible side effects.
- MCP gives the model a standardized, inspectable capability surface.
- Skills keep domain operating procedures version-controlled and progressively disclosed.
- The workflow engine owns state and recovery, preventing the LLM conversation itself from becoming the source of truth.

**Division of labour between model and system.** The model supplies *judgment*: which levers to investigate, scenario assumptions (improvement and realization rates), rationale, and narrative. The system supplies *facts and arithmetic*: baseline values, margins, metric calculations, value-case sizing, prioritization scores, and permissions. A tool never accepts a baseline number from the model.

For local development use MCP over stdio or in-process tests. For deployed servers use Streamable HTTP behind authenticated ASGI infrastructure. Use the Python MCP SDK v2 (`mcp>=2.2,<3`) and Python 3.12+.

## Recommended stack

- Python 3.12+ (CI matrix: 3.12, 3.13, 3.14)
- `uv` for environment/package management, with a committed `uv.lock`
- MCP Python SDK v2
- FastAPI/Starlette only where non-MCP HTTP endpoints are needed. The first such endpoint is the **human approval API** (humans approve; the model cannot).
- Pydantic v2 for contracts; `Decimal` for all currency and rates
- PostgreSQL for operational state and audit logs, with row-level security on `company_id`
- Alembic for migrations
- pgvector or a managed vector store only where semantic retrieval is genuinely required
- Neo4j only for graph-heavy projects, not by default
- DuckDB/Polars for local analytical execution
- dbt for warehouse transformations where applicable
- A small explicit state machine for workflows. Revisit Temporal/Prefect only if retries, timers, or distributed workers justify it (ADR, PVC-047).
- OpenTelemetry for traces and metrics; structlog for JSON logs
- pytest with the anyio plugin + MCP in-process client tests
- Docker for reproducible deployment

Do not make the agent framework the center of the repository. Keep orchestration behind interfaces so Claude, another model, or a deterministic job can drive the same domain services.

## Project architecture

### MCP capability boundaries

Run **one MCP server process** for v0.1, with one Python module per capability boundary. Split into separate servers only when a boundary gets distinct authorization, lifecycle, or deployment needs.

| Module | Capability |
|---|---|
| `portco_financials` | P&L, balance sheet, headcount, S&M and COGS detail |
| `crm` | Customers, opportunities, renewals, churn reason codes |
| `product_analytics` | Usage and adoption metrics |
| `support` | Ticket volumes, categories, handle time, CSAT |
| `pricing` | Price books, invoice lines, discounts, price waterfall |
| `benchmark` | Anonymized peer-set metrics with provenance |
| `value_model` | Opportunities, value cases, findings, evidence, prioritization, KPIs |
| `workflow` | Run status and approval requests |

### MCP tool catalog

Every tool that touches company data takes `company_id` and enforces scope server-side. Status: **built**, or the ROADMAP ticket that delivers it.

| Tool | Module | Purpose | Status |
|---|---|---|---|
| `healthcheck()` | core | Service health | built |
| `get_company_profile(company_id)` | portco_financials | Business model, scale, fiscal calendar | built |
| `get_financials(company_id, period_start, period_end)` | portco_financials | Monthly P&L lines | built |
| `get_churn_summary(company_id, period)` | crm | Trailing-12-month churned logos by churn type, voluntary reason codes, renewal win/loss counts | built |
| `get_usage_metrics(company_id, period)` | product_analytics | Active accounts, feature adoption | built |
| `get_support_metrics(company_id, period)` | support | Volumes, categories, handle time, CSAT | built |
| `price_waterfall(company_id, period, segment=None)` | pricing | List → invoice → pocket price and leakage | built |
| `get_benchmarks(metric, peer_set)` | benchmark | Anonymized peer distribution (at least 5 peers; never portco-level values) | built on a synthetic peer set; real data source is open (PVC-116) |
| `check_data_sufficiency(company_id, analysis)` | value_model | SUFFICIENT/INSUFFICIENT plus a gap list per analysis | built |
| `compute_saas_metrics(company_id, period)` | value_model | ARR bridge, NRR, GRR, CAC payback, LTV/CAC, magic number, burn multiple, Rule of 40 | built |
| `compute_retention_cohorts(company_id, cohort_grain)` | value_model | Logo and dollar retention by cohort | built |
| `record_finding(run_id, finding_type, title, statement, confidence, evidence_ids, ...)` | value_model | Persist a finding; rejects uncited value claims | built |
| `propose_opportunity(run_id, lever, baseline_metric, ...)` | value_model | Model proposes scenario rates and evidence; server fills in baseline and flow-through | built |
| `size_value_case(company_id, opportunity_id, ev_multiple=None)` | value_model | Deterministic low/base/high EBITDA sizing | built |
| `list_evidence(company_id, opportunity_id)` | value_model | Evidence linked to an opportunity | built |
| `prioritize_opportunities(run_id)` | value_model | Deterministic priority scores | built |
| `draft_100_day_plan(run_id)` | value_model | Workstreams, initiatives and KPIs from prioritized value cases | built |
| `get_kpi_status(company_id)` | value_model | Plan-vs-actual for approved KPIs | built |
| `start_diagnostic_run(company_id, mode, idempotency_key)` | workflow | Start an interactive or automated run (idempotent) | built |
| `get_run_status(run_id)` | workflow | Current step, status, gaps | built |
| `request_approval(run_id)` | workflow | Pause the run for human review | built |

There is deliberately **no** `approve` tool. Approval decisions come only through the authenticated human approval API (PVC-060).

Resources (all built): `project://policies`, `company://{company_id}/data-inventory`, `run://{run_id}/summary`. Prompt (built): `review_run(run_id)`.

### Agent Skills
- `pe-value-creation-diagnostic`: orchestrating procedure for a full diagnostic run.
- `saas-unit-economics`: growth-efficiency metrics and diagnostic trees.
- `pricing-value-creation`: price waterfall, leakage, and price-increase sizing.
- `customer-retention`: GRR/NRR decomposition and retention sizing.
- `ai-opportunity-assessment`: automation and AI candidate scoring and sizing.
- `100-day-planning`: turn approved value cases into a governed plan.

**Decision:** Skills contain checklists, decision rules, diagnostic trees, and output contracts. They do not embed secrets, thresholds that belong in policy configuration, or mutable state. Frontmatter advertises the Skill, the body provides procedure, and `references/` or `scripts/` hold deeper material only when needed.

### Primary workflow

A diagnostic run ends at human approval. KPI monitoring is a **separate scheduled job** started by an approved plan, not a step in the same run.

1. `intake`: load company profile and data inventory.
2. `data_sufficiency`: per-analysis check. Insufficient analyses are skipped with gaps recorded, not guessed.
3. `diagnostics`: runs **in parallel** (anyio task group), with branches `unit_economics`, `pricing`, `retention`, `ai_opportunity`. A failed branch is recorded as a gap; the run fails only if every branch fails.
4. `value_modeling`: deterministic sizing of each proposed opportunity.
5. `evidence_review`: every value claim resolves to stored evidence. Otherwise the run pauses with `NEEDS_EVIDENCE`.
6. `prioritization`: deterministic scoring.
7. `roadmap_100_day`: plan built from prioritized, sized opportunities.
8. `human_approval`: the run pauses at `AWAITING_APPROVAL` until a human decides through the approval API.

After approval, the `kpi_monitoring` job runs on a schedule against the approved plan's KPIs.

### Human approval boundaries
- No autonomous management actions
- No LLM-authored financial arithmetic
- No cross-portco data leakage (enforced by `company_id` scope checks and Postgres row-level security, not by prompts)
- No uncited value claim (enforced by `record_finding` and the evidence-review step)

## Data and state model

Use PostgreSQL as the workflow source of truth. Every company-scoped table carries `company_id` so row-level security can enforce tenancy. Minimum tables:

```sql
create table companies (
  company_id text primary key,
  name text not null,
  created_at timestamptz not null default now()
);

create table workflow_runs (
  run_id uuid primary key,
  company_id text not null references companies(company_id),
  project_type text not null,
  status text not null,
  current_step text,
  completed_steps jsonb not null default '[]'::jsonb,
  state jsonb not null default '{}'::jsonb,          -- checkpoint for resume
  idempotency_key text unique,
  schema_version int not null default 1,
  requested_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table evidence (
  evidence_id uuid primary key,
  company_id text not null references companies(company_id),
  run_id uuid references workflow_runs(run_id),       -- null when evidence predates a run
  source_uri text not null,
  source_type text not null,
  as_of timestamptz,
  retrieved_at timestamptz not null default now(),
  content_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  unique (company_id, content_hash)
);

create table findings (
  finding_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  finding_type text not null,
  title text not null,
  statement text not null,
  confidence text not null check (confidence in ('low', 'medium', 'high')),
  assumptions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table finding_evidence (
  finding_id uuid references findings(finding_id),
  evidence_id uuid references evidence(evidence_id),
  relation text not null,                             -- supports | contradicts | context
  primary key (finding_id, evidence_id, relation)
);

create table opportunities (
  opportunity_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  lever text not null,
  baseline_metric text not null,
  baseline_value numeric not null,
  ebitda_flow_through numeric not null,
  scenarios jsonb not null,                           -- low/base/high rates
  annual_run_cost numeric not null default 0,
  one_time_cost numeric not null default 0,
  confidence text not null,
  rationale text not null,
  created_at timestamptz not null default now()
);

create table opportunity_evidence (
  opportunity_id uuid references opportunities(opportunity_id),
  evidence_id uuid references evidence(evidence_id),
  primary key (opportunity_id, evidence_id)
);

create table value_cases (
  value_case_id uuid primary key,
  opportunity_id uuid not null references opportunities(opportunity_id),
  company_id text not null references companies(company_id),
  annual_ebitda_low numeric not null,
  annual_ebitda_base numeric not null,
  annual_ebitda_high numeric not null,
  ev_multiple numeric,
  calc_version text not null,
  inputs_hash text not null,
  created_at timestamptz not null default now()
);

create table approvals (
  approval_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  artifact_type text not null,
  artifact_id uuid not null,
  decision text check (decision in ('approved', 'rejected', 'changes_requested')),
  decided_by text,                                    -- human principal; never a model
  rationale text,
  requested_at timestamptz not null default now(),
  decided_at timestamptz
);

-- Append-only: the application role gets INSERT and SELECT only.
create table audit_events (
  event_id bigserial primary key,
  run_id uuid references workflow_runs(run_id),
  company_id text not null,
  step text not null,
  actor text not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
```

### Core contracts

```python
# src/pe_value_os/domain/models.py
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field

class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class EvidenceRef(BaseModel):
    evidence_id: str
    company_id: str
    source_uri: str
    source_type: str
    retrieved_at: datetime
    as_of: datetime | None = None
    content_hash: str

class Finding(BaseModel):
    finding_id: str
    run_id: str
    company_id: str
    finding_type: str
    title: str
    statement: str
    confidence: Confidence
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class AuditEvent(BaseModel):
    run_id: str | None
    company_id: str
    step: str
    event_type: str
    actor: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
```

### Project-specific contracts

Rates are fractions in `[0, 1]` (`0.05` means 5%) to remove the "is 10 ten percent or a thousand percent" ambiguity.

```python
# src/pe_value_os/domain/project_models.py
from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator
from .models import Confidence

class Lever(StrEnum):
    PRICING = "pricing"
    RETENTION = "retention"
    SALES_EFFICIENCY = "sales_efficiency"
    GROSS_MARGIN = "gross_margin"
    AI_AUTOMATION = "ai_automation"

class ScenarioInputs(BaseModel):
    improvement_rate: Decimal = Field(ge=0, le=1, description="Fraction of baseline improved, 0.05 = 5%")
    realization_rate: Decimal = Field(ge=0, le=1, description="Fraction of the improvement actually captured")

    @property
    def effective_rate(self) -> Decimal:
        return self.improvement_rate * self.realization_rate

class Opportunity(BaseModel):
    opportunity_id: str
    company_id: str
    lever: Lever
    baseline_metric: str                                  # e.g. "renewing_arr", "annual_churned_arr"
    baseline_value: Decimal = Field(ge=0)                 # server-populated from company data
    ebitda_flow_through: Decimal = Field(gt=0, le=1)      # server-populated from margins/policy
    low: ScenarioInputs
    base: ScenarioInputs
    high: ScenarioInputs
    annual_run_cost: Decimal = Field(default=Decimal(0), ge=0)
    one_time_cost: Decimal = Field(default=Decimal(0), ge=0)
    confidence: Confidence
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def scenarios_ordered(self) -> "Opportunity":
        if not (self.low.effective_rate <= self.base.effective_rate <= self.high.effective_rate):
            raise ValueError("Scenario effective rates must satisfy low <= base <= high")
        return self

class ValueCase(BaseModel):
    opportunity_id: str
    annual_ebitda_low: Decimal
    annual_ebitda_base: Decimal
    annual_ebitda_high: Decimal
    one_time_cost: Decimal
    ev_multiple: Decimal | None = Field(default=None, gt=0)
    ev_impact_base: Decimal | None = None
    calc_version: str
    inputs_hash: str
```

### Deterministic sizing service

```python
# src/pe_value_os/domain/services.py
import hashlib
from decimal import Decimal
from .project_models import Opportunity, ScenarioInputs, ValueCase

CALC_VERSION = "value-case/1"

def _scenario_ebitda(opp: Opportunity, s: ScenarioInputs) -> Decimal:
    gross = opp.baseline_value * s.effective_rate * opp.ebitda_flow_through
    return gross - opp.annual_run_cost

def size_value_case(opp: Opportunity, ev_multiple: Decimal | None = None) -> ValueCase:
    base = _scenario_ebitda(opp, opp.base)
    return ValueCase(
        opportunity_id=opp.opportunity_id,
        annual_ebitda_low=_scenario_ebitda(opp, opp.low),
        annual_ebitda_base=base,
        annual_ebitda_high=_scenario_ebitda(opp, opp.high),
        one_time_cost=opp.one_time_cost,
        ev_multiple=ev_multiple,
        ev_impact_base=base * ev_multiple if ev_multiple is not None else None,
        calc_version=CALC_VERSION,
        inputs_hash=hashlib.sha256(opp.model_dump_json().encode()).hexdigest(),
    )
```

Results are run-rate annual EBITDA. In-year phasing is a separate calculation (PVC-025), and must never be presented as run-rate.

### Project-specific MCP tools

```python
# add to src/pe_value_os/mcp_server.py
from decimal import Decimal
from .adapters.repositories import get_repository
from .domain import services
from .domain.models import EvidenceRef
from .domain.project_models import ValueCase
from .security import scope
from .observability import audit

@mcp.tool()
def size_value_case(company_id: str, opportunity_id: str, ev_multiple: Decimal | None = None) -> ValueCase:
    """Size low/base/high annual run-rate EBITDA impact for a stored opportunity.

    Baseline values and flow-through come from ingested company data, never from the caller.
    """
    scope.require(company_id)
    repo = get_repository()
    opp = repo.get_opportunity(company_id, opportunity_id)
    case = services.size_value_case(opp, ev_multiple)
    repo.save_value_case(company_id, case)
    audit.emit(company_id=company_id, step="value_modeling", event_type="value_case_sized",
               payload={"opportunity_id": opportunity_id, "inputs_hash": case.inputs_hash})
    return case

@mcp.tool()
def list_evidence(company_id: str, opportunity_id: str) -> list[EvidenceRef]:
    """List evidence linked to one opportunity."""
    scope.require(company_id)
    return get_repository().evidence_for_opportunity(company_id, opportunity_id)
```

`scope.require` raises if the calling principal may not access `company_id`. In v0.1 the allowed set comes from the `PVC_ALLOWED_COMPANIES` environment variable. In production it comes from OAuth token claims (PVC-091/092). `get_repository()` returns the in-memory repository in tests and the Postgres repository when `DATABASE_URL` is set.

## Repository skeleton

Target layout. Items marked ✅ exist today. Everything else is planned in [ROADMAP.md](ROADMAP.md).

```text
pe-value-creation-os/
├── pyproject.toml                 ✅ (needs PVC-002/003/004 fixes)
├── uv.lock
├── README.md                      ✅
├── IMPLEMENTATION_HANDOFF.md      ✅
├── ROADMAP.md                     ✅
├── .env.example
├── docker-compose.yml
├── migrations/                    # Alembic
├── src/pe_value_os/               # currently src/ with no package name (PVC-003)
│   ├── mcp_server.py              ✅ (partial)
│   ├── security.py                # scope checks
│   ├── observability.py           # structlog, OTel, audit emitter
│   ├── domain/
│   │   ├── models.py              ✅ (partial)
│   │   ├── project_models.py
│   │   ├── services.py
│   │   ├── metrics.py             # SaaS, retention, pricing calculations
│   │   └── policies.py
│   ├── adapters/
│   │   ├── repositories.py        # interface + in-memory + Postgres
│   │   ├── fixtures.py            # fixture-backed source systems
│   │   └── external.py
│   ├── workflows/
│   │   ├── base.py
│   │   ├── steps.py
│   │   └── primary.py
│   └── api/
│       └── approvals.py           # human-only approval endpoint (FastAPI)
├── skills/                        ✅ six skills
├── tests/
│   ├── test_mcp.py                ✅ (partial)
│   ├── test_services.py
│   ├── test_workflow.py
│   ├── test_policies.py
│   └── fixtures/
├── evals/
│   └── golden/
└── docs/
    ├── architecture.md
    ├── data_contracts.md
    ├── threat_model.md
    └── runbooks/
```

## Package skeleton

Corrections from revision 1: a build system and package path (fixes the `pytest` import failure), a single async test plugin, and heavy dependencies moved to extras until they are used.

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "pe-value-creation-os"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "mcp[cli]>=2.2,<3",
  "pydantic>=2.9",
]

[project.optional-dependencies]
postgres = ["sqlalchemy>=2.0", "psycopg[binary]>=3.2", "alembic>=1.13"]
http = ["fastapi>=0.115", "uvicorn>=0.30"]
observability = ["structlog>=24.4", "opentelemetry-api>=1.27", "opentelemetry-sdk>=1.27"]
dev = ["pytest>=8", "anyio>=4", "ruff>=0.7", "mypy>=1.12"]

[tool.hatch.build.targets.wheel]
packages = ["src/pe_value_os"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

## MCP server skeleton

```python
# src/pe_value_os/mcp_server.py
from __future__ import annotations
from mcp.server import MCPServer
from pydantic import BaseModel

mcp = MCPServer("PE Portfolio Value Creation Operating System")

class Health(BaseModel):
    status: str
    version: str

@mcp.tool()
def healthcheck() -> Health:
    """Return service health for diagnostics."""
    return Health(status="ok", version="0.1.0")

@mcp.resource("project://policies")
def policies() -> str:
    """Human-readable operating and safety policies."""
    return (
        "No autonomous management actions | No LLM-authored financial arithmetic | "
        "No cross-portco data leakage | No uncited value claim"
    )

@mcp.prompt()
def review_run(run_id: str) -> str:
    """Create a user-controlled review prompt for a workflow run."""
    return f"Review workflow run {run_id}. Separate facts, assumptions, and recommendations."

app = mcp.streamable_http_app()
```

## Workflow skeleton

Revision 1's runner could stop at a review point but could not resume. This version checkpoints after every step, skips completed steps on resume, and treats approval as a gate step that re-checks for a decision each time it runs.

```python
# src/pe_value_os/workflows/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_EVIDENCE = "needs_evidence"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    REJECTED = "rejected"
    FAILED = "failed"

PAUSED = {Status.NEEDS_EVIDENCE, Status.AWAITING_APPROVAL}

@dataclass
class RunState:
    run_id: str
    company_id: str
    status: Status = Status.PENDING
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

class Step(Protocol):
    name: str
    async def execute(self, state: RunState) -> RunState: ...

class StateStore(Protocol):
    async def load(self, run_id: str) -> RunState | None: ...
    async def save(self, state: RunState) -> None: ...

class AuditSink(Protocol):
    async def emit(self, state: RunState, event_type: str, **payload: Any) -> None: ...

async def run_steps(state: RunState, steps: list[Step], store: StateStore, audit: AuditSink) -> RunState:
    """Run or resume a workflow. Completed steps are skipped, so reruns are idempotent."""
    state.status = Status.RUNNING
    for step in steps:
        if step.name in state.completed_steps:
            continue
        state.current_step = step.name
        await audit.emit(state, "step_started")
        try:
            state = await step.execute(state)
        except Exception as exc:
            state.errors.append(f"{step.name}: {exc!r}")
            state.status = Status.FAILED
            await store.save(state)
            await audit.emit(state, "step_failed", error=repr(exc))
            return state
        if state.status in PAUSED or state.status == Status.REJECTED:
            await store.save(state)
            await audit.emit(state, f"run_{state.status}")
            return state
        state.completed_steps.append(step.name)
        await store.save(state)
        await audit.emit(state, "step_completed")
    state.status = Status.COMPLETE
    state.current_step = None
    await store.save(state)
    await audit.emit(state, "run_completed")
    return state
```

## Primary workflow implementation

```python
# src/pe_value_os/workflows/primary.py
from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
import anyio
from .base import AuditSink, RunState, StateStore, Step, run_steps

StepFn = Callable[[RunState], Awaitable[Any]]

@dataclass
class FunctionalStep:
    name: str
    fn: StepFn

    async def execute(self, state: RunState) -> RunState:
        state.artifacts[self.name] = await self.fn(state)
        return state

@dataclass
class ParallelStep:
    """Run diagnostic branches concurrently. Partial failure is recorded, not fatal."""
    name: str
    branches: dict[str, StepFn]

    async def execute(self, state: RunState) -> RunState:
        results: dict[str, Any] = {}
        failures: dict[str, str] = {}

        async def run(key: str, fn: StepFn) -> None:
            try:
                results[key] = await fn(state)
            except Exception as exc:
                failures[key] = repr(exc)

        async with anyio.create_task_group() as tg:
            for key, fn in self.branches.items():
                tg.start_soon(run, key, fn)

        if not results:
            raise RuntimeError(f"All diagnostic branches failed: {failures}")
        state.artifacts[self.name] = {"results": results, "failures": failures}
        state.errors.extend(f"{self.name}.{k}: {v}" for k, v in failures.items())
        return state

DIAGNOSTIC_BRANCHES = ["unit_economics", "pricing", "retention", "ai_opportunity"]
SEQUENTIAL_STEPS_BEFORE = ["intake", "data_sufficiency"]
SEQUENTIAL_STEPS_AFTER = ["value_modeling", "evidence_review", "prioritization", "roadmap_100_day", "human_approval"]

async def run_primary(state: RunState, services, store: StateStore, audit: AuditSink) -> RunState:
    """Start or resume the diagnostic run. `services.for_step(name)` returns a domain service
    whose `execute` returns structured data, not prose."""
    steps: list[Step] = [FunctionalStep(n, services.for_step(n).execute) for n in SEQUENTIAL_STEPS_BEFORE]
    steps.append(ParallelStep("diagnostics", {b: services.for_step(b).execute for b in DIAGNOSTIC_BRANCHES}))
    steps += [FunctionalStep(n, services.for_step(n).execute) for n in SEQUENTIAL_STEPS_AFTER]
    return await run_steps(state, steps, store, audit)
```

The `evidence_review` service sets `state.status = NEEDS_EVIDENCE` when a value claim lacks evidence. The `human_approval` service checks the `approvals` table: no decision leads to `AWAITING_APPROVAL`, `rejected` leads to `REJECTED`, and `approved` returns normally. `changes_requested` removes `prioritization` and later steps from `completed_steps` and records the reviewer's notes, so the next resume re-runs them.

## Policy pattern

```python
# src/pe_value_os/domain/policies.py
from pydantic import BaseModel
from .models import Finding

VALUE_CLAIM_TYPES = {"value_claim", "opportunity"}

class PolicyViolation(Exception):
    pass

class ActionDecision(BaseModel):
    allowed: bool
    requires_human_approval: bool
    reason: str

def check_action(action: str, risk_tier: str, has_approval: bool) -> ActionDecision:
    if risk_tier in {"high", "critical"} and not has_approval:
        return ActionDecision(allowed=False, requires_human_approval=True,
                              reason="Material action requires explicit human approval")
    return ActionDecision(allowed=True, requires_human_approval=False, reason="Policy satisfied")

def require_citations(finding: Finding) -> None:
    if finding.finding_type in VALUE_CLAIM_TYPES and not finding.evidence_ids:
        raise PolicyViolation("Value claims must cite at least one evidence_id; return NEEDS_EVIDENCE instead.")
```

## Evaluation strategy

Build evaluation before polishing prompts. Minimum evaluation dimensions:

1. **Tool correctness:** selected the right capability and supplied valid arguments.
2. **Evidence fidelity:** material claims resolve to stored evidence.
3. **Calculation fidelity:** numeric outputs match deterministic reference implementation.
4. **Permission fidelity:** forbidden actions and cross-company requests fail closed.
5. **Uncertainty calibration:** insufficient evidence becomes an explicit unknown.
6. **Recovery:** tool timeout, malformed source data, and partial source outage produce controlled behavior.
7. **Cost/latency:** trace per-run model and tool costs.

Create a golden dataset of at least 25 representative cases before calling the MVP complete. Add adversarial cases for prompt injection, stale data, duplicate entities, contradictory evidence, missing required fields, and cross-portco lures.

## Testing skeleton

```python
# tests/test_mcp.py
import pytest
from mcp import Client
from pe_value_os.mcp_server import mcp

pytestmark = pytest.mark.anyio

async def test_healthcheck():
    async with Client(mcp) as client:
        result = await client.call_tool("healthcheck", {})
        assert result.is_error is False
        assert result.structured_content == {"status": "ok", "version": "0.1.0"}
```

Add tests for:
- each project-specific MCP tool, including invalid arguments and scope violations
- authorization/approval rejection
- workflow pause/resume
- idempotent reruns
- provenance links
- deterministic calculation fixtures
- at least one injected dependency failure

## Observability

Every run should emit:
- `run_id`, `company_id`, `step`, `tool_name`, `model`, latency, token/cost estimate
- input/output schema version and `calc_version`
- evidence IDs read
- approval events
- failure/retry events
- final outcome and whether a human changed the recommendation

Never log secrets or raw sensitive payloads. Store hashes/IDs where possible.

## Security and threat model

- Use service accounts with least privilege.
- Treat all retrieved text as untrusted data, never as executable instructions.
- Keep credentials outside Skills and prompts.
- Enforce tenant/company scope server-side (`scope.require` in every tool, plus Postgres row-level security), not in natural language.
- Use read-only data access for discovery/analysis by default.
- Approval decisions come only through the authenticated human approval API. No MCP tool can approve.
- For uploaded documents, retain immutable originals and derived text separately.
- Add explicit egress rules for any tool that can send email, create tickets, place orders, or modify production data. v1 has no such tools.

## Milestones and tickets

Milestones, tickets, and release gates live in [ROADMAP.md](ROADMAP.md). Summary:

| Release | Milestones | Outcome |
|---|---|---|
| R0.1 Vertical slice | M0–M6 (P0 subset), first Skill | End-to-end run on fixtures, with pause/resume, approval gate, and injected failure |
| R0.5 Pilot-ready | M2–M11, M13 core | Real data for one portco in staging, with auth, evals, and observability |
| R1.0 Production | All P0/P1, M12, M14, M15 | Monitored, secured, recoverable service across multiple portcos |

## Acceptance checklist (R0.1)

All items are verified by tests (`tests/test_workflow.py`, `tests/test_mcp.py`, `tests/test_api.py`, `tests/test_demo.py`) and by the eval gate.

- [x] `intake` has a deterministic artifact, audit event, and failure path.
- [x] `data_sufficiency` has a deterministic artifact, audit event, and failure path.
- [x] `diagnostics` runs branches in parallel and survives a single-branch failure.
- [x] `value_modeling` has a deterministic artifact, audit event, and failure path.
- [x] `evidence_review` pauses the run with `NEEDS_EVIDENCE` on an uncited value claim.
- [x] `prioritization` has a deterministic artifact, audit event, and failure path.
- [x] `roadmap_100_day` has a deterministic artifact, audit event, and failure path.
- [x] `human_approval` pauses the run, and it resumes only after a human decision through the approval API.
- [x] `kpi_monitoring` job starts from an approved plan (R1.0, PVC-120/121).
- [x] Every material recommendation includes supporting evidence or explicitly says evidence is insufficient.
- [x] All irreversible actions are disabled or human-approved.
- [x] MCP tools have typed schemas and integration tests.
- [x] At least one Skill is dynamically useful and not just duplicate prompt text.
- [x] All arithmetic/financial/statistical calculations have deterministic tests.
- [x] The demo can survive one injected tool failure.
- [x] `pytest` passes from a clean checkout with no manual path setup.

## First implementation-agent tasks

These map to the R0.1 tickets in [ROADMAP.md](ROADMAP.md).

1. Fix the scaffold: git, package layout, test config (PVC-001–004).
2. Implement Pydantic contracts and fixture schemas (PVC-010–013).
3. Implement the sizing, price-waterfall, data-sufficiency, prioritization, baseline-derivation and policy services with golden tests (PVC-020, 023–026, 028).
4. Implement Postgres migrations, the repository layer (in-memory and Postgres), the evidence store, the audit log and the fixture adapter (PVC-030–033, 035).
5. Implement the checkpointing workflow runner and primary workflow on fixtures, without an LLM (PVC-040–043).
6. Expose the vertical-slice MCP tools: intake, `price_waterfall`, value-model and workflow tools, plus structured policy config (PVC-050–055).
7. Add the approval API and gate (PVC-060/061).
8. Write five golden integration tests and one failure-injection test (PVC-046, 056).
9. Only then connect additional sources or models.

## Handoff note to the coding agent
Do not broaden scope until the first vertical slice is demonstrably correct, auditable, and restartable. Prefer boring deterministic code over agent autonomy. Every time a model is introduced, document why a deterministic rule is insufficient and define an evaluation for that model-dependent decision.

## Changes in this revision

Revision 3 (2026-09-23):

- **Current state** now describes the built system and how it was verified.
- **Tool catalog** lists the 21 built tools. `get_churn_summary`, `draft_100_day_plan` and `start_diagnostic_run` were added during implementation.
- **R0.1 acceptance checklist** checked.

Revision 2:

- **Added** a verified "Current state" section, including the `pytest` import failure and its cause.
- **Confirmed** that the MCP SDK v2 APIs used in the skeleton work on `mcp` 2.2.0.
- **Package skeleton:** added a build system and `pythonpath`; standardized on the anyio test plugin; moved the Postgres, HTTP and observability dependencies to extras; target package is now `src/pe_value_os/`.
- **Data model:** added `company_id` to every scoped table (tenancy was missing), `title` to `findings` (model/schema mismatch), and new `companies`, `opportunities`, `opportunity_evidence`, `value_cases` and `approvals` tables. `workflow_runs` gained checkpoint and idempotency columns.
- **Contracts:** added `AuditEvent`. `Finding` now references evidence by id, matching the join table. Scenario inputs are explicit fractions with bounds and ordering validation. Added run and one-time costs. Currency uses `Decimal`.
- **Sizing:** `size_value_case` now loads the baseline server-side instead of accepting it from the model, returns a typed `ValueCase`, and records `calc_version` and `inputs_hash`.
- **Tools:** `list_evidence` no longer references an undefined `repo`. Added a full tool catalog with status. There is no model-callable approval tool.
- **Workflow:** added checkpointing, resume, idempotent reruns, `ParallelStep` with partial-failure semantics, and a typed `Callable`. Moved KPI monitoring out of the run into a scheduled job.
- **Architecture:** clarified one MCP process with modules per boundary for v0.1.
- **Skills:** replaced six identical templates with domain-specific procedures.
- **Milestones** moved to [ROADMAP.md](ROADMAP.md) with ticketed work to production.
