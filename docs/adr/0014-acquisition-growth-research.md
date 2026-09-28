# ADR 0014: Acquisition contribution, revenue mix and research assessments

Status: accepted for the public research case, September 28, 2026.

## Problem and decision

Reported revenue growth alone cannot distinguish an acquired business from the
remaining business. A numerical residual also cannot identify organic growth,
pricing headroom or removable costs. Extend the existing public baseline with an
optional, typed growth context bound to the exact financial bundle fingerprint.
Keep the original 241 financial facts and their source mappings unchanged.

`public-growth-bridge/1` compares consecutive same-currency annual periods from one
reviewed filing. Acquisition contributions reference the original revenue fact IDs,
their disclosure, units, currency, precision and approximate classification. Public
source and filing-hash gates cover the nested revenue mix as well as the main bundle.
The context has its own fingerprint; research edits change it without changing the
financial input fingerprint.

## Economic meaning

For Progress FY2025 versus FY2024, reported revenue increases by $224.422 million.
The disclosed approximate ShareFile contributions increase from $21.1 million to
$261.6 million, a $240.5 million contribution change. Subtraction leaves an
approximately $16.1 million decline in revenue excluding ShareFile, approximately
2.2% of the prior residual revenue. This is not ShareFile growth or organic growth.
The residual still includes FX, Nuclia, product/service mix and renewal timing.

The engine retains central-value arithmetic using the published rounded inputs for
reproducibility. The executive exhibit displays contribution and residual amounts
at the coarsest supplied source resolution, $0.1 million here. Extra subtraction
digits are not extra source precision. No statistical confidence interval or exact
FX-dollar bridge is inferred from rounded disclosure. A zero residual denominator
produces an unavailable growth rate. Acquired earnings and organic growth remain
explicitly unavailable; no margin, EBITDA or synergy plug fills those fields.

The separate Note 12 extraction contains 15 source facts: four revenue components
and total revenue for three years. Each total and each overlapping original fact
must match the financial bundle; all four components must sum to that total.
Incomplete components, shifted periods, foreign currencies, negative components,
unregistered sources and incompatible revisions fail before export. SaaS revenue
is a period flow, not an ARR balance.

## Facts and judgments

`Disclosure` separates issuer summaries from analytical limits and identifies
unaudited pro forma context. Pro forma evidence cannot be used as the reported
acquisition contribution. The source document URL, accession, file hash and page
locators remain inspectable. Short text anchors locate reviewed source passages;
they do not prove the correctness of a paraphrase or constitute an automated
semantic review.

`ResearchAssessment` requires a mechanism, population, supporting context,
counterevidence, alternative explanations, required evidence, a falsification or
reopening test and review date. Dispositions are investigate, defer or reject.
These are authored research judgments, not algorithmically established causal
claims or management decisions. No operating approval, KPI activation, company
assignment or savings amount follows from them. The initial four assessments:

- Investigate the quality of reported growth after explaining the residual.
- Defer broad pricing action without eligible contract/cohort economics.
- Reject termination of the disclosed TSA as a new saving: it already ended.
- Defer an integration/automation cost-out claim without a removable cost pool.

The file and its fingerprint version these assessments. This increment does not
add a mutable review API or claim actual human acceptance. Dedicated case-review
receipts remain the separate mechanism described in ADR 0013.

## Replay and verification

```powershell
uv run pvc public-diligence --input data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --output var/public-diligence/baseline
uv run python scripts/verify_growth_source.py --pdf var/public-diligence/sources/progress-2025-10k.pdf
```

The first command is offline and needs no vendor access. The second needs the
research extra and the exact locally downloaded issuer PDF. It re-extracts all 15
mix facts with the reviewed mapping, checks disclosure anchors and reconciles the
result to the original financial case. PDF pages 25, 26, 52, 53, 54 and 63 were
visually inspected. The issuer's pro forma presentation stays in context only.

Tests cover independently worked arithmetic, source/currency/period/perimeter
rejections, precision, zero denominator, reconciliation including offsetting
component changes, private-source export isolation, research authority, changed
fingerprints, HTML escaping and input overwrite protection. CI renders the enriched
baseline from both the checkout and installed package and checks desktop, tablet
and phone layouts.

Metric-specific peer eligibility, a complete organic bridge where disclosures
permit one, reviewed commercial conclusions, maintainable earnings adjustments,
the full executive memo and actual operating evidence remain further work. The
absence of an organic disclosure is an explicit finding, not permission to invent
one to finish a roadmap ticket.
