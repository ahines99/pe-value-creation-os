# ADR 0001: One MCP server process with modules per capability boundary

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-007

## Context
The handoff names eight capability boundaries (financials, CRM, product analytics, support, pricing, benchmark, value model, workflow). Separate servers would multiply deployment, auth configuration, and test setup before any boundary has distinct authorization or lifecycle needs.

## Decision
Run one `MCPServer`. Each boundary is a Python module under `pe_value_os.tools` that registers its tools on the shared server. Every tool enforces company scope itself.

## Consequences
- One deployment, one auth configuration, one in-process test client.
- A boundary can be split into its own server later by mounting its module on a new `MCPServer`; tool code does not change.
- Split triggers: a boundary needs different credentials or network placement (for example, benchmark data under a licence that forbids co-location), or a different scaling profile.
