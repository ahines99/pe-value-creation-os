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
| Interim update | FY2026 Q1/Q2 and their comparative periods; quarter earnings and YTD cash remain distinct |
| Information cutoff | September 28, 2026; selected filings through Q2 and the September 22 acquisition event, not a claim of complete disclosure coverage |
| Currency and scale | USD; source tables in thousands; calculations in native dollars; memo displays millions |
| Method | Public source facts, explicit accounting bridges, then hypotheses; constructed operating schedules will be separate |
| Audience | PE operating partners/executives; source and technical appendix for diligence |
| Decision authority | Codex authors research and proposed assumptions; no actual management decisions inferred |

## Source and publication policy

`data/public/progress/financial-facts.json` assembles facts extracted directly from
the issuer's annual and interim filings. Every fact preserves its document identity, page, row, comparative column,
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

The public registry contains 81 annual and 160 interim facts. FY2025 checks match. FY2023 and FY2024 cash-flow
amortization includes amounts beyond the two acquired-intangible amortization
rows in the income statement. The differences remain explicit; dependent earnings
measures are withheld, while independently supported cash remains available. This is a mapping
and accounting-definition question, not evidence of an issuer error.

Q2 cash/D&A is calculated from YTD minus Q1 with both sources and cross-filing
comparability checks. The 2025 comparative amortization difference remains open.
The September 22 Domo acquisition is shown as a subsequent perimeter change;
historical statements are not represented as post-acquisition pro forma results.

The [constructed underwriting exercise](../../data/constructed/progress/README.md)
now supplies typed operating assumptions and dated 24-month EBITDA/cash scenarios,
cost commitments, collection reversals and illustrative incremental EV sensitivity.
Its operating records are explicitly authored examples, not Progress data. The
[constructed 100-day plan](../portfolio/operating-plan.html) now reserves weekly
capacity, enforces dependencies and supplies delayed dates to the same economics.
No actual assignment or accepted deliverable is represented. [Case history](../portfolio/case-history.html)
now preserves original/current inputs and outputs, with separately classified
simulated review receipts. Actual authenticated review is supported by the API
but has not occurred for this public case.

The public baseline now includes the ShareFile contribution/residual bridge,
three-year revenue mix and four typed research assessments with counterevidence.
The residual is not organic growth; standalone acquired earnings remain unavailable.
The disclosed TSA termination is rejected as a new saving because it already occurred.
See [ADR 0014](../adr/0014-acquisition-growth-research.md).

The public peer exhibit now records metric-specific decisions for PTC, OpenText,
Descartes and an unquantified SS&C candidate. The strict median is withheld;
reported differences do not become savings targets (ADR 0015).

Still required: wider candidate/definition review, reviewed commercial conclusions,
richer interactions,
public-baseline integration, actual execution evidence, full decision memo and
realization demonstration. These foundations do not complete S1 or any later goal
milestone by themselves.

Alex confirmed that no operating-company sponsor is available yet and requested
the [permissioned pilot package](permissioned/README.md). Preparation proceeds;
actual access, management participation and observed outcomes remain unperformed.
