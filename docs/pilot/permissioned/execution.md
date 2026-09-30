# Private intervention decisions and delivery evidence

This increment records bounded human authorization, reported work, and independent
task acceptance against an exact [reviewed baseline](reviewed-baselines.md).
Its release gate is separate from local implementation; see the
[completion checklist](../../portfolio/remaining-work.md). Validation uses
fictional identities, commitments, records and decisions. No real sponsor,
permission, company intervention or realized value is represented.

## Authorize a bounded scope

A company-scoped human processing operator with the `approver` role records an
authorization. Approval scope and the configured approval client are required.
Authorization binds the baseline's exact capacity plan and includes:

- Selected, scheduled tasks and their prerequisite tasks.
- A named human operator for every demanded resource, with a capacity-commitment
  evidence reference, hash and attestation.
- A future or current start timestamp and an exclusive expiry within the frozen
  plan's 100-day horizon. Authorization cannot be backdated.
- A nonnegative cost limit for the work charged to this authorization, in the
  baseline's currency and native units.
- The permitted population/actions, constraints, stopping conditions, rollback
  plan and evidence of the sponsor's authority.

These references and attestations are recorded human assertions. The application
does not authenticate the referenced documents, establish a person's legal
authority, confirm actual capacity or perform a company-side action. Real pilot
entry gates and company review remain necessary. Plan review and baseline
designation alone still do not authorize an intervention.

Subsequent `hold`, `stop` or `withdraw` decisions remove current recorded support.
They take effect at their server recording timestamp. They can be recorded even
after source processing is revoked, the baseline is superseded or source review
is withdrawn. They do not reopen raw source bytes or grant new permission.
Resumption requires a new explicit authorization, current baseline/source support,
fresh processing permission and a non-backdated window. A replacement decision
does not retroactively authorize earlier work.

## Report work without concealing exceptions

Only the assigned accountable human operator can report a delivery segment.
Each segment identifies a stable `work_key`, task, exact authorization, actual
start/through timestamps, state, effort for each demanded resource, incurred
cost, delivered scope/exceptions and an evidence reference/hash/attestation.
These are reported observations, not independently verified accounting facts.
Future work cannot be reported as performed.

A work key identifies one segment within the baseline. Updates to that key are
cumulative corrections of that segment, retaining its task and reporting author.
They replace its contribution to the current reported totals while preserving
the original receipts. Separate segments represent disjoint portions of work,
including work before and after a pause under different authorization versions.
The reporting operator and reviewer must check that segments do not duplicate
the same work or costs; a unique key alone does not establish that fact.

The workflow preserves reports of work outside the authorization window, work
spanning a hold/replacement, work before the plan's earliest start, impossible
reported person-hours and cost overruns. It exposes those exceptions rather than
discarding actual reports. Such exceptions prevent accepted completion support.
Reported costs across current segments bound to one authorization are compared
with that authorization's limit. An overrun also removes current authorization
support in the status report; a new decision does not erase the previous overrun.

The status reports total case costs and costs charged to the latest authorization
separately. Each authorization has its own explicit limit; limits are not summed
or presented as a new approved baseline budget. Reported costs do not modify the
frozen financial forecast or replace reconciled ledger actuals.

## Accept exact work and prerequisite evidence

A scoped human `operating_reviewer` records accept, reject, request-changes or
withdraw decisions. Approval scope/client are required. The reviewer must be a
different person from every submitting operator whose segments are being reviewed.
An acceptance must bind every current segment for its task exactly once, and all
segments must be completed without authorization/effort/cost exceptions.

Every prerequisite needs an exact current acceptance recorded before the dependent
work began. A corrected segment, new segment, withdrawn/replaced prerequisite
acceptance or unsupported baseline invalidates downstream current support. The
original work and decision receipts remain unchanged. Reacceptance is explicit;
it never silently reactivates a dependent receipt bound to an older version.

A reviewer can withdraw the preceding accepted delivery set after processing
revocation without reproducing source data. The withdrawal must retain the exact
accepted segment bindings. Other new decisions and delivery reports require
current baseline/source support and named processing permission.

Natural authorization expiry does not invalidate properly completed and accepted
historical work. A later stop likewise does not rewrite a prior work interval.
Neither task acceptance nor a recorded authorization proves causal financial
impact. [Actuals/counterfactual comparisons](observations.md) remain separate,
and all differences there remain unattributed until a supported attribution
workflow is implemented and reviewed.

## API, history and current status

All routes have the prefix `/companies/{company_id}/private-execution`.

| Method / suffix | Purpose |
|---|---|
| `POST /baselines/{baseline_id}/events/{kind}` | Append a `PrivateExecutionRequest`; kind is `authorization`, `delivery` or `acceptance` and must match the body |
| `GET /baselines/{baseline_id}/events` | Historical event receipts; no current-permission claim |
| `GET /baselines/{baseline_id}/status` | Reproduce original baseline support and replay execution history under current processing permission |

Role checks precede parsing of a bounded 1 MiB private body. Writes require an
explicit bearer token; responses are non-cacheable and validation errors omit
private input details. Models and services cannot submit or read these private
human workflows. Hold/stop/withdrawal paths do not require a configured processing
environment; they retain the human role and approval checks. There are no MCP or
public-export routes and no source-system writeback.

The baseline has one append-only event sequence. Every new event supplies the
current predecessor hash, preventing stale decisions and concurrent branching.
Same-author exact idempotent retries return the historical receipt, including
after revoked processing, without restoring support. Company locks serialize
authorization, source revocation and review changes; receipts and minimal audit
references commit atomically. Current status refuses a clock earlier than its
stored history.

Migration `0015` adds forced company row-level security, exact baseline/case and
predecessor foreign keys, unique heads and insert/select-only runtime permissions.
Populated downgrades are blocked even for migration owners without company scope.
Whole-company offboarding removes the execution receipts with their source chain.

## Remaining pilot work

Private attribution and delivery-to-claim reconciliation, an integrated executive
memo and usable review interface remain unfinished. So do per-source expiry,
legal holds, backup/copy disposal, authenticated staging and the other
[pilot entry gates](../pilot-plan.md). Sponsor authority, real source records,
actual management review and operating activity cannot be supplied by a test fixture.
