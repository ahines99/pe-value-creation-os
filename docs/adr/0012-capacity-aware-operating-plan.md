# ADR 0012: capacity-aware 100-day operating proposal

Status: implemented for constructed analytical cases. This is not a management
approval or actual execution record. Durable case/review persistence is now
implemented separately in [ADR 0013](0013-immutable-case-reviews.md).

## Decision

Use one typed `OperatingPlan` bound to the exact underwriting case hash, identity
and start date. Stable task, resource, initiative and gate IDs support inspection.
Every task has one proposed accountable resource, explicit demand, a deliverable,
required acceptance evidence and a proposed reviewer. A benefit gate must depend
on all of its initiative's work. Cycles, orphan references, duplicate identities,
unknown resources and uncovered initiatives are rejected before scheduling.
An initiative retains one workstream and accountable operator across its packages;
unrelated initiatives cannot share a workstream ID to evade concurrency limits.

The scheduler chooses the first dependency-ready task in the authored priority
order and places it in its earliest feasible slot. This is a deterministic serial
schedule, not an optimization or a recommendation that the priority is correct.
It reserves each resource's net change hours and counts distinct workstreams in
every occupied week. Enablers consume both resources and a workstream slot.
Separate tasks in the same workstream still consume their full resource demand.

Planning weeks are consecutive seven-day intervals anchored on the case start,
not calendar Mondays. Work packages are non-preemptive and use constant demand
over whole weeks. Dependencies finish before their successors start. Day 100 is
inclusive; its final two-day partial interval cannot fit a full-week task. No
implicit partial-week compression or interpolation of capacity is permitted.

Capacity budgets are explicit for all 15 intervals, net of ordinary duties. A
missing budget is `null`, not zero or an unlimited resource. An unknown interval
cannot accept work; later explicit intervals may still be feasible. No feasible
slot leaves a task blocked, with dependent work also blocked. Rejected candidate
slots retain constraint type, week, required/remaining hours and competing tasks.

## Connection to economics

The scheduler owns dates, never a second financial calculator. An immutable copy
of the underwriting input takes the later of the original economic start and
the day after the scheduled final acceptance gate. Original inputs remain intact.
Projected acceptance is only an assumption; no acceptance receipt is manufactured.

Monthly underwriting version 2 adds a per-scenario benefit-suppression mask to
the calculation fingerprint. A blocked initiative earns no benefit anywhere in
the 24-month forecast until a revised feasible plan exists. All original costs,
fees, capex and recognition/payment dates remain. The mask does not represent
initiative rejection and does not exercise the existing avoidable-cost exclusion
rule. A real cost cancellation or new timing requires a separately authored case.
Resource hours represent availability, not extra compensation automatically
added to costs. Reviewers must check that the separate cost assumptions cover
the proposed effort, purchases and commitments.

If a collections gate falls on or after its original counterfactual collection
date, its acceleration benefit is unavailable. The counterfactual never moves to
preserve an artificial opportunity. Scenario-specific economic dates and costs
remain scenario-specific. Neither scheduling nor arithmetic supplies missing
contract, quality, staffing, accounting or management evidence.

The report compares original and scheduled forecasts from the same engine,
including day-100/monthly/yearly earnings, cash, funding and valuation sensitivity.
Input, plan, calculation and report hashes expose drift. The original standalone
underwriting report is regenerated with version 2; its economic values are
unchanged absent a benefit block or explicitly revised start date.

## Current example and verification

The generator authors four resource budgets and seven packages. A shared finance
and data constraint pushes the service gate to December 30, 2026. Base service
benefit starts December 31 instead of December 15, reducing first-year EBITDA and
the cash proxy by USD 9,290.32 while preserving costs. This is a constructed
timing demonstration, not a Progress staffing plan or forecast.

Worked tests check independent start/finish dates and financial amounts, order
sensitivity, missing/zero capacity, prerequisite failure, maximum concurrency,
missed collections windows, last-day boundaries, exact-case binding, cost
retention, original-input preservation and private-source rejection. CLI replay,
installed-package smoke and desktop/tablet/phone keyboard/disclosure checks cover
the published artifact. Tests prove conditional behavior, not management buy-in.

## Remaining work

Immutable database revisions and exact-version research receipts are available;
actual acceptance events remain required before using this as an operating
execution record. Add the selected/rejected
thesis rationale, full decision memo and original/current/actual attribution ledger.
The current public report exposes these limitations and does not mark any pilot
or real initiative approved, executed or realized. Daily calendars, leave handling,
preemptive work and mathematical optimization are outside this initial method.
