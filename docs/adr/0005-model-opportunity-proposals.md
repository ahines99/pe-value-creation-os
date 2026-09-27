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
- rejects unbound numeric prose; server-issued quantity references bind each metric, unit, company, period and evidence;
- enforces screening eligibility and overlapping-baseline rules in code, in addition to prompt guidance;
- validates rates and ordering, derives baseline values and flow-through, and applies policy costs;
- passes permitted documents as `<untrusted_document>` data, with no tools available to the model in this step; `PVC_MODEL_DOCUMENT_EXCLUDED_COMPANIES` excludes selected companies or `*` before prompt construction;
- pauses the run (`NEEDS_EVIDENCE`, reason `model_unavailable`) on outage or refusal unless policy selects rules.

## Why a deterministic rule is insufficient
Choosing *which* opportunities are worth sizing and at what realization, given a mix of metrics, findings and
documents, is judgment that thresholds encode poorly. Arithmetic stays deterministic.

## Evaluation
- Deterministic gate (CI): `evals/adversarial` cases run a scripted model that obeys injected instructions and
  invents numbers; every such proposal must be rejected (`pvc eval --suite adversarial --gate`).
- Live model eval (requires `ANTHROPIC_API_KEY`): `pvc eval --suite all --proposer model --gate` scores planted-lever
  recall, citation validity, rejection rate, and cost per run. Thresholds in `evals/thresholds.toml`; costs are estimates, not billing reconciliation.

## Consequences
- Token/cache usage and estimated model cost per run are tracked (`pvc.model.tokens`, `pvc.model.cost_usd`).
- A model outage never produces a guess; operators either resume later or switch policy to the rule fallback.


September 27 evaluation correction: the historical September 23 paid subset exercised the proposer only. Current evaluation includes narrator checks and negative/adversarial outcomes; it rejects empty selections and incomplete score evidence. Scheduled paid runs need explicit repository opt-in (`PVC_RUN_LIVE_EVALS=true`) as well as the API secret. No current live-provider rerun is claimed.
