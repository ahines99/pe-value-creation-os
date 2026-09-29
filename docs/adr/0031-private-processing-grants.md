# ADR 0031: persist human private-processing authority separately

Date: September 29, 2026. Status: implemented increment; admission remains pending.

The private preflight deliberately cannot verify an agreement or approve data
use. Add an append-only grant stream rather than changing a preflight boolean or
loosening constructed-only case contracts.

Each grant binds an `IntakePolicy`, exact authenticated operator subjects and a
processing environment. Its writer is a scoped human `data_owner` with the
approval API's client/scope controls. Revocation appends to the same chain; a
replacement grant must bind the current head. Retried historical requests cannot
reactivate a revoked scope. Finance review and operating approval remain distinct.

Use the existing in-memory/PostgreSQL repository interface, audit transaction and
company scope. Migration 0008 adds forced RLS, composite parent identity, unique
sequence/idempotency and append-only runtime access. Lock the company row before
reading the current head to serialize both initial and later grants. Include the
new collection in in-memory rollback and both offboarding implementations.

Expose the registry only through the separate authenticated approval API. Reads
require human company scope and OAuth read permission where present. Writes
require an explicit bearer credential. Do not add a model-callable authorization
tool or expand existing dev-token roles.

Source agreement references and human attestations are evidence of what was
recorded, not automated legal verification. Current status is not a historical
point-in-time claim. The supplied-stream processing check is a reusable predicate,
not a substitute for loading the latest record atomically during admission.

Tests cover memory/PostgreSQL behavior, stale and concurrent updates, exact policy,
operator/environment scope, expiry/revocation, replay, cross-company access,
approval client/role/CSRF boundaries, atomic audit, RLS, immutable records,
populated downgrade protection and offboarding. The older execution downgrade
tests restore the migration head after testing their specific historical guard.

Next: source custody, transactional intake/quarantine/correction records, finance
acceptance, private-case integration and complete retention/deletion handling.
The registry alone does not satisfy private-data readiness or a performed pilot.
