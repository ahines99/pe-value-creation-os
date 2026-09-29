# Reviewed public peer inputs

Each `*-map.json` selects exact financial rows and comparative columns from an
issuer annual-report PDF. The matching `*-facts.json` preserves reported units,
signs, source rows, periods and hashes. The public Progress peer context embeds
these bundles plus metric-specific selection judgments. This directory contains
public filing facts; it contains no licensed vendor extract or raw annual report.

| Candidate | Annual end selected | Source rows | Financial PDF pages | Filing |
|---|---|---:|---|---|
| PTC | 2025-09-30 | 27 over three years | 55, 57 | 10-K, filed 2025-11-21 |
| OpenText | 2025-06-30 | 27 over three years | 144, 147 | 10-K, filed 2025-08-07 |
| Descartes | 2026-01-31 | 39 over three years | 52, 55 | 40-F, filed 2026-03-11 |
| SS&C | 2025-12-31 | 30 over three years | 59, 60 | 10-K, filed 2026-02-26 |
| Progress supplement | 2025-11-30 | 3 over three years | 41 | Same registered FY2025 10-K as original baseline |

Source URLs, hashes and locators are in the maps. SS&C was retrieved and reviewed
on September 29; its services mix and software investment make it context-only.
No candidate can enter the calculation without mapped source facts. The [ADR](../../../docs/adr/0015-metric-specific-peer-context.md)
explains the deliberately limited comparison and withheld medians.

Replay the public exhibit without a vendor account or network request:

```sh
uv run pvc public-diligence --input data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --peers data/public/progress/peer-context.json --output docs/portfolio/progress-baseline
```

To verify extraction, obtain the exact issuer PDFs referenced in the maps through
an authorized route. Save them in a local ignored directory as `ptc-2025.pdf`,
`opentext-2025.pdf`, `descartes-2026.pdf` and `ssc-2025.pdf`; retain the original Progress PDF
separately. Then run:

```sh
uv run python scripts/verify_peer_sources.py --pdf-directory var/peer-sources --focal-pdf var/public-diligence/sources/progress-2025-10k.pdf
```

The verifier checks exact byte hashes, re-extracts all 126 facts, compares both
standalone and embedded bundles, locates ten reviewed disclosure anchors and
validates the analysis contract. A changed source requires a reviewed new mapping,
not replacing a hash merely to bypass validation. Do not publish raw reports or
licensed data under the code's Apache-2.0 license.

SS&C uses USD millions rather than thousands. Its mapped software investment
outflows remain separate from the existing PP&E-only cash measure. The PDF page
number appears first in extracted text despite its visual footer position, so its
map uses the extractor's `header` text-line check. Financial tables and referenced
disclosures were visually reviewed; no numeric parsing rule was relaxed.
