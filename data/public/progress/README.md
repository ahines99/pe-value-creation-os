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

Reproduce the baseline without a network or vendor account:

```powershell
uv run pvc public-diligence --input data/public/progress/annual-facts.json --output var/public-diligence/baseline
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
headlines rather than being silently plugged. No operating savings are claimed.

These are comparative facts as presented in this filing. They are not a claim
that the same facts were known in 2023 or 2024. The original publication date,
retrieval time, extraction version and mapping hash remain distinct.
