# Pilot retrospective and go/no-go (PVC-154)

For the operating partner, who makes the decision, and the engineering and security leads, who sign next to it. Copy this file to `docs/pilot/go-no-go-<company>-<yyyy-mm-dd>.md`, fill it in from the pilot's evidence, and sign it. This template is blank. No pilot has run yet.

## 1. Summary

| | |
|---|---|
| Pilot company | |
| Pilot dates | |
| Runs completed and reviewed | |
| Approvers | |
| Recommendation | GO / GO WITH CONDITIONS / NO-GO |

One paragraph: what the pilot showed, and the recommendation.

## 2. Results against the pilot measures

Take each value from the source named in [pilot-plan.md](pilot-plan.md), "What we measure". Attach the audit export and the dashboard screenshots.

| Measure | Target | Result | Met? |
|---|---|---|---|
| Complete runs reviewed by humans | at least 2 | | |
| Override rate, run 1 then run 2 | recorded | | n/a |
| Disputes with root cause and ticket | 100% | | |
| Unresolved calculation defects | 0 | | |
| Value claims without evidence | 0 | | |
| Successful cross-company access | 0 | | |
| Model cost per run | at most $2.00 | | |
| SLOs (run p95, availability) | within SLO | | |
| Mean reviewer usefulness score | recorded | | n/a |

## 3. Disputes by root cause

| Root cause | Count | Fixed | Open tickets |
|---|---|---|---|
| Data | | | |
| Calculation | | | |
| Skill | | | |
| Model | | | |

## 4. Retrospective

- **What worked:**
- **What didn't:**
- **What surprised the deal team:**
- **Opportunities approvers found valuable but would not have found without the system:**
- **Opportunities approvers rejected, and why:**
- **Incidents and pages during the pilot:** (links to incident notes)

## 5. Production readiness checklist

All must be checked for GO. Any unchecked item becomes a condition for GO WITH CONDITIONS.

- [ ] Production environment applied from Terraform, and the smoke test passes (PVC-131 to 136)
- [ ] External pen test complete; high and critical findings fixed (PVC-097)
- [ ] Production restore drill passed (PVC-142)
- [ ] On-call rotation staffed and paged successfully in a test (PVC-148)
- [ ] Legal and data-processing review covers production and the model provider (PVC-147)
- [ ] Policy values signed off by the fund's operating team (no `-placeholder` in the policy version)
- [ ] Live-model eval (`pvc eval --proposer model`) meets the `[model]` thresholds in `evals/thresholds.toml`
- [ ] Onboarding playbook updated with lessons from this pilot

## 6. Conditions for production

| # | Condition | Owner | Due | Evidence it is met |
|---|---|---|---|---|
| 1 | | | | |

## 7. Decision

| Role | Name | Decision | Signature | Date |
|---|---|---|---|---|
| Operating partner (decision owner) | | | | |
| Engineering lead | | | | |
| Security lead | | | | |

A NO-GO records what would have to change before another pilot. A GO WITH CONDITIONS is not a production release until every condition in section 6 has evidence.
