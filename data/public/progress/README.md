# Public Progress financial facts

These are public reported facts, independently extracted from [Progress's FY2025
Form 10-K](https://investors.progress.com/static-files/2a74fac9-6513-42b2-b875-51cb2da6021c).
The [SEC filing index](https://www.sec.gov/Archives/edgar/data/876167/000087616726000008/0000876167-26-000008-index.htm)
identifies the January 20, 2026 filing and November 30, 2025 annual period.
No WRDS/LSEG extract or private operating schedule is included.

- `fy2025-map.json`: reviewed rows, units, comparative columns, PDF page numbers,
  printed page numbers and expected source SHA-256.
- `annual-facts.json`: 81 facts, preserving original amounts and signed cash
  outflows; source thousands are explicitly separate from normalized dollars.
- `fy2026-q1-map.json` / `fy2026-q1-facts.json`: 58 reported facts from the
  [March 31, 2026 10-Q](https://investors.progress.com/static-files/d9d7dc10-3cea-4b4d-a5af-52d5505eff81).
- `fy2026-q2-map.json` / `fy2026-q2-facts.json`: 102 reported facts from the
  [June 30, 2026 10-Q](https://investors.progress.com/static-files/214c980f-8e95-4d8c-b878-f1569502f2f5).
- `context-events.json`: a reviewed, source-hashed event from the
  [September 22, 2026 acquisition 8-K](https://investors.progress.com/node/28981/html),
  with reported facts and analytical implications in separate fields.
- `financial-facts.json`: assembled case inputs preserving all 241 source facts
  and their versions. Calculated quarters are not fabricated as reported facts.

Reproduce the baseline without a network or vendor account:

```powershell
uv run python scripts/build_public_case.py
uv run pvc public-diligence --input data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --output var/public-diligence/baseline
```

To verify extraction, install the research extra, retrieve the public PDF linked
above, and run the extractor with the actual retrieval timestamp. The expected
PDF SHA-256 is `f5227b4aac09542c5acccc8264a0b975f1db25e1891108ededd5df96cd1709c1`.
Different bytes require a new reviewed mapping, not removal of the hash guard.

```powershell
uv sync --extra research
uv run python scripts/extract_public_filing.py --pdf <downloaded-file.pdf> --mapping data/public/progress/fy2025-map.json --retrieved-at <actual-ISO-8601-UTC-time> --cutoff 2026-09-28 --output var/public-diligence/reextracted.json
```

The initial PDF was retrieved September 28, 2026 at 13:39:25 UTC. Its income and
cash-flow table pages were rendered and visually inspected. A direct SEC
companyfacts request returned HTTP 403; extraction used the accessible issuer
filing instead. The extractor itself performs no network access.

Calculated EBITDA uses net income + tax provision + interest expense + operating
depreciation/amortization. It is not issuer-adjusted EBITDA or a maintainable
earnings opinion. Debt amortization is already part of interest expense and is
not added again. Operating income plus D&A and CFO less PP&E purchases are
separately named measures. Historical amortization differences block dependent
earnings measures rather than being silently plugged. Independently supported
cash measures remain available. No operating savings are claimed.

These are comparative facts as presented in this filing. They are not a claim
that the same facts were known in 2023 or 2024. The original publication date,
retrieval time, extraction version and mapping hash remain distinct.

Quarter mappings use explicit repeated-header occurrences and period groups.
Extraction v2 IDs contain start, end and basis. The original annual v1 records
remain unchanged; re-extracting with v2 creates versioned provenance rather than
claiming byte-identical v1 output. Q1 and Q2 income/cash pages were rendered and
visually reviewed. Their source SHA-256 values are:

- Q1: `8311992f98a337a4c7ba5af9d4709837fce9f7e08c09c791ff84c77f06fd0d78`
- Q2: `0b9e73fba989801c4d734a2e032026bd4d3235d0799ff8aecf4d878cf45db9c6`

Q2 cash/D&A is a separately labeled YTD-minus-Q1 calculation with both fact IDs.
The source income statements must reconcile and reproduce the separately reported
quarter before subtraction is accepted. Missing inputs, restatement differences,
wrong signs and mixed currencies block the affected calculation. The 2025
comparative amortization difference remains an explicit accounting question.

The dated acquisition event is not folded into historical figures. No post-deal
pro forma baseline, synergies or later-than-cutoff disclosure is inferred. See
[ADR 0011](../../../docs/adr/0011-quarterly-source-and-perimeter.md).

## Acquisition contribution and commercial research

`growth-context.json` adds the approximate ShareFile contribution disclosures,
nine reviewed disclosure notes and four authored research assessments. It also
contains a separately extracted 15-fact revenue disaggregation from Note 12,
using `revenue-mix-map.json`. The original 241-fact financial registry is unchanged;
overlapping values and annual component sums must reconcile before export.

The FY2025/FY2024 revenue increase is $224.422 million; the approximate ShareFile
contribution increase is $240.5 million. The remaining change is approximately
negative $16.1 million (negative 2.2%). This residual is not organic growth and
retains FX, Nuclia, mix and timing. Unaudited pro forma revenue stays separate;
ShareFile earnings and exact organic growth remain unavailable. SaaS revenue is
not ARR. No public operating opportunity is sized from these disclosures.

The assessments investigate growth quality, defer broad pricing and cost-out
claims, and reject cancellation of the already terminated ShareFile TSA as a new
saving. Each retains its supporting context, counterevidence, alternatives and the
test that could change the judgment. These are research-author assessments, not
management approvals or independent practitioner reviews.

Verify against the same exact downloaded FY2025 PDF:

```powershell
uv run python scripts/verify_growth_source.py --pdf var/public-diligence/sources/progress-2025-10k.pdf
```

This checks the source hash, re-extracts the mix and verifies source anchors.
Anchors locate manually reviewed paragraphs rather than validating their meaning.
Pages 25, 26, 52, 53, 54 and 63 were visually inspected. See
[ADR 0014](../../../docs/adr/0014-acquisition-growth-research.md) for precision,
research authority and remaining work.

## Point-in-time cash, debt and lease facts

`fy2025-balance-map.json` and `balance-facts.json` add 13 facts as of November 30,
2025, from the same exact FY2025 10-K, PDF/printed pages 37 and 55. They are
point-in-time records, separate from the 241 duration facts. The mapping retains
the original document identity and records its own extraction hash. Both source
pages were visually inspected; comparative dashes are not interpreted as zero.

```powershell
uv run python scripts/verify_balance_source.py --pdf var/public-diligence/sources/progress-2025-10k.pdf
uv run pvc historical-valuation --facts data/public/progress/financial-facts.json --balances data/public/progress/balance-facts.json --spec data/constructed/progress/historical-valuation.json --output docs/portfolio/historical-valuation
uv run pvc decision-memo --brief data/constructed/progress/decision-brief.json --facts data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --peers data/public/progress/peer-context.json --underwriting data/constructed/progress/underwriting.json --operating-plan data/constructed/progress/operating-plan.json --balances data/public/progress/balance-facts.json --valuation data/constructed/progress/historical-valuation.json --output docs/portfolio/decision-memo
```

Cash is 94.807 million; total debt principal is 1,410.000 million, versus net
carrying value of 1,400.349 million. Five debt checks must reconcile. Assumed
multiples, available cash, lease treatment, other claims and fees live in the
separate constructed specification. The historical equity sensitivity is not
current value, a post-Domo capital structure, per-share pricing or transaction
proceeds. See [ADR 0017](../../../docs/adr/0017-historical-equity-bridge.md).
