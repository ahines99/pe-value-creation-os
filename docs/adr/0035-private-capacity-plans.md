# ADR 0035: Private capacity proposals and scheduled financials

Status: Accepted for implementation; release and pilot acceptance are separate.

## Context

Private forecasts now preserve accepted financial sources and explicit authored
assumptions. They still need to reflect scarce operator capacity and prerequisites
without implying actual assignments, accepted delivery or operating permission.
Public plans must retain their constructed provenance and existing serialization.

## Decision

Share a structural planning base, scheduler and benefit-timing transformation.
Keep separate public and private plan contracts; private plans bind exact saved
underwriting revisions and record capacity evidence/attestations. Preserve public
field order, classification and numerical behavior. Private resources remain
proposed and cannot use simulated-assignment or actual-assignment labels.

Calculate the selected private initiatives and their enablers under explicit
resource/workstream limits. Delay benefits until the later of the original date
and planned gate; suppress infeasible or expired opportunities while preserving
original costs and collection counterfactuals. Store original/scheduled reports
without mutating underwriting history. Keep the private evaluator's fixed local
Decimal precision, including capacity scheduling and constrained hour inputs.

Persist private capacity revisions separately, with exact underwriting/source
reproduction, company locking, atomic audit, source/predecessor foreign keys,
forced RLS, immutable runtime access, idempotency and offboarding. Require current
source permission and latest underwriting/plan revisions for current-use reads.
Historical retrieval remains a distinct scoped-human operation.

## Consequences

A private proposal now connects resource assumptions to dated EBITDA, cash and
valuation sensitivity. Its feasibility is conditional on authored inputs and
does not establish management commitment, optimality or execution acceptance.
The common planning fields remain stable; private `case_id` denotes the case key
and its underwriting hash denotes the saved private revision rather than the
public case-input fingerprint.

Exact-version finance/operating decisions and frozen baselines remain subsequent
integration work. A new forecast cannot silently rebind an old plan, and later
review must distinguish current support from a preserved historical baseline.
Observed delivery, counterfactuals, attribution, private memos, retention and pilot
readiness remain open. See the [workflow guide](../pilot/permissioned/capacity-plans.md).
