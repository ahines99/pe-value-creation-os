# Load test results (PVC-143)

Two tests, both against a local PostgreSQL 18 on developer hardware. Repeat them on staging hardware before GA.

- **Runs** (`scripts/load_test.py`): 4 concurrent workers drain a queue of automated runs. Target: step p95 inside the 5 s SLO, and no run executed twice. The 19:26 re-run, after the audit fixes, is about 25% slower than the first run (2.1 vs 2.8 runs/s). The likely cause is the per-attempt state copy that protects against abandoned step attempts. It remains well inside the SLO.
- **MCP sessions** (`scripts/mcp_load_test.py`): 20 concurrent Streamable HTTP sessions, each running a mix of read tools and interactive-run calls. Target: availability SLO (at most 0.5% failed calls) and tool p95 under 2 s.

The first MCP runs failed the availability target: 2.8% of calls errored. A second failing run was made only to capture the error messages, and its numbers were not kept. Concurrent first loads of a company raced on the filesystem evidence store's temporary file. The store now publishes originals with an atomic create-if-absent link (`tests/test_audit_fixes.py::test_concurrent_evidence_writes_are_safe`), and the re-run had no errors. The first failing run and the passing re-run are in the table below.

| When | Setup | Load | Throughput | Run latency | Checks |
|---|---|---|---|---|---|
| 2026-09-23 15:56 UTC | local PostgreSQL 18, 4 workers | 40 runs | 2.8 runs/s | p50 1.32 s, p95 2.17 s | no double claims; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
| 2026-09-23 19:14 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 49.6 calls/s | tool p50 169 ms, p95 912 ms | **failed**: errors 17 (2.83%), evidence-store race; fixed before the next run |
| 2026-09-23 19:16 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 44.3 calls/s | tool p50 237 ms, p95 752 ms | errors 0 (0.00%); p95 target 2 s |
| 2026-09-23 19:26 UTC | local PostgreSQL 18, 4 workers | 40 runs | 2.1 runs/s | p50 1.78 s, p95 2.94 s | no double claims; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
