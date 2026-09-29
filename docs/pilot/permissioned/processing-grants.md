# Private processing grants and revocations

The private grant registry records a human data owner's decision about one exact
intake policy, named operator subjects and one processing environment. It is a
permission control for the forthcoming intake workflow, separate from finance
acceptance and authorization to change company operations.

This implementation has been exercised with fictional test identities and
policies. No sponsor, actual agreement or company operating data is represented.
The [pilot entry gates](../pilot-plan.md) remain required.

## Scope and authority

A grant binds the complete [intake policy](intake-preflight.md), including its
company/entity, purpose, period/currency, source agreement reference and hash,
processing/retention window, account mappings and controls. The data owner also
names the exact authenticated operator subjects and environment identifier. A
changed policy requires another explicit decision; it does not inherit the
previous permission automatically.

The writer must be a human principal scoped to the company with the `data_owner`
role. Token-based requests need `pvc.read` and `pvc.approve` and the configured
approval client. An ordinary `approver`, `operator`, service or model cannot
grant or revoke processing rights. JSON writes require an explicit bearer
credential; a local browser session cookie is insufficient. No MCP tool exposes
these writes, and no existing demo token or role has been expanded.

`authority_attestation` records what the data owner asserts they have checked.
Software does not independently prove their legal authority, authenticate an
external agreement or complete the legal/data-processing review. Identity-provider
role assignment must follow the agreed pilot ownership and access decisions.

## API and record sequence

| Operation | Route / behavior |
|---|---|
| Grant or revoke | `POST /companies/{company_id}/private-grants/{grant_key}/events` |
| Read history and current policy status | `GET /companies/{company_id}/private-grants/{grant_key}?policy_sha256=<exact-policy-hash>` |
| First grant | `action=grant`, complete policy, nonempty `operator_subjects`, `environment_id`, `expected_previous_sha256=null`, unique `idempotency_key`, rationale and authority attestation |
| Change or reauthorize | New `action=grant` request with the current event hash and an explicit complete policy/operator/environment scope |
| Revoke | `action=revoke`, current event hash, new idempotency key, rationale and attestation; no replacement policy, operators or environment |

Responses are private and use `Cache-Control: no-store`. Write responses identify
the recorded historical event; clients must read current history/status before
using permission. Retrying an old grant returns its original receipt without
undoing a later revocation. Reusing a key with different contents or another
actor fails. Stale parents fail with a conflict; concurrent writers cannot fork
the current history.

`processing_grant_active` describes the current policy grant, not permission for
every caller. The processing check additionally requires a scoped human operator,
an exact subject match and the named environment. Expired, not-yet-valid, revoked,
missing or different-policy grants cannot support processing. The returned
finance, data-admission and operating-action flags remain false.

The registry's current-status function is not a historical availability replay.
`require_processing_permission` validates a supplied current history. It must be
used with a fresh, transactionally loaded stream at admission; a caller-provided
cached list cannot establish that no later revocation exists.

## Persistence, audit and deletion

Both repository implementations preserve grant events and audit them atomically.
PostgreSQL migration `0008` adds a company-scoped table with forced row-level
security, composite predecessor bindings, unique sequence/idempotency constraints
and insert/select-only runtime permissions. Company locking serializes the first
grant as well as later updates. An audit failure rolls back the grant.

Individual events cannot be updated or deleted by the runtime database role.
The populated downgrade guard detects history even when the table owner has no
active company scope. Authorized whole-company offboarding removes grant records
through the existing company deletion path and retains minimal audit history.
That behavior does not establish legal-hold handling or deletion of every external
file, replica or backup.

## Remaining intake work

The standalone `pilot-intake-check` remains a preflight with all authorization
flags false. It does not silently treat the presence of a grant as admission.
The next increment must connect freshly loaded grant state to private source
custody, persisted preflight/quarantine and correction history, with finance
decisions bound to exact source/policy versions. That admission transaction must
serialize against revocation. Retention/deletion for stored source bytes and
integration with private case/actuals contracts also remain open.

A real pilot still needs the sponsor, reviewers, approved environment and actual
decisions specified in the [permissioned pilot package](README.md).
