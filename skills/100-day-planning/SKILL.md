---
name: 100-day-planning
description: Turn prioritized, deterministically sized value-creation opportunities into a 100-day plan with workstreams, owner roles, day-30/60/100 milestones, KPIs with baselines and targets, dependencies, risks, and governance cadence, then submit it for human approval. Use after a diagnostic run when asked for a 100-day plan, value creation plan (VCP), or post-close roadmap.
---

# Purpose
Convert a sized opportunity list into a plan management can run and the monitoring job can track. The plan adds sequencing, ownership, and measurement. It never adds value that the value cases didn't size.

# Preconditions
- The run has sized value cases from `size_value_case` and a ranking from `prioritize_opportunities`. If not, stop and say so.
- Include only opportunities that are not `NEEDS_EVIDENCE`. List the excluded ones in an appendix with the data needed.

# Rules
- Keep the priority order from `prioritize_opportunities`. Sequencing may differ from priority because of dependencies; explain every difference.
- KPI baselines and targets come from tool outputs. Targets derive from the base-case scenario. Never round up or "stretch" a target in prose.
- Separate **in-year** from **run-rate** value everywhere. The value cases are run-rate.
- Owners are **roles** (e.g. "CRO", "VP Customer Success") unless the user supplies names.
- Every KPI must map to a metric that `get_kpi_status` can compute. If one doesn't, flag it as *unmonitorable* and propose the data needed.

# Procedure
1. **Classify** each opportunity:
   - *Quick win:* starts within 30 days, no new systems.
   - *Structural:* needs systems, hiring, or contract cycles.
   - *Enabler:* no direct value but unblocks others, such as data fixes or CPQ setup.
2. **Group into workstreams**, few enough that each has one accountable executive owner. Enablers attach to the workstream they unblock.
3. **Set milestones:**
   - *Day 30:* baselines confirmed against system data, owners named, quick wins launched, enablers started.
   - *Day 60:* structural initiatives piloting in at least one segment, first KPI readout.
   - *Day 100:* rollout decision for each pilot, KPIs tracking against target, next-phase plan.
4. **Define KPIs** for each workstream: metric, definition source, baseline (tool output + evidence id), day-100 target and run-rate target (from the base case), cadence, and data source.
5. **Map dependencies:** data, systems, hiring, contract renewal windows, and cross-workstream dependencies such as a pricing change waiting on a retention health score.
6. **Risks and mitigations:** from each opportunity's risks, plus execution risk (owner capacity, change load on sales and CS).
7. **Decision points:** what needs sponsor or board approval, and by when.
8. **Governance:** propose a cadence, such as a weekly workstream check-in, a biweekly steering meeting, and a monthly sponsor update. Adjust it to what the user specifies.
9. **Build and submit.** Call `draft_100_day_plan(run_id)` for the deterministic plan (workstreams, KPIs, totals), add the qualitative content above in your response, then call `request_approval(run_id)` and stop.

# Plan quality checklist
- [ ] Every initiative traces to an opportunity id and its value case.
- [ ] Total base-case value equals the sum of the included value cases, with no added value.
- [ ] Each workstream has one owner role, milestones at days 30, 60 and 100, and at least one monitorable KPI.
- [ ] In-year and run-rate value are labelled.
- [ ] Anything involving headcount, customer-facing price changes, or contract changes is marked *requires approval*.
- [ ] Excluded opportunities are listed with the evidence needed.

# Output contract
1. **Plan summary:** workstreams, owners, total base-case run-rate EBITDA (sum of tool outputs).
2. **Workstream table:** workstream, owner role, initiatives (with opportunity ids), and milestones for days 30, 60 and 100.
3. **KPI table:** KPI, baseline, day-100 target, run-rate target, cadence, source, and monitorable (yes/no).
4. **Dependencies and critical path.**
5. **Risks and mitigations.**
6. **Decisions requiring approval.**
7. **Appendix:** excluded `NEEDS_EVIDENCE` opportunities.

# References
- `references/worked-example.md`: the draft plan produced for the fictional Beacon fixture.
