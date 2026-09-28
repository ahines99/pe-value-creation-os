# Public-company research pilot

This is the first real-data validation lane for the portfolio project: a private,
academic financial-statement study of one software company and a small candidate
peer group. It tests ingestion, source reconciliation, deterministic analysis and
the usefulness of an executive diligence memo. It does not establish that a
portfolio company adopted a plan or achieved value creation.

The [operating-company pilot](pilot-plan.md) is a later stage. Its production
controls and company data-access requirements remain applicable to that stage;
this local research study neither satisfies nor changes them.

## Implemented workflow

1. Read an existing authorized local Compustat Parquet cache without vendor login,
   network calls, source-system writes or importing another project's runtime.
2. Keep `INDL / STD / D / C` rows. Preserve annual and discrete quarterly records
   separately, native reporting currency and financial amounts in millions.
3. Preserve source file SHA-256, original zero-based row index, entity identifier,
   reporting date, vintage and availability timestamp. Reject identity collisions
   and conflicting financial rows with the same vintage.
4. Exclude future reporting dates, vintages and availability dates. Select complete
   rows from the newest eligible revision, without filling missing fields from
   older revisions. This remains **current-vintage retrospective research**;
   availability timestamps do not turn it into an as-filed historical backtest.
5. Use the focal company's explicit annual anchor date. For each peer, select the
   nearest same-currency annual period within 183 days; earlier date wins a tie.
   Disclose exact dates and business-model differences. This is an analyst-selected
   comparison set, not a representative statistical industry sample.
6. Calculate revenue growth and standardized expense/margin ratios using Decimal
   arithmetic. Growth requires the prior fiscal year, same quarter if quarterly,
   same currency and a 330–400-day interval. Missing values remain missing. Peer
   medians exclude the focal company and require at least three usable values.
7. Compare supplied issuer figures plus documented accounting bridges to the
   standardized fields. The absolute matching tolerance is 0.001 million.
8. Produce a standalone HTML memo and JSON calculation/evidence record under
   ignored `var/research-pilot/`. The memo includes source definitions, candidate
   peers, history, illustrative sensitivities, open issues and a 100-day diligence
   agenda. It creates no operational approvals, initiatives or KPI subscriptions.

## Run locally

Install the optional extraction dependency with `uv sync --extra research`; the
development extra also includes it. The report engine itself requires only the
ordinary package dependencies. The extraction script can alternatively run in an
existing environment with PyArrow installed, without modifying that environment.

Create `var/research-pilot/config.json` with this structure. Replace the fictional
identifiers with an explicitly chosen company and peer list. Do not put passwords
or API keys in this file.

```json
{
  "focal_ticker": "TEST",
  "anchor_period_end": "2025-12-31",
  "first_year": 2021,
  "peers": [
    {"ticker": "AAA", "rationale": "Explain business comparability", "limitation": "Explain material differences"},
    {"ticker": "BBB", "rationale": "Explain business comparability", "limitation": "Explain material differences"},
    {"ticker": "CCC", "rationale": "Explain business comparability", "limitation": "Explain material differences"}
  ],
  "source_notes": ["Document units, definitions and source limitations"],
  "open_items": ["Independent source reconciliation and peer review pending"],
  "reconciliations": []
}
```

```powershell
python scripts/extract_research_cache.py --cache "D:/authorized-cache/comp" --config var/research-pilot/config.json --as-of 2026-09-27T23:59:59Z --name input
pvc research-pilot --input var/research-pilot/input.json --name memo
```

Use an actual cutoff no later than the time of extraction. The cache must contain
`funda/` and `fundq/` directories. The script scans local files, rejects nonempty
files without required columns, skips empty files and records extraction counts.
Rows lacking a vintage or positive finite revenue are excluded and counted.
The selected scope and source snapshot remain in the private input bundle.

Open `var/research-pilot/memo.html` locally. The companion `memo.json` contains
the normalized selected records, calculations and input checksum. Do not point
the public Pages workflow or an unauthenticated file server at this directory.
The command restricts output paths to the private directory; this is an export
guard, not encryption or a substitute for access control on the workstation.

## Financial interpretation

Compustat provides [standardized financial statements](https://www.marketplace.spglobal.com/en/datasets/compustat-financials-%288%29).
Do not equate its `XSGA` to just sales and marketing, or assume `OIADP` is the
issuer's GAAP operating income. Reconcile the particular company and period to
the issuer's own financial statement. The gross-margin proxy is also subject to
cost classification and depreciation/amortization differences.

The 50/100/150-basis-point sensitivities are explicit hypothetical changes applied
to annual revenue. They are alternatives, not additive initiatives, and exclude
implementation costs, timing, tax, feasibility and cash conversion. They are not
inferred achievable savings or an approved EBITDA forecast. Revenue growth also
includes acquisition and currency effects unless separately bridged.

Fiscal-calendar changes and short/long reporting periods need manual review;
the current contract does not carry statement start dates. No annual-to-monthly
interpolation, quarterly cash-flow differencing, valuation multiple or investment
recommendation is included in this lane.

## LSEG integration boundary

Use LSEG as a second source only after recording field identifier, fiscal-period
end, annual/quarterly/TTM basis, currency, unit scale, observation date and revision
or availability timestamp. A daily observation date is not a financial period.
The existing cache's field names alone cannot establish those definitions.

For the first comparison, reconcile annual revenue for the exact focal period,
then reconcile the profit definition. Never combine standardized EBITDA, GAAP
operating income and company-adjusted EBITDA without an explicit bridge.
If metadata is missing, request a small attended Workspace export with those
fields; do not infer entitlement from configured credentials or start unattended
authentication retries. The implemented report currently uses Compustat only.

## Ownership and completion roadmap

| Stage | Engineering actions | Alex / reviewer actions | Completion evidence |
|---|---|---|---|
| Local research run | Build normalized bundle, private memo, source lineage and reproducibility checks | Review the focal-company choice and candidate peer rationale | Private input checksum and report; candidate selection accepted |
| Accounting review | Supply source bridges; resolve mismatches; make quarterly and cost-of-revenue limitations explicit | Independently recompute key figures; confirm metric definitions | Signed review worksheet with no unexplained material differences |
| LSEG cross-check | Add period-aware normalization after inspecting a small authorized export | Use attended Workspace access if required; confirm permitted use for the extract | Exact-period revenue and profit-definition comparisons, or an explicit documented exclusion |
| PE usefulness review | Revise the memo and diligence questions from feedback | Ask a PE/finance practitioner to score clarity, relevance, evidence and actionability; record disagreements | Reviewer feedback and explicit acceptance, not an automated approval |
| Portfolio case study | Publish code, synthetic regression tests and a permitted narrative; independently sourced public examples where appropriate | Confirm what results, figures and screenshots may be published under the actual data agreements | Public case study accurately distinguishes technical validation from business validation |
| Operating-company pilot | Implement approved source mapping and follow the existing operating-pilot gates | Secure a company sponsor, operational data, approvers and participation terms | Two reviewed diagnostics, a bounded experiment and monitored outcomes |

University access is not a redistribution grant. Keep licensed extracts and derived
reports private while checking dataset-specific terms against
[IU's electronic resource policy](https://libraries.indiana.edu/policies/e-resources-use)
and [WRDS's download and analysis policy](https://wrds-www.wharton.upenn.edu/pages/about/data-download-and-analysis-policy/).
The Apache-2.0 source-code license does not license vendor data.

## Validation

`tests/test_research_pilot.py` uses only fictional values. It covers source extraction,
format filtering, empty files, lineage, revision selection, ambiguous revisions,
entity collisions, future data, currency/date alignment, missing values, growth
periods, accounting bridges, deterministic output, HTML escaping and private
output boundaries. Human acceptance is always recorded as pending by this workflow.
