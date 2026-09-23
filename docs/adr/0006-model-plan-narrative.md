# ADR 0006: Model-written plan narrative

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-072

## Context
Sponsors read a short narrative before the tables. Templated text reads poorly and cannot weigh risks.

## Decision
`ModelNarrator` writes at most 180 words from the deterministic plan and findings. The narrative is discarded if it
contains any number absent from the plan or findings; on outage the plan is produced without a narrative.
Suspicious-content findings are excluded from the model input.

## Why a deterministic rule is insufficient
Summarising trade-offs and the dominant risk across workstreams is a writing task, not a calculation.

## Evaluation
No-new-numbers check on every call (hard gate); live eval samples narratives for factual consistency with the plan.

## Consequences
The plan never depends on the narrative; approval shows both, labelled.
