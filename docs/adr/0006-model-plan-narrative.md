# ADR 0006: Model-written plan narrative

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-072

## Context
Sponsors read a short narrative before the tables. Templated text reads poorly and cannot weigh risks.

## Decision
`ModelNarrator` writes at most 180 words from the deterministic plan and findings. The narrative is discarded if it
contains unbound numeric prose rather than server-issued metric/unit/company/period/evidence references; on outage the plan is produced without a narrative.
Suspicious-content findings are excluded from the model input.

## Why a deterministic rule is insufficient
Summarising trade-offs and the dominant risk across workstreams is a writing task, not a calculation.

## Evaluation
Quantity-reference validation runs on every call. The current harness exercises narrator results, safety rejection and failures, including a scripted narrator-injection case. The September 23 paid subset did not exercise the narrator. A current live proposer/narrator evaluation is pending.

## Consequences
The plan never depends on the narrative; approval shows both, labelled.
