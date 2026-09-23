# Load test results (PVC-143)

Target: 4 concurrent workers sustain the automated workflow with step p95 inside the 5 s SLO and no run executed twice.

| When | Setup | Load | Throughput | Run latency | Checks |
|---|---|---|---|---|---|
| 2026-09-23 15:56 UTC | local PostgreSQL 18, 4 workers | 40 runs | 2.8 runs/s | p50 1.32 s, p95 2.17 s | no double claims; statuses {'awaiting_approval': 30, 'needs_evidence': 10} |
| 2026-09-23 19:16 UTC | local PostgreSQL 18, MCP over Streamable HTTP (1 process) | 20 concurrent sessions, 600 tool calls | 44.3 calls/s | tool p50 237 ms, p95 752 ms | errors 0 (0.00%); p95 target 2 s |
