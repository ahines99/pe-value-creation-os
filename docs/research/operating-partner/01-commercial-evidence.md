# Commercial thesis and evidence roadmap

Research date: 2026-09-27. Scope: repository audit and primary-source research; no new production functionality or claims about achieved company results. Owner: Codex. Primary audience: PE investment and operating leaders; technical reviewers should be able to reproduce every displayed conclusion.

## Recommendation

Build one Progress Software case with two explicitly separate layers: a public financial and commercial diligence memo grounded in issuer filings, and a constructed operating exercise that demonstrates how a management team would test the hypotheses. Keep the existing academic WRDS/LSEG comparison privately reproducible. Do not translate a peer margin difference directly into an EBITDA opportunity, or describe constructed transactions as Progress customer records.

The first thesis should be a **decision to investigate**, not a predetermined savings claim: which commercial or operating mechanisms could improve recurring economics without damaging retention, product quality or channel relationships, and what evidence would permit approval? The portfolio should demonstrate at least one supported decision, one rejected hypothesis and one deferred hypothesis. Those outcomes should follow the evidence; they are not quotas to manufacture findings.

The issuer describes an acquisition-oriented business with mixed perpetual, term and subscription models, significant indirect channels and a single reportable operating segment. It also cautions that its ARR definition may differ from other companies. These features make a uniform SaaS benchmark inappropriate as an operating target. Consolidated disclosure does not supply product-level profitability or contractual pricing headroom. Sources: [Progress FY2025 10-K, Business, ARR and segment disclosures](https://investors.progress.com/static-files/3c6bd027-e443-4977-9b29-b55ee2530013), printed pages 4–8, 29 and 70.

## What actually exists

Paths below are relative to the repository root. They describe implemented contracts and calculations, not proof of a live integration or management adoption.

| Capability | Evidence in repository | Remaining gap |
| --- | --- | --- |
| Reproducible statement research | `research/models.py` and `research/pilot.py` under `src/pe_value_os/`: entity IDs, source hashes/rows, dates/vintages, revision selection, annual/quarterly separation, issuer bridges, restricted private output | Sources restricted to `comp.funda`/`comp.fundq`; bundle classification has only licensed-private/synthetic. No first-class public issuer source contract or source-specific metric definition registry. |
| Peer context | `research/pilot.py:analyze`: same-currency annual alignment within 183 days, explanatory peer rationale/limitation, minimum three usable values for medians | No metric-specific eligibility, business-model scorecard, segment bridge, acquisition-adjusted comparability, or peer exclusion sensitivity. Three observations are a display floor, not statistical validation. |
| Research boundary | `research/pilot.py` returns `operating_plan=not_created`, hypothetical basis-point sensitivities, and pending human acceptance | No governed conversion of a research observation into a falsifiable commercial thesis and an evidence request. |
| Operational data contracts | `domain/source_models.py`: P&L, customers, ARR, invoices, price books, contracts, concessions, CRM, support, usage and headcount | SaaS-oriented account/ARR definitions need explicit scope mapping for a mixed licensing business. No constructed-versus-observed classification on each record/assumption. |
| Import mechanisms | `adapters/csv_export.py`, `warehouse.py`, `hubspot_crm.py`, `stripe_billing.py`, `zendesk_support.py`, `sources.py` | Adapter existence does not establish authorized access to Progress operating systems. Use CSV for the first case; prove mapping and reconciliations before adding integrations. |
| Data sufficiency | `domain/sufficiency.py`: required datasets, freshness, history, currency, monthly gaps, parsing errors and entity warnings | Does not prove economic representativeness, row-to-ledger coverage, contract enforceability, or causal relevance. A syntactically complete constructed dataset can pass. |
| Commercial calculations | `domain/pricing.py`: pocket-price waterfall, comparable discount groups, renewal realization and contract constraints; `domain/retention.py`: cohort/segment retention; `domain/metrics.py`: named SaaS metric variants | Existing fixture assumptions cannot become claims about the focal issuer. Need source-defined denominators, channel/customer/product scope and reconciliation to the public baseline. |
| Evidence primitives | `domain/models.py`: provenance, evidence relation, supporting/contradicting IDs, confidence, assumptions | No multidimensional evidence assessment, material-assumption coverage gate or mandatory disconfirmation. An authentic file can still be irrelevant to a claim. |
| Candidate proposals | `workflows/proposals.py`: policy-threshold rules and default scenario rates, deterministic baselines | Threshold breach is a screening event. It lacks explicit mechanism, counterfactual, alternative explanation, falsification test and decision state. |
| Automation discipline | `domain/ai_ops.py` withholds sizing for finance/billing processes lacking transaction volumes | Tier-1 support feasibility/risk scores are defaults; measured cost/volume still does not prove safe deflection, cash savings or capacity realization. |
| Existing benchmark tool | `benchmarks/__init__.py`, `tools/benchmark.py`: distributions, provenance/licence, synthetic flag, minimum five peers | Bundled data is synthetic. Minimum count is not a redistribution permission or a proof that a peer set is comparable. Keep this separate from named-company public research medians. |

## One coherent case, three source classes

### Public facts lane

Use issuer filings as the canonical public baseline, starting with FY2025 and adding subsequent available filings with an explicit information cutoff. Extract a compact set of facts with source URL, filing accession/date, page/table, reporting entity, duration, currency, unit, definition and immutable content hash where a permitted snapshot is retained. Link to originals; do not bundle full reports unnecessarily.

The SEC APIs provide filing histories and standardized entity-wide XBRL facts without API keys. They omit custom-taxonomy and non-entity-wide facts from those aggregated endpoints, so a company-facts result is not a complete filing or a product schedule. Calendar frames also require attention to actual fiscal dates. Use original filing tables for missing or contextual facts. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

Public data may support a question about acquisition integration, revenue quality, collections or cost composition. It does not establish customer discounts, contract exceptions, ticket eligibility or vendor overlap. No automatic allocation of consolidated costs to invented product segments.

### Constructed operating lane

Create a separate case identity, for example `progress-operating-exercise`, displayed everywhere as **constructed operating schedules anchored to selected public facts; not company records**. Do not attach invented customers to the real company's legal entity as if observed. A case may link to Progress as its public reference company while preserving separate observation scope.

Start with 24 months of internally coherent customer/ARR, contract/invoice, CRM and support/labor schedules. Include channel versus direct business, product family, contract type, renewal month and customer size. Build from a manifest of assumptions with deterministic seed and version. Reconcile only the totals explicitly declared as anchors; make remaining allocation residuals and out-of-scope businesses visible. Do not force a fictional SaaS ledger to explain all reported revenue. ARR, bookings, invoices, cash and recognized revenue must remain separate measures.

Include realistic counterexamples: contractual caps, channel discounts justified by partner services, low-price long-tenure cohorts with stronger retention, support cases that require expert escalation, an initiative already reflected in the baseline, and opportunities that compete for the same customers. A constructed example can validate workflow behavior and arithmetic; it cannot validate that Progress has that opportunity or that the assumed effect is likely.

Working capital/procurement schedules should be deferred from the first operating exercise unless needed to answer an explicit case question. If added, use a separate cash-release mechanism and vendor/account ledger; do not label reduced receivables as EBITDA improvement.

### Private academic lane

Preserve WRDS/LSEG extracts, proprietary definitions and vendor-derived reports in ignored private storage. Record entitlement and permitted use for each source separately. Do not republish a vendor-backed chart simply because the underlying company is public; rebuild the public case independently from public sources.

IU's policy limits electronic-resource use to individual noncommercial research/learning and states restrictions on automated use, dissemination and derivative works. WRDS permits off-platform research subject to vendor agreements and emphasizes private storage and deletion when access ends. These sources do not establish the exact terms of the user's particular subscriptions. Codex should prepare a short entitlement checklist and use public sources for any work that does not require licensed access; the user need only handle institutional clarification when a specific licensed use requires it. [IU e-resources policy](https://libraries.indiana.edu/policies/e-resources-use), [WRDS download policy](https://wrds-www.wharton.upenn.edu/pages/about/data-download-and-analysis-policy/)

## Comparability before benchmarking

Treat the existing 12 companies as a candidate universe, not an approved peer set. Build a dated selection matrix from each candidate's issuer filings. Record product/workflow exposure, revenue model, recurring versus perpetual mix, direct/channel mix, customer sector and size, services intensity, acquisition activity, geographic mix, currency, fiscal dates and accounting definitions. Describe unknowns explicitly.

Use metric-specific cohorts: a company might inform mature-software operating costs but be unsuitable for customer acquisition or retention comparison. Segment-level comparisons require disclosed comparable segment facts; missing disclosures do not authorize synthetic segment profit estimates. Avoid optimizing the peer list to create a desired gap. Freeze selection rules before computing results, retain exclusions with reasons and show all-candidate versus stricter-cohort sensitivity.

For the first release, use a small transparent comparison set and ranges. A 12-company cross-section is too weak a basis for elaborate adjustment regressions presented as causal potential. Withhold a benchmark where definitions or membership fail the gate, even when a numeric median can be calculated. Observed gap, hypothesized mechanism and management-approved target should be separate fields and distinct visual states.

## Evidence quality and falsification

Retain the existing hash and source IDs, but assess evidence against the particular claim. Proposed dimensions:

| Dimension | Required record | Example of a failure |
| --- | --- | --- |
| Provenance and authenticity | Original source, immutable reference, producer, transformations | Correctly hashed copy with unknown original producer |
| Scope and relevance | Claim, population, product, period, denominator | Consolidated SG&A used to infer support labor |
| Completeness and reconciliation | Coverage, excluded rows/value, ledger tie, sampling limits | High apparent discounts driven by omitted full-price invoices |
| Definition and comparability | Metric formula and accounting mapping | Company ARR compared with an incompatible peer definition |
| Currency and time | Currency, economic period, available date, revision | Restated data portrayed as known at underwriting |
| Causal strength | Mechanism, counterfactual, alternatives, observed intervention | Correlation between ticket volume and churn treated as proven causation |
| Contradiction and uncertainty | Disconfirming sources, unresolved tests, bounds | Renewal caps ignored when proposing price increases |
| Rights and classification | Public/licensed/constructed/permissioned; permitted output | Private licensed values included in public screenshots |

Do not collapse these dimensions into a pseudo-precise weighted confidence score. A useful executive badge can show `direct`, `corroborated`, `proxy` or `hypothesis`, with a separate **constructed** marker that cannot be upgraded to factual evidence by volume or a ledger reconciliation. A sourced public filing is strong for the reported fact and weak for undisclosed customer behavior. Confidence and evidence grade are not realization probabilities.

Every thesis should include mechanism, affected population, supporting evidence, counterevidence, material assumptions, alternative explanations, required test, rejection threshold, expiry/review date and decision owner. Reject or defer when a material causal link has no support; preserve the decision and what would reopen it.

| Candidate question, not current company finding | Minimum operating evidence | What would change the decision |
| --- | --- | --- |
| Is renewal price realization below enforceable contractual terms? | Contract-level caps/notice terms, invoices, quantities, renewal cohorts, credits, channel arrangements and cancellation outcomes | Apparent gap disappears after mix/quantity adjustment; caps prohibit uplift; churn or concessions outweigh gains |
| Can selected service work be automated economically? | Eligible ticket cohorts, handle time, fully loaded costs, escalation/reopen rates, quality evaluation and staffing/vendor cost action | Safe containment is low; quality or customer harm rises; costs cannot be removed or avoided; required platform cost exceeds benefit |
| Can collections improve without harming customers? | Invoice due dates, terms, dispute status, aging, payment/credit history and collection capacity | Seasonality or changed contractual terms explains delay; disputed balances dominate; no collectible addressable pool |
| Are acquisition integration costs addressable? | Dated integration plan, already-approved actions, general ledger, vendor contracts and organizational owners | Savings already included in forecast; costs support required capabilities; duplicate initiatives claim the same cost pool |

## Prioritized Codex tickets

Estimates are focused engineering/research days for one engineer, including meaningful verification, not elapsed service commitments. Financial engine, lifecycle and executive presentation work belong to companion reports; avoid adding these estimates twice. No ticket depends on the user writing code or making routine design decisions.

| ID / priority | Deliverable and dependency | Acceptance | Effort / owner |
| --- | --- | --- | --- |
| CE-01 / P0 | Case charter and source/rights manifest; no dependency. Fix public reference entity, cutoff, public/private/constructed lanes and intended claims. | Every input/output has source class and permitted destination; public case runnable without vendor credentials; no implication of client engagement. | 0.5–1 day, Codex. User only if institutional rights clarification is actually needed. |
| CE-02 / P0 | Public issuer baseline adapter and fact registry; CE-01. Add source-specific contracts rather than pretending issuer facts are Compustat rows. | Selected facts tie to filing tables; missing/custom tags handled explicitly; currency/duration/revisions preserved; independent public inputs generate public outputs; material unmapped fields block dependent calculations. | 2–3 days, Codex. |
| CE-03 / P0 | Metric-specific peer selection dossier and deterministic eligibility; CE-02. | Inclusion/exclusion written before results; three or more eligible facts required for displayed medians; fiscal/definition differences visible; exclusion sensitivity and deliberate withholding demonstrated. | 1.5–2.5 days, Codex. |
| CE-04 / P0 | Evidence assessment plus thesis decision contract; CE-01. Reuse finding/evidence IDs. | Every material claim distinguishes observation, hypothesis, constructed scenario and approved action; contradiction and falsification fields required; constructed data cannot pass factual-evidence gate; edits produce an audit record. | 2–3 days, Codex. |
| CE-05 / P1 | Constructed operating case and reconciliation workbook/JSON; CE-02, CE-04. Reuse CSV importer. | Deterministic regeneration; declared public anchors reconcile; no real customer identifiers; 24-month linkage/coverage checks; channel/contract edge cases; all rendered/exported scenario claims labelled constructed. | 2–3 days, Codex. |
| CE-06 / P1 | Three to five thesis investigations with explicit retain/reject/defer decisions; CE-03–05. Connect only supported mechanisms to financial engine. | Reviewer can trace each amount to population/driver/assumption; public-only hypotheses remain unsized when evidence lacks; at least one genuine negative result from a documented test; no required count of positive opportunities. | 1.5–2.5 days, Codex. |
| CE-07 / P1 | Evidence request pack for a future permissioned operating pilot; CE-06. Templates, minimum columns, anonymization guidance and reconciliation requests. | Exported pack answers who provides what and why; no live source connection needed; no request for broad dumps unrelated to a thesis; rejects mixed/unreconciled periods. | 0.5–1 day, Codex. User only introduces authorized company sponsor if a real pilot is pursued. |
| CE-08 / P1 | Public case release verification and reviewer packet; CE-06. | Source-to-claim checks, no licensed rows/charts, no unsupported savings/adoption claims, deliberately contradicted evidence changes decision, replay from clean public inputs, rejected/deferred hypotheses shown in memo. | 1–1.5 days, Codex. Independent practitioner comments only when available; never substitute a model for that person. |

Total within this workstream: approximately 11–17.5 focused days. CE-02 and CE-04 can proceed independently after CE-01; CE-03 follows CE-02; CE-05 then unlocks CE-06. A credible public diligence memo can ship after CE-01–04 before the constructed operating extension. Do not make public portfolio progress contingent on a private-company data introduction.

## Defer or reject

Reject presentation of a public margin gap as cost-out potential; claimed product profitability without disclosed segment data; invented Progress customer evidence; automatic promotions from signed/hashes to high-confidence causal proof; realized savings claims from simulations; and uncalibrated likelihood percentages described as probabilities.

Defer additional companies, vendor integrations, scraped alternative data, elaborate benchmark regressions, broad procurement/working-capital modules and production deployment until the one-company thesis can survive a skeptical review. Existing infrastructure is sufficient to begin this phase.

The completion demonstration is a traceable discussion: here is what the public record establishes, here is what remains unknown, here is a constructed mechanism test, here is a hypothesis we rejected, and here is the exact operating evidence needed before a management team could approve spending or claim value.
