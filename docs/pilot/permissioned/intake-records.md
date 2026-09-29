# Private source custody and finance review

This increment connects [processing grants](processing-grants.md) to persisted
[ledger preflight](intake-preflight.md) results, exact source bytes, correction
history and human finance decisions. It is tested with fictional records and
identities. Released in PR #43; exact-build acceptance is recorded in the
[completion checklist](../../portfolio/remaining-work.md).

No actual sponsor, company permission, accepted company records or performed
pilot is represented. The [pilot entry gates](../pilot-plan.md) still apply.

## Operator sequence

1. A scoped human data owner records the exact policy, named processing subjects
   and environment in a grant. Include the finance reviewer's authenticated
   subject among the permitted processing subjects.
2. The operator submits the policy, source manifest and original ledger bytes.
   The request names the current grant hash and dataset predecessor hash; the
   first intake uses a null predecessor. The server checks the current grant
   while holding the same company lock used for revocation.
3. An authorized submission stores its exact bytes and recomputed preflight in
   one transaction with its audit event. Invalid ledger structure, incomplete
   mappings, duplicate rows or failed controls produce a stored quarantine.
   Foreign-company headers, absent permission and sources over 10 MiB are rejected
   before custody. A stored quarantine is not finance acceptance.
4. The finance reviewer inspects the source and controls, then records accept,
   reject or request_changes with rationale and an evidence reference/hash. The
   decision binds the exact intake, current grant and prior review hashes.
   Acceptance replays preflight from stored bytes and fails for quarantined data.
5. A later decision can withdraw acceptance. New decisions must target the latest
   dataset version. A source correction appends a new intake, preserving earlier
   bytes, controls and decisions; its finance review starts empty.
6. An accepted-source read checks live permission, current dataset head, current
   finance acceptance and source reproduction under the company lock. Ordinary
   authorized source downloads also allow historical or quarantined records for
   investigation; they do not claim analytical eligibility.

Each dataset is a versioned replacement stream, not an additive set of monthly
imports. Resubmitting the same bytes with a new idempotency key and the current
parent creates a new version and requires a new finance review. It never adds the
amounts to an existing baseline. Separate populations need separate dataset keys;
composition into a private financial case remains future work.

## Roles and environment

| Operation | Required identity and scope |
|---|---|
| Read intake/review metadata | Company-scoped human with `pvc.read` |
| Store source | Named human processing subject, `operator`, `pvc.read` and `pvc.write` |
| Record finance decision | Named human processing subject, `operator` and `finance_reviewer`, `pvc.read` and `pvc.approve`, configured approval client |
| Download original or accepted source | Named human processing subject, `operator` and `pvc.read` |

`operator` here is an application processing role; it does not make the person
the company's accountable operating executive. Models and service principals
cannot perform these operations. Ordinary approval-demo identities acquire no
new roles. Role assignment and identity-provider integration need the agreed
pilot access decisions.

The API reads `PVC_PROCESSING_ENVIRONMENT_ID` from the server environment. Empty
configuration disables intake writes, finance decisions and source downloads
with HTTP 503. The request cannot choose or override that environment. It must
exactly match the current grant. This setting is not pilot authorization.

## API

All routes start with `/companies/{company_id}/private-intakes`.

| Method / suffix | Request or response |
|---|---|
| `POST /datasets/{dataset_key}` | JSON object with `intake` (`IntakeRequest`) and `source_base64` containing the original file bytes; returns a `PrivateIntake` receipt |
| `GET /datasets/{dataset_key}` | Intake metadata history, current intake ID, operating authority false; no source bytes |
| `POST /{intake_id}/reviews` | `FinanceReviewRequest`; returns the recorded human decision |
| `GET /{intake_id}/reviews` | Ordered finance decision history |
| `GET /{intake_id}/source` | Original bytes for an authorized processing subject |
| `GET /{intake_id}/source?accepted_only=true` | Original bytes only when current finance acceptance and current dataset/processing checks pass |

Writes require explicit bearer credentials. Browser cookies alone cannot write.
Authentication and company/role checks precede body consumption. Upload envelopes
are streamed with a 16 MiB limit, decoded sources are limited to 10 MiB, and review
bodies are limited to 1 MiB. Duplicate JSON keys and invalid base64 fail. Validation
responses contain generic messages, not private request values. Responses use
`Cache-Control: no-store`; source downloads use a fixed attachment filename.

Retried writes return the original historical receipt if the key, request, actor
and (for intake) source hash match. A later revocation or correction is not undone.
A receipt is not a current authorization check. Conflicting key reuse and stale
dataset/review parents return HTTP 409. Invalid binding or quarantine acceptance
returns HTTP 422; inaccessible or unauthorized records return HTTP 404.

## Persistence and verification

Migration `0009` adds `private_intakes` and `private_intake_reviews`. PostgreSQL
stores raw bytes with the intake row so source custody, metadata and audit commit
or roll back together. The database checks the SHA-256 of stored bytes, enforces
company/grant/parent relationships and unique stream/idempotency constraints, and
applies forced company row-level security. Runtime roles can insert/read, not
rewrite or individually delete receipts. Populated downgrades are blocked even
for a migration owner without an active company scope.

The in-memory repository provides the corresponding lock and rollback behavior.
Both adapters serialize grants, source writes, finance decisions and source-use
checks. Concurrent corrections have one winner. An intake waiting behind a
revocation transaction must observe the committed revocation before admission.

`test_private_records.py` exercises both adapters, real PostgreSQL constraints,
audit rollback, immutable source corrections, quarantine, withdrawal, revocation,
concurrent operations, authenticated API behavior, bounded payloads and
reproduction of a tampered preflight. The fixtures are fictional; tests do not
constitute an independent finance review of actual company records.

## Remaining boundaries

The original preflight flags remain false because the preflight itself supplies
neither permission nor a human decision. Grant events, finance decisions and
current accepted-source checks are separate evidence. Finance acceptance here is
a recorded review of a source version, not approval of an operating intervention.
Receipt hashes preserve content identity; they do not independently authenticate
an external agreement or substantiate a reviewer's judgment.

Revocation or expiry stops new processing, decisions and source downloads. It
does not erase historical metadata or copies already obtained. Authorized
whole-company offboarding removes database source bytes, intake/review records and
grants while retaining minimal audit events. Scheduled per-source expiry deletion,
legal holds, backup/copy disposal and an operational deletion receipt remain open.

Private receipts reject public-exhibit use and have no MCP tool or public case
export route. An authorized source download still returns private data and must
stay within the approved handling scope. Private financial-case/actuals integration,
provider processing, company-specific source adapters, staging deployment and real
human reviews remain to be completed before a company pilot. The subsequent
[financial snapshot](financial-snapshots.md) adds versioned monthly inputs from
accepted sources, with a separate release gate; it does not complete the private
underwriting, frozen baseline, counterfactual or memo workflow.
