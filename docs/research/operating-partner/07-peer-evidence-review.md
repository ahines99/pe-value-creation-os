# Peer evidence disposition: SS&C source review

September 29, 2026. Research-author review; not independent finance approval.
The selected information cutoff remains September 28, 2026. Retrieval on the
following day does not claim that our system possessed the document earlier.

## Finding and decision

The previously selected SS&C candidate now has a verified issuer PDF and 30
mapped financial facts. Retain its reported operating margin and PP&E-only cash
ratio as context. Do not admit it to the strict cohort or infer organic growth,
ARR growth, addressable savings or an operating target from these statements.

The [issuer FY2025 Form 10-K](https://investor.ssctech.com/static-files/8d784cd6-7a12-4eaf-a8a6-8f7672e2fb2b)
and [SEC filing index](https://www.sec.gov/Archives/edgar/data/1402436/000119312526076745/0001193125-26-076745-index.htm)
identify the December 31, 2025 period and February 26, 2026 filing. The source
SHA-256 is `da30345eaee3f0177917144ff957dfcde153674163cab12eb0aebca983474a61`.
Raw reports remain local; the public map preserves units, signs and page locators.

## Evidence and analytical consequence

| Question | Reviewed evidence | Disposition |
|---|---|---|
| Do the operating statements reconcile? | Page 59: revenue less cost equals gross profit; gross profit less expenses equals operating income for each of three years. | Accept reported GAAP ratios as contextual facts. |
| Is the business mix matched? | Page 59 separates software-enabled services from license/maintenance; page 62 describes financial-services and healthcare exposure. | No matched operating-cost benchmark. |
| Does CFO less PP&E represent complete investment-adjusted cash? | Page 60 separately reports capitalized software outflows; page 64 describes software capitalization. | Preserve the defined proxy, explicitly not free cash flow. |
| Can all cash balances fund corporate activity? | Pages 60 and 65 identify restricted client funds; related obligation movements are financing flows. | Do not equate total cash-flow closing cash with available corporate cash or add client flows to CFO. |
| Is consolidated growth organic? | Page 73 places Calastone in the consolidation perimeter during FY2025. | Exclude organic and ARR comparisons without common definition/perimeter bridges. |

The page 59 income statement and page 60 cash-flow statement use the same
consolidated net income, rather than net income attributable to common holders.
The map retains the separate software-investment row without silently changing
the cash metric used for the other candidates.

## Effect on the recommendation

The four-candidate contextual operating-margin median is 25.9%, versus 28.8%
before SS&C's source became available. The contextual PP&E-only cash median is
28.9%, versus 31.3%. These are calculations from the selected filings, not issuer
claims or representative industry estimates. Strict operating-margin eligibility
still has one candidate; strict cash eligibility has none. Both strict medians
remain withheld under the unchanged three-observation floor.

The recommendation remains bounded commercial and operating diligence. No new
savings case is created. A different software/services mix and investment policy
can explain part of a reported margin difference; finance and operating records
are needed before attributing any difference to remediable performance.

## Reproduction and open evidence

`scripts/verify_peer_sources.py` now reproduces 126 facts including the Progress
supplement and checks ten disclosure anchors against the exact local PDFs.
The financial tables and relevant disclosure pages were also inspected visually.
The public baseline and three executive memos bind the reviewed context hash;
the operating cases, frozen approvals and historical claims are not revised.

The extraction map's `header` setting describes the first extracted text line;
SS&C's printed page number is visually a footer. This is a documented text-order
property, not a claim that the filing's visual layout changed.

Remaining peer questions are common investment definitions, comparable business
populations, organic-growth bridges and practitioner challenge. Source retrieval
is closed for the four selected candidates; economic comparability remains
limited. Candidate inclusion is not expanded merely to produce a strict median.
