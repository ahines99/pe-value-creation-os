# PE Portfolio Value Creation Operating System

Turns portfolio-company operating data into evidence-backed value-creation initiatives, deterministically sized EBITDA cases, a human-approved 100-day plan, and ongoing KPI monitoring.

**Status: pre-alpha scaffold.** Only a health-check MCP tool, a policies resource, partial domain models, and six Agent Skills exist. Everything else is specified in [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md) and scheduled in [ROADMAP.md](ROADMAP.md).

## How it works (target design)

| Layer | Owns |
|---|---|
| Deterministic services | All arithmetic, metric definitions, joins, permissions |
| MCP server | Typed tools, resources and prompts the model can call |
| Agent Skills (`skills/`) | Domain procedure: diagnostic trees, checklists, output contracts |
| Workflow + PostgreSQL | Run state, checkpoints, approvals, audit trail |

The model supplies judgment: which levers to investigate, scenario assumptions, narrative. The system supplies facts and arithmetic. Every value claim cites stored evidence. Humans approve plans through a separate authenticated API; no model-callable tool can approve.

## Quick start (current scaffold)

Requires Python 3.12+.

```bash
pip install "mcp[cli]>=2.2,<3" "pydantic>=2.9" pytest
python -m pytest        # 1 test passes
```

Run pytest as `python -m pytest`. Plain `pytest` currently fails with `ModuleNotFoundError: No module named 'src.mcp_server'`; ticket PVC-002 fixes this.

## Repository map

| Path | Contents |
|---|---|
| [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md) | Architecture, contracts, data model, tool catalog, current state |
| [ROADMAP.md](ROADMAP.md) | Ticketed milestones and release gates to production |
| [src/mcp_server.py](src/mcp_server.py) | MCP server (health check and policies resource) |
| [src/domain/models.py](src/domain/models.py) | Core Pydantic contracts (partial) |
| [skills/](skills/) | Six Agent Skills. They reference MCP tools that are planned but not yet built. |
| [tests/](tests/) | In-process MCP client tests |

## Why this is not just a chatbot

- The LLM never does financial arithmetic. Sizing and metrics are versioned, tested code.
- The LLM is not the system of record. Runs, evidence, findings and approvals live in PostgreSQL.
- Every value claim must resolve to stored evidence, or the run pauses with `NEEDS_EVIDENCE`.
- Company scope is enforced server-side, so one portco's data can't leak into another's analysis.
- Material actions stop at a human approval gate with an audit trail.
