# Restore drill log (PVC-142)

| When | Environment | Data | Dump | Restore | Checks | Result |
|---|---|---|---|---|---|---|
| 2026-09-23 15:56 UTC | local PostgreSQL 18 | 201 rows, 93 KB dump | 0.16 s | 0.19 s | counts match; RLS verified | pass |
| 2026-09-27 21:02 UTC | local PostgreSQL 18 | 399 rows, 99 KB dump | 0.21 s | 0.26 s | all 17 table counts match; read/write RLS verified on 16 tables | pass |
