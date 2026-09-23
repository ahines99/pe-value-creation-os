# Threat model (PVC-090)

**Status:** drafted 2026-09-23 by the engineering owner. **Review required:** security lead and fund operating partner (sign-off table at the end). Review is a human step and is not yet done.

## System and trust boundaries

```text
 Analyst's MCP client ──(OAuth bearer, TLS)──► MCP server (Streamable HTTP) ─┐
 Approver's browser ──(IdP-injected token)──► Approval API + review UI ──────┤
                                                                            ├─► PostgreSQL (RLS, pvc_app role)
 Worker (runs, KPI refresh, escalation) ────────────────────────────────────┤
                                                                            ├─► Evidence store (S3 + Object Lock)
 Source adapters (warehouse, CSV exports, CRM/billing APIs) ◄──(read-only)──┤
 Claude API (judgment steps only, no tools) ◄──(egress allow-list)──────────┘
```

Boundaries: (1) client ↔ MCP server, (2) browser ↔ approval API, (3) services ↔ database, (4) services ↔ evidence store, (5) adapters ↔ portco systems, (6) workflow ↔ model provider, (7) worker ↔ notification channel.

## Assets
Portco financial and customer data; value cases presented to investment committees; approval decisions; the audit log; credentials (DB roles, model API key, webhook URL, adapter credentials).

## STRIDE analysis

| # | Threat | Where | Mitigation | Verified by |
|---|---|---|---|---|
| S1 | Spoofed caller on MCP endpoint | Boundary 1 | OAuth 2.1 JWT verification (issuer, audience, expiry, signature); unauthenticated requests get 401 | `tests/test_auth.py` (HTTP round trip), PVC-091 |
| S2 | Model or service principal approves a plan | Boundary 2 | Approval requires `pvc_principal_type=human` and the approver role; no MCP approval tool | `tests/test_api.py::test_only_human_approvers_can_decide`, adversarial A09, ADR 0004 |
| S3 | Forged approval via cross-site request | Boundary 2 | Double-submit CSRF cookie (SameSite=Strict) on the HTML form; JSON endpoint requires bearer | `tests/test_api.py::test_review_page_and_csrf_form` |
| T1 | Tampering with evidence originals | Boundary 4 | Write-once originals (hash check), S3 Object Lock + versioning in production | `tests/test_repository_contract.py::test_evidence_dedupe_and_immutability` |
| T2 | Tampering with the audit trail | Boundary 3 | `pvc_app` has INSERT/SELECT only on `audit_events` | `test_audit_is_append_only_for_app_role` (PostgreSQL) |
| T3 | Model output alters numbers | Boundary 6 | Server-derived baselines, deterministic sizing, no-new-numbers guardrail, strict tool arguments | `tests/test_llm.py`, `test_propose_rejects_caller_supplied_baseline`, adversarial A02 |
| T4 | Prompt injection in documents or CRM notes | Boundaries 5, 6 | Deterministic screening into `suspicious_content`; `<untrusted_document>` delimiting; no tools during model steps; guardrails reject steered outputs; free text never returned by tools | adversarial A01, `test_injected_document_cannot_steer_outputs` |
| R1 | Actor denies a decision or data change | All | Append-only audit events with actor, policy version, approval id; approvals store decided_by and diff | `test_approve_with_edits_records_diff_and_resumes` |
| I1 | Cross-portco data leakage | Boundaries 1-3 | `security.require` on every tool and repository call; PostgreSQL row-level security keyed on token-derived company scope; ids of other companies' rows return NotFound | `test_cross_company_isolation`, `test_rls_filters_unfiltered_queries`, adversarial A07, eval permission dimension |
| I2 | Sensitive values in logs or traces | Observability | Allow-listed log fields; everything else hashed; span attributes redacted the same way | `tests/test_observability.py` |
| I3 | Data exfiltration through outbound calls | Boundaries 6, 7 | Application egress allow-list for every HTTP client; Network Firewall domain allow-list in production | `test_egress_allow_list`, infra `network.tf` |
| I4 | Model provider retains portco data | Boundary 6 | Data-handling review before pilot data reaches a model; only aggregated tool outputs and documents sent; PVC_PROPOSER=rules until approved | `docs/model_data_handling.md` (PVC-147) |
| I5 | Benchmark data reveals a single company | Benchmark tool | Distributions only; peer sets with n < 5 refused | `test_benchmarks_return_distribution_only`, invalid-args test |
| D1 | Request floods or oversized payloads | Boundaries 1, 2 | WAF rate limiting and request-size limits at the load balancer (PVC-135) | infra `ingress.tf`; load test PVC-143 |
| D2 | Model outage stalls runs | Boundary 6 | Pause with `model_unavailable`, resume later, or policy fallback to rules | `test_model_outage_pauses_then_resumes`, adversarial A08 |
| D3 | Stuck or crashed workflow | Worker | Checkpoint per step, stale-lock takeover, idempotent re-execution | `test_crash_then_resume_skips_finished_steps`, `test_claim_and_resume` |
| E1 | SQL injection | Repository | Parameterised queries only; identifiers are constants | code review; ruff `S608` reviewed |
| E2 | Path traversal in evidence store | Evidence store | Company and evidence ids validated as single path components | `evidence_store._safe` |
| E3 | Privilege via migration role at runtime | Database | Separate `pvc_migrator` (owner), `pvc_app` (runtime, RLS enforced with FORCE), `pvc_readonly` | `db/roles.sql`, deployment docs |
| E4 | Secrets committed to the repo | Supply chain | gitleaks in CI and pre-commit; secrets only from environment/Secrets Manager | `test_no_secrets_in_skills_prompts_policy_or_source`, CI security job |
| E5 | Vulnerable dependencies or base image | Supply chain | pip-audit and Trivy in CI; uv.lock pinned | CI security and container-scan jobs (PVC-096) |

## Residual risks and follow-ups

| Risk | Owner | Ticket |
|---|---|---|
| Identity-provider configuration (claims mapping for `pvc_companies`, roles, principal type) is not yet set up for a real tenant | Security lead | PVC-091 deployment step |
| External penetration test not yet performed | Security lead | PVC-097 (`docs/security/pentest_scope.md`) |
| Real adapter credentials and network paths to portco systems are untested | Engineering | PVC-111..115 during pilot onboarding |
| Model data-processing terms not yet approved | Legal / operating partner | PVC-147 |

## Review sign-off

| Reviewer | Role | Date | Decision |
|---|---|---|---|
| _pending_ | Security lead | | |
| _pending_ | Operating partner | | |
