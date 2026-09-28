# ADR 0024: Preserve public disclosure vintages and withhold unsupported timing

Status: accepted for the public research implementation, September 28, 2026.

## Decision

Keep two ShareFile purchase-price allocations as separate immutable typed inputs:
the preliminary allocation in Progress's FY2024 10-K and the final allocation in
its FY2025 10-K. Each retains its accession, issuer PDF hash, mapping hash, page,
row text, reported units and extraction version. Components reconcile to the
reported total within each version before any comparison is produced.

The issuer describes measurement-period adjustments. We classify that revision
explicitly and do not call it an accounting-error restatement. This supplies a
real historical revision example but does not close OP-16's literal restatement
requirement or prove a full point-in-time public information set.

An acceptance selector excludes filings accepted after its cutoff. A distinct
public-availability selector requires timestamp evidence; missing evidence for an
otherwise relevant filing withholds the selection instead of falling back to an
older known value. Both require timezone-aware times. Acceptance and retrieval
never populate the availability field automatically. Any future evidence-based
availability selection covers only registered sources, not a complete market
information set.

The [SEC's timestamp guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions)
says the website has no first-availability timestamp. The two January acceptance
records are represented with the documented EST offset. Their publication fields
remain null. No assumed one-minute delay, midnight date, vendor cache timestamp
or today's PDF download establishes historical availability.

## Evidence and financial consequence

The [FY2024 filing](https://www.sec.gov/Archives/edgar/data/876167/000087616725000010/prgs-20241130.htm)
and [FY2025 filing](https://www.sec.gov/Archives/edgar/data/876167/000087616726000008/prgs-20251130.htm)
give nine allocation rows apiece. The total changes from $852.702 million to
$853.897 million. The signed component differences reconcile to $1.195 million.

These acquisition-accounting amounts do not become operating savings. The
exhibit routes the changed intangible balance to amortization diligence and
requests closing/settlement evidence for transaction cash timing. Existing
historical financial facts, EV-to-equity assumptions and constructed operating
forecasts remain separately versioned.

## Reproduction

```powershell
pvc disclosure-history --input data/public/progress/sharefile-allocation-history.json --output docs/portfolio/disclosure-history
python scripts/verify_allocation_sources.py --original-pdf var/public-diligence/sources/progress-2024-10k.pdf --revised-pdf var/public-diligence/sources/progress-2025-10k.pdf
```

Download the issuer PDFs at the URLs registered in the JSON to the supplied local
paths before running the offline source verifier. The verifier checks file and
mapping hashes, issuer identity, headings, units, exact row text, amounts and
intangible useful-life columns. The public report builds offline from the reviewed
facts; ordinary tests do not silently fetch a newer source.

Tests cover exact-cutoff selection, missing availability, later-file exclusion,
same-entity/units requirements, source classification, reconciliation, immutable
inputs, rendering escaping, output collisions and committed-output consistency.
Browser checks cover the cutoff results and exhibit at three widths. Source PDF
tables were also visually inspected; these checks do not assert an exhaustive
search of intermediate disclosures or actual investor access at acceptance time.
