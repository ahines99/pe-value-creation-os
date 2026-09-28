# ADR 0015: Public peer context by metric

Status: implemented, September 28, 2026. This is research context, not an
independent financial review or a management-approved savings benchmark.

The Progress case needs comparable questions, not a single peer list that implies
every company is comparable on every metric. The selection dossier records
candidate rationale, disclosure evidence, metric-specific inclusion/exclusion and
a stricter-cohort sensitivity before computing medians. The discovery rules were
recorded before numeric comparison; this is a small purposive sample, not the
complete software universe or a representative industry benchmark.

## Sources and period selection

The committed maps reproduce 93 comparative statement facts from PTC FY2025,
OpenText FY2025 and Descartes FY2026. Three additional Progress cash-flow net-income
facts reconcile the focal cash measure without rewriting its original 241 facts.
Raw issuer PDFs stay outside the repository; maps, factual rows, source hashes,
filing identity, dates and brief reviewed interpretations are public. No WRDS or
LSEG extract enters this exhibit. Code licensing does not relicense issuer reports.

Underlying filing identities are independently checked against the
[PTC index](https://www.sec.gov/Archives/edgar/data/857005/000119312525291326/0001193125-25-291326-index.htm),
[OpenText index](https://www.sec.gov/Archives/edgar/data/1002638/000100263825000053/0001002638-25-000053-index.htm)
and [Descartes 40-F index](https://www.sec.gov/Archives/edgar/data/1050140/000110465926026450/0001104659-26-026450-index.html).
Hashes identify the exact issuer-hosted annual-report PDFs, not byte identity
with EDGAR HTML. Descartes financials accompany its 40-F; it is not relabeled 10-K.

Choose the annual period closest to the focal November 30, 2025 end, within 183
days and with duration differing by at most seven days. A latest-end tie breaker
is deterministic. Dates, not fiscal-year labels, govern: Descartes FY2026 ends
January 31, 2026 and is closer than FY2025. Sources must be public, USD, US GAAP
and filed by the shared September 28, 2026 cutoff. No currency translation or
quarter annualization is inferred.

## Definitions and judgments

GAAP operating margin is reported operating income divided by revenue. Revenue
less cost of revenue must reconcile to gross profit; gross profit less operating
expenses must reconcile to operating income. Descartes' five named expense
components are summed explicitly because its displayed expense total is unlabeled.
Acquired-intangible amortization is included in GAAP operating income, irrespective
of whether classified above or below gross profit. Gross margins are not compared.

Cash context is reported operating cash flow plus signed PP&E purchases, divided
by revenue. Cash-flow net income must match income-statement net income. This is
not complete free cash flow, cash available to equity or an initiative benefit.
Missing inputs, positive purchase outflows or reconciliation differences withhold
the dependent metric. A cash mismatch does not erase a valid operating margin.

PTC's upfront license recognition and CAD/PLM exposure make it context-only.
Descartes' transaction/subscription services mix makes it context-only. OpenText's
adjacent information-management exposure and full FY2025 period after AMC disposal
permit narrower **reported operating-margin** context; this is an author judgment,
not normalized earnings. None qualifies for the stricter cash cohort because
complete cash-investment classifications have not been reconciled. Its capitalized
development disclosure is one concrete reason to retain this limitation.

SS&C was considered but issuer PDF retrieval failed twice. Its filing link and
exclusion remain visible; it contributes no numbers. No financial hashes or facts
are invented to complete a peer set. All four candidates are excluded from organic
growth and ARR comparisons until common definitions and perimeter bridges exist.

All-eligible and strict medians require three observations. The released strict
operating cohort has one observation and strict cash has zero: both medians are
withheld. Three is a display floor, not statistical validation. The calculator
does not turn any ratio difference into dollars of savings, an operating target
or a valuation. Original evidence and selection rationales remain inspectable.

## Reproduction and acceptance

`pvc public-diligence` accepts `--peers data/public/progress/peer-context.json` in
addition to the existing `--input` and `--growth` arguments. Context is bound to
the exact original fact-bundle hash. Source restrictions and contracts are checked
before creating output files. The optional context preserves existing callers.

See [source replay instructions](../../data/public/peers/README.md).
`verify_peer_sources.py` re-extracts all 96 rows and checks disclosure anchors
against exact local PDFs; locating an anchor does not independently validate the
interpretation or cohort judgment. Financial source pages were visually inspected.

`filing-pdf/3` adds an explicit header-page-number location. Footer-only mappings
retain version 2 and their previous canonical serialization and hashes. Both
locations fail closed on changed page labels. This does not relax numeric row
matching, source hashing, entity headings or column checks.

Tests exercise independent ratios, insufficient samples, per-metric exclusions,
missing and mismatched inputs, calendar/duration/currency failures, private source
rejection, exact-bundle binding, public escaping, immutable input files and 40-F
header mapping. Browser coverage includes desktop, tablet and phone widths,
keyboard disclosure access and expanded-table overflow. Peer judgments and the
executive interpretation still need independent practitioner challenge.
