# Model provider data handling (PVC-147)

**Status:** review packet prepared. **The review itself is pending** (legal and the operating partner must approve before any pilot data reaches a model). Until then production runs use `PVC_PROPOSER=rules`, which sends nothing to a model.

## What is sent, and when
Model calls happen only in two judgment steps, only when `PVC_PROPOSER=model`:

| Step | Data sent | Not sent |
|---|---|---|
| Opportunity proposals (per diagnostic branch) | Aggregated tool outputs for that branch (metrics, cohort and segment summaries, waterfall layers), finding statements, evidence ids, policy thresholds, and the company's management documents (delimited as untrusted data) | Customer-level rows, customer names, invoice lines, credentials, other companies' data |
| Plan narrative | The deterministic plan (workstreams, initiatives, value-case totals, KPIs) and finding statements (suspicious-content findings excluded) | Documents, customer-level data |

Data classes: company-confidential financial aggregates and management commentary. Aggregated outputs are intended to exclude personal rows, but documents and finding statements can contain personal or confidential content. Review the permitted inputs per company before enabling model calls; this is not an automatic personal-data detector.

## Controls in place
- Egress allow-list: only `api.anthropic.com` for model calls (application check and network firewall).
- No tools are available to the model in these steps; output must match a JSON schema and passes the no-new-numbers and citation guardrails.
- Input/output tokens, cache creation/read tokens and estimated cost are recorded per call (`pvc.model.tokens`, `pvc.model.cost_usd`); prompts and outputs are not logged.

Cost records are estimates based on configured rates, not billing reconciliation. Historical September 23 usage omitted full cache accounting and exercised only the proposer.

## Decisions for the review
1. Data-processing terms with the model provider (commercial terms, retention settings available to the organisation, and whether zero-data-retention applies to the chosen model).
2. Which portcos' agreements permit sending management documents to a third-party processor.
3. Whether documents must be excluded from model input. Set `PVC_MODEL_DOCUMENT_EXCLUDED_COMPANIES` to comma-separated company IDs, or `*` for all companies. Exclusion happens before provider prompt construction; it does not redact independently supplied findings or aggregates. Verify the company setting and approved data classes before enabling the model.

## Sign-off
| Reviewer | Role | Date | Decision |
|---|---|---|---|
| _pending_ | Legal | | |
| _pending_ | Operating partner | | |
