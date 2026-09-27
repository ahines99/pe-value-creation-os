# Load test results (PVC-143)

Two tests, both against a local PostgreSQL 18 on developer hardware. Repeat them on staging hardware before GA.

- **Runs** (`scripts/load_test.py`): 4 concurrent workers drain automated runs with no duplicate execution. Historical September 23 rows measured whole-run latency only and do not prove the step SLO. The September 27 rerun measured step durations from persisted audit events and enforced p95 <= 5 s: 1.143 s across 40 runs, with no failed runs or duplicate claims. The script now fails on missing step samples or an exceeded threshold. Test logins are unique per invocation and never reset shared database-role passwords.
- **MCP sessions** (`scripts/mcp_load_test.py`): 20 concurrent Streamable HTTP sessions, each running a mix of read tools and interactive-run calls. Target: availability SLO (at most 0.5% failed calls) and tool p95 under 2 s.

The first MCP runs failed the availability target: 2.8% of calls errored. A second failing run was made only to capture the error messages, and its numbers were not kept. Concurrent first loads of a company raced on the filesystem evidence store's temporary file. The store now publishes originals with an atomic create-if-absent link (`tests/test_audit_fixes.py::test_concurrent_evidence_writes_are_safe`), and the re-run had no errors. The first failing run and the passing re-run are in the table below.

| When | Setup | Load | Throughput | Run latency | Checks |
|---|---|---|---|---|---|
| 2026-09-23 15:56 UTC | local PostgreSQL 18, 4 workers | 40 runs | 2.8 runs/s | p50 1.32 s, p95 2.17 s | no double claims; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
| 2026-09-23 19:14 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 49.6 calls/s | tool p50 169 ms, p95 912 ms | **failed**: errors 17 (2.83%), evidence-store race; fixed before the next run |
| 2026-09-23 19:16 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 44.3 calls/s | tool p50 237 ms, p95 752 ms | errors 0 (0.00%); p95 target 2 s |
| 2026-09-23 19:26 UTC | local PostgreSQL 18, 4 workers | 40 runs | 2.1 runs/s | p50 1.78 s, p95 2.94 s | no double claims; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
| 2026-09-27 21:03 UTC | local PostgreSQL 18, 4 workers | 40 runs | 1.7 runs/s | p50 2.36 s, p95 3.29 s | no double claims; step p95 1.143 s <= 5 s; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
| 2026-09-27 21:10 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 52.8 calls/s | tool p50 179 ms, p95 446 ms | errors 0 (0.00%); p95 target 2 s |
