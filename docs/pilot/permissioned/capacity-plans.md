# Private underwriting to a capacity-aware 100-day proposal

This increment connects a saved [private underwriting revision](underwriting.md)
to an explicit resource/dependency plan and recalculates its benefit timing. It
has a separate CI/publication gate in the
[completion checklist](../../portfolio/remaining-work.md). Tests use fictional
companies, operators, capacity evidence and grants; no company commitment or
performed pilot is represented.

## Author a proposal with evidence

A named human processing operator supplies a plan bound to the exact current
underwriting revision ID/hash, case key and forecast start. The repository
rechecks that revision and its accepted financial source under the company lock.
An earlier successful request or historical receipt is insufficient to establish
current source authority.

The plan contains:

- Resources with 15 weekly net-hour budgets, proposed operators, basis, capacity
  evidence references/hashes and attestations. Unknown capacity is `null`;
  zero is known unavailability. Neither is interpreted as unlimited capacity.
- Work packages with accountable resources, explicit hours, earliest start,
  full-week duration, prerequisites, deliverables and acceptance requirements.
- An authored priority order and maximum simultaneous workstreams.
- Exactly one benefit gate per underwriting initiative, depending on every work
  package for that initiative.

Capacity references are recorded human assertions, not independently verified
commitments. Assignments remain `proposed`; simulated or actual-assignment labels
are rejected in this contract. A dated acceptance gate is a planning assumption,
not evidence that someone accepted the deliverable. Separate operating review
and subsequent delivery evidence remain necessary.

Proposals support up to 100 resources and 250 tasks. Hour inputs have at most six
decimal places and retain the 0–168 weekly-hour bounds. Task workstreams and owners
cannot be changed merely to bypass concurrency. Cycles, orphan prerequisites,
duplicate priorities, unknown resources and incomplete gates are rejected.

## Calculate feasibility and its financial effect

The deterministic scheduler uses authored priority among dependency-ready tasks
and the earliest feasible full planning weeks. Weeks start on the forecast date,
not necessarily Monday. The last two days of the 100-day horizon cannot fit a
full-week package. This is conditional feasibility, not mathematical optimization.

Only selected initiatives and their required enablers consume capacity. A selected
initiative cannot depend implicitly on an excluded initiative. Resource conflicts
and workstream limits are recorded with the rejected candidate dates.

A scheduled initiative earns benefits no earlier than both its original economic
date and the day after its planned acceptance gate. A blocked gate suppresses
benefits throughout the forecast until the plan is revised. Collection acceleration
is suppressed when the gate misses the original counterfactual collection date;
the calculator never moves that counterfactual to rescue the opportunity.

The result saves original and scheduled private financial reports plus the
proposed schedule, capacity usage, timing changes and scheduled inputs. Dated
costs of selected work stay intact when benefits are delayed or blocked.
Explicitly avoidable costs of excluded work are excluded; retained commitments
remain once. The scheduler never moves expense or payment dates automatically.

The fictional worked case first schedules a one-week foundation and then a
one-week pricing gate. Benefits begin October 15 rather than October 1. The
original 39.20 monthly contribution becomes 21.50 for the partial first month;
the 50 implementation expense remains. First-year EBITDA becomes 402.70 and cash
becomes 363.50, compared with original amounts of 420.40 and 381.20. Missing all
capacity suppresses benefits but preserves the 50 cost. These are hand-checked
test results, not actual savings or approved forecasts.

## API and immutable revisions

All routes start with `/companies/{company_id}/private-capacity`.

| Method / suffix | Behavior |
|---|---|
| `POST /cases/{case_key}` | `CapacityPlanRequest`: idempotency key, previous capacity-revision hash, underwriting revision ID, typed plan and rationale |
| `GET /cases/{case_key}` | Scoped-human historical records with no current-use assertion |
| `GET /revisions/{revision_id}/usable` | Requires the latest capacity and underwriting revisions, current source authority and complete calculation reproduction |

The common planning payload calls its private case key `case_id`; its
`underwriting_sha256` is the stored private underwriting revision's content hash.
The plan's `plan_id` and `revision_id` are authored labels. The enclosing stored
capacity revision has a separate server-generated UUID, timestamp, author,
sequence and content hash. The server supplies all results and permission state.

Writes require a scoped named human operator, `pvc.read`/`pvc.write` and explicit
bearer authentication. The server chooses the processing environment and checks
authentication before reading the bounded 1 MiB body. Validation errors do not
echo private payloads; responses are non-cacheable. There is no MCP or public
export for this contract.

Migration `0012` adds forced company RLS, exact underwriting/predecessor foreign
keys, insert/select-only runtime access and unique sequence/idempotency rules.
The company lock covers current-authority checks, calculation, append and audit.
Audit failure rolls back the revision. Populated downgrades are blocked, including
when the migration owner has no active company scope. Whole-company offboarding
removes capacity history with its inputs.

An identical request by the same author returns the original historical receipt.
Changed requests or stale heads conflict. Revisions preserve original schedules
and forecasts. Source corrections, withdrawn acceptance, changed review/grant
heads, revocation, expiry, superseded underwriting or a wrong processing environment
prevent current use. Scoped humans can still read historical records; this does
not assert that processing remains permitted or delete retained copies.

## Remaining decisions

The plan remains unreviewed and uncommitted. Exact-version finance and operating
reviews, reviewed frozen baseline designation, private observations/counterfactuals,
attribution and executive memo composition remain subsequent work. No feasible
schedule alone authorizes an intervention. Retention operations, independent
review and the actual [pilot entry gates](../pilot-plan.md) remain open.
