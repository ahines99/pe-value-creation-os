# Progress Software public diligence case charter

Status: implementation in progress, September 28, 2026. Owner: Codex. The complete
goal remains the five outcomes in the [operating-partner roadmap](../operating-partner-roadmap.md),
including an actual permissioned pilot when a sponsor is available.

## Fixed case choices

| Field | Decision |
|---|---|
| Entity | Progress Software Corporation, CIK 0000876167, PRGS |
| Role | Public research subject; no represented client, portfolio holding or acquisition |
| Baseline | Consolidated FY2025, December 1, 2024 through November 30, 2025; comparative FY2024 and FY2023 from the same filing |
| Source | FY2025 Form 10-K, accession 0000876167-26-000008, filed January 20, 2026; issuer-hosted PDF |
| Information cutoff | September 28, 2026; initial extraction covers annual tables only, not all information available at that date |
| Currency and scale | USD; source tables in thousands; calculations in native dollars; memo displays millions |
| Method | Public source facts, explicit accounting bridges, then hypotheses; constructed operating schedules will be separate |
| Audience | PE operating partners/executives; source and technical appendix for diligence |
| Decision authority | Codex authors research and proposed assumptions; no actual management decisions inferred |

## Source and publication policy

`data/public/progress/annual-facts.json` is extracted directly from the issuer's
filing. Every fact preserves its document identity, page, row, comparative column,
period, unit and original signed amount. Document and mapping hashes are retained.
The local raw PDF remains under ignored `var/public-diligence/sources/`; the public
repository includes a compact factual extract and source links, not the full report.

The separate university WRDS/LSEG study stays private. Its fields are not copied
into this public bundle. A public fact must be independently sourced through the
public route. The source report is not relicensed by the repository's Apache-2.0
code license. Constructed records will retain that label through all calculations
and exports; they cannot become Progress customer or operational evidence.

## Questions to investigate, not accepted opportunities

1. How much reported growth reflects acquisitions, currency and mix rather than
   organic improvement? Gather issuer acquisition/contribution disclosures before
   comparing growth with peers.
2. Which recurring commercial mechanisms can be investigated without assuming all
   revenue behaves like SaaS ARR? Contract/channel/cohort evidence is still absent.
3. Where could a service intervention reduce cost rather than merely release staff
   time? Real ticket volumes, quality thresholds and a cost action are needed.
4. Could collection timing improve cash without changing earnings? Actual aging,
   terms, disputes and seasonality are needed before sizing a working-capital case.
5. Which integration expenses are temporary, continuing or already addressed in
   guidance? A labeled accounting adjustment is not automatically an avoidable cost.

Do not force a favorable thesis, accepted initiative count or peer-implied savings
target. A rejected or deferred hypothesis is a legitimate decision output.

## Current evidence and remaining work

The first implementation extracts 81 annual facts across three years and six
statement checks per year. FY2025 checks match. FY2023 and FY2024 cash-flow
amortization includes amounts beyond the two acquired-intangible amortization
rows in the income statement. The differences remain explicit; derived measures
for those periods are conservatively withheld until reviewed. This is a mapping
and accounting-definition question, not evidence of an issuer error.

Still required: quarterly facts, acquisition/growth bridge, metric-specific peer
eligibility, typed thesis/assumption and immutable case revisions, monthly
initiative P&L/cash scenarios, interactions, constrained execution, full decision
memo and realization demonstration. This annual baseline does not complete S1
or any later goal milestone by itself.

Alex confirmed that no operating-company sponsor is available yet and requested
the [permissioned pilot package](permissioned/README.md). Preparation proceeds;
actual access, management participation and observed outcomes remain unperformed.
