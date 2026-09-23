# Restore drill log (PVC-142)

| When | Environment | Data | Dump | Restore | Checks | Result |
|---|---|---|---|---|---|---|
| 2026-09-23 15:56 UTC | local PostgreSQL 18 | 201 rows, 93 KB dump | 0.16 s | 0.19 s | counts match; RLS verified | pass |
