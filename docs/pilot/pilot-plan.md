# Pilot plan: one portfolio company (PVC-153)

For the operating partner, the pilot company's deal team, and the engineering lead. This plan says how the pilot runs, who decides what, and what evidence the go/no-go decision (PVC-154) needs. The pilot has not started. The fields marked **TBD** are open decisions for the project owner (ROADMAP.md, "Open decisions").

## Entry criteria

Do not start until all of these are true:

- [ ] R0.5 gate passed: staging deployed (PVC-131 to 136), live alerting for 2 weeks (PVC-103), threat-model review signed (PVC-090).
- [ ] Legal and data-processing review complete (PVC-147), including the model data-handling terms in [model_data_handling.md](../model_data_handling.md).
- [ ] Domain-expert sign-off on the six skills and the policy values (PVC-071, PVC-055). The policy file must not carry `-placeholder` in its version.
- [ ] Data-access agreement signed with the pilot company. Read-only credentials issued.
- [ ] Onboarding playbook steps 1 to 5 complete ([onboarding-playbook.md](onboarding-playbook.md)), and `pvc onboard-check` exits 0.

## Scope

| Item | Pilot setting |
|---|---|
| Company | **TBD**, one company |
| Environment | Staging, with production-grade controls. Read-only source credentials. |
| Sources | **TBD**, warehouse-first (ADR 0008). Vendor APIs only where the warehouse lacks a dataset. |
| Proposer | `model` (Claude) with `model.on_unavailable = "pause"`. Engineering also does a separate `PVC_PROPOSER=rules` run on the same data. Approvers don't see it; it is the baseline for comparing model proposals. |
| Approvers | Deal team lead and operating partner (`pvc_roles: ["approver"]`, scoped to the pilot company only) |
| Duration | 6 weeks: 2 diagnostic runs, one KPI refresh cycle (30-day cadence) |
| Out of scope | Writing back to any source system, other portfolio companies, benchmark data under an unconfirmed licence (PVC-116) |

## Schedule

| Week | Activity | Owner |
|---|---|---|
| 0 | Entry criteria checked; kickoff with the deal team; walk through the demo | Engineering lead |
| 1 | Run 1 on data as of the latest month-end. Engineering reviews the run before approvers see it. | Engineering |
| 2 | Approvers review run 1 in the review UI: approve, reject or request changes, with rationale. Disputed items go into the dispute log. | Approvers |
| 3 | Root-cause each dispute and fix what can be fixed (policy, skill, data mapping). Recompute if the calculator changed. | Engineering + domain expert |
| 4 | Run 2 on refreshed data, with fixes applied | Engineering |
| 5 | Approvers review run 2. First KPI refresh for the approved plan. | Approvers |
| 6 | Retrospective and go/no-go ([go-no-go.md](go-no-go.md)) | Operating partner |

## What we measure

| Measure | Source | Target to proceed |
|---|---|---|
| Complete diagnostic runs reviewed by humans | Audit log (`pvc audit-export`) | At least 2 |
| Approver override rate (changes requested or rejected ÷ decisions) | `/metrics/approvals` | Recorded. There is no target for the first company, but the trend from run 1 to run 2 is reviewed. |
| Disputed opportunities with a root cause and ticket | Dispute log below | 100% |
| Calculation disputes traced to a code defect | Dispute log | 0 unresolved |
| Value claims without evidence | Evidence review step; eval `evidence_fidelity` | 0 |
| Cross-company access attempts that succeeded | Access logs; RLS | 0 |
| Model cost per run | `pvc.model.cost_usd` metric | At most $2.00 (eval threshold) |
| Run p95 duration, availability | [slo.md](../slo.md) dashboards | Within SLO |
| Reviewer usefulness score (1 to 5, per opportunity) | Reviewer form (kept outside the system) | Recorded |

## Dispute log

Every opportunity or number that a reviewer disputes gets one row. Root cause is exactly one of: **data** (source wrong or mis-mapped), **calculation** (calculator or metric definition), **skill** (procedure or thresholds), or **model** (proposal or narrative).

| # | Run | Opportunity / figure | Reviewer's objection | Root cause | Ticket | Resolution |
|---|---|---|---|---|---|---|
| 1 | | | | | | |

## Safeguards during the pilot

- Only the pilot company's id appears in any token or worker configuration (`PVC_WORKER_COMPANIES`).
- An approval does not trigger any action in the company's systems. It only activates KPI monitoring.
- Stop the pilot immediately on a suspected data exposure ([runbooks/data-exposure.md](../runbooks/data-exposure.md)), or on any calculation defect that changes a reviewed number by more than 10%. Then follow [runbooks/bad-calculation-release.md](../runbooks/bad-calculation-release.md).
- At the end, retain or delete the data according to the data-access agreement (`pvc offboard`, [data_retention.md](../data_retention.md)).
