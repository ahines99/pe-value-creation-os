# ADR 0034: Private underwriting with source-bound revisions

Status: Accepted for implementation; release and pilot acceptance are separate.

## Context

Accepted private financial snapshots establish mapped historical balances. They
do not establish contract eligibility, achievable operating changes or approved
forecasts. The existing public underwriting contract explicitly requires
constructed operating assumptions and must not be widened to admit private data.

## Decision

Introduce separate private forecast inputs, assumption bases and revision history.
Bind forecasts to exact currently usable baseline-candidate financial snapshots.
Preserve company/entity/currency/origin and historical/forecast period boundaries.
Require every assumption to identify either an exact financial-component mapping
or an explicit operator judgment; record initiative eligibility, constraints and
falsification evidence as review inputs without claiming independent verification.

Extract neutral validation, disjoint-pool ledger calculation and scenario reports
from the public calculator. Preserve the public schema, serialized field order,
classification requirements, calculation versions and rendered artifact behavior.
Use fixed private Decimal precision and bounded numeric inputs. Do not synthesize
a public case or use a constructed source book for private calculations.

Store append-only private forecast revisions and audit events atomically under
the same company lock as grants/source corrections. Use exact-source reproduction,
forced RLS, source/predecessor foreign keys, optimistic concurrency, actor-bound
idempotency, populated-downgrade protection and whole-company offboarding.
Historical retrieval and current-usability checks remain separate operations.

Expose only authenticated private API routes with bounded request bodies and
server-side processing environment selection. Human processing/write authority
is required; models/services have no mutation or direct private-source route.

## Consequences

Private accounting inputs can support versioned incremental EBITDA, cash and
valuation sensitivities without changing public provenance contracts. Source
acceptance does not become forecast approval, causal impact or operating authority.
Document locators/hashes preserve authored references but do not establish their
truth, rights or eligibility. Financial review of assumptions remains required.

Disjoint benefit pools are supported; private shared populations require explicit
future source/allocation contracts. Capacity-plan association, finance/operating
reviews, frozen baselines, observations, attribution and memo integration remain
open. Historical derived data survives revocation until authorized retention or
offboarding operations remove it. See the [workflow guide](../pilot/permissioned/underwriting.md).
