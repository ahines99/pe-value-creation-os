# ADR 0005: Model-generated opportunity proposals

- **Status:** accepted
- **Date:** 2026-09-23
- **Ticket:** PVC-072, PVC-073

## Context
Rule-based proposers (`workflows/proposals.py`) fire only on screening-threshold breaches and use fixed policy
scenario rates. They miss opportunities that need judgment: combining signals across findings, adjusting rates to
company context (for example, a legacy book with many capped contracts), and reading management documents.

## Decision
`ModelProposer` (Claude, `claude-opus-5` by default, via the Anthropic SDK with a JSON-schema output format) may
propose opportunities for each diagnostic branch. The model supplies judgment only: lever, baseline metric *name*,
scenario rates, confidence, rationale and citations. The server:

- restricts levers, metrics and evidence ids to enumerated values in the output schema;
- rejects proposals whose text introduces numbers not present in the tool output given to the model;
- validates rates and ordering, derives baseline values and flow-through, and applies policy costs;
- passes documents as `<untrusted_document>` data, with no tools available to the model in this step;
- pauses the run (`NEEDS_EVIDENCE`, reason `model_unavailable`) on outage or refusal unless policy selects rules.

## Why a deterministic rule is insufficient
Choosing *which* opportunities are worth sizing and at what realization, given a mix of metrics, findings and
documents, is judgment that thresholds encode poorly. Arithmetic stays deterministic.

## Evaluation
- Deterministic gate (CI): `evals/adversarial` cases run a scripted model that obeys injected instructions and
  invents numbers; every such proposal must be rejected (`pvc eval --suite adversarial --gate`).
- Live model eval (requires `ANTHROPIC_API_KEY`): `pvc eval --suite golden --proposer model` scores planted-lever
  recall, citation validity, rejection rate, and cost per run. Thresholds in `evals/thresholds.toml`.

## Consequences
- Model spend per run is tracked (`pvc.model.tokens`, `pvc.model.cost_usd`).
- A model outage never produces a guess; operators either resume later or switch policy to the rule fallback.
