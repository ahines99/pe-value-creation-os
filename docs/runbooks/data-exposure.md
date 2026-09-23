# Suspected cross-company data exposure

**Signals:** `PvcScopeDenialsSpike`; a user reports seeing another company's data; a penetration-test finding.

1. Treat as Severity 1. Page the security lead and the engineering on-call.
2. Contain: revoke the principal's tokens at the identity provider. If a code path is suspected, scale the affected service (MCP or API) to zero; the worker can keep running.
3. Preserve evidence: `pvc audit-export --company <each affected company> --out incident-<id>.jsonl`; export load-balancer and application logs for the window.
4. Determine exposure: audit events carry actor, company, tool and run ids. Row-level security scopes database reads to the token's companies, so check whether the principal's `pvc_companies` claim was misconfigured at the identity provider.
5. The fund's data-protection lead decides whether to notify affected portfolio companies under their data agreements.
6. Fix, add a regression case to `evals/adversarial.json`, and hold a post-incident review within 5 working days.
