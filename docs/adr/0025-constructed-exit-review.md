# ADR 0025: An explicit exit review without a proceeds claim

Status: accepted for the constructed research exercise, September 28, 2026.

## Decision and scope

Add a composed schema-3 case payload to the existing immutable revision ledger.
It contains the unchanged schema-2 operating-source contract, the public facts
and historical valuation inputs, and explicit exit assumptions. Existing schema-1
and schema-2 serialized payloads retain their hashes. No database migration is
needed: the existing typed JSONB revisions, concurrency checks, audit, tenant
scope, review receipts and retention/export paths apply.

New exit writes require a saved source-backed ownership/exit parent and an
authored effective date equal to the operating horizon end. It cannot silently
discard its source or valuation basis in a later revision. A simulated review
accepts research arithmetic; it cannot authorize a sale or establish ownership.
Older schema-1/2 exit-stage markers remain readable with their original hashes;
they do not acquire an exit calculation retroactively.

The demonstration extends original underwriting, hypothetical close, operating
review, source challenge and vendor correction with a sixth revision and its
simulated review. The frozen close, source accounting, attribution claims and
operating forecast are preserved. Another multiple assumption produces another
signed revision; it does not overwrite the first exit review.

The executive packet consumes this sixth revision through memo schema 4. It
recomputes both the source forecast and exit sensitivity before accepting the
stored results; older source-only packets retain schema 3 compatibility.

## Two economic scopes stay separate

The company-level sensitivity uses the historical FY2025 calculated EBITDA and
the previously disclosed debt/cash/claim convention. It applies explicitly
authored 0.9/1.0/1.1 earnings factors and 4x/6x/8x/10x multiples around an assumed
8x starting mark. These are sensitivity coordinates, not a post-Domo forecast,
market comparables, probability estimates or an IPEV fair-value opinion.

The earnings definition remains the existing public bridge, not a new normalized
or issuer-adjusted measure. Historical claim inputs are held constant. They do
not describe an actual entry transaction or future payoff, and partial operating
cash does not automatically reduce debt or increase available cash.

The constructed operating records cover scoped pools rather than consolidated
accounts. Their forecast is displayed separately and never added to company
exit earnings. The corrected base case ends with zero vendor cost removal and
monthly incremental EBITDA of −8,500 after recurring costs. Expired contract
terms and missing cost-release evidence cannot support a perpetual uplift.
Maintainable annual operating uplift therefore remains unavailable.

## Reconciled arithmetic and evidence boundary

```text
change in EV = starting multiple × earnings change
             + starting earnings × multiple change
             + earnings change × multiple change
             + explicit rounding residual

equity sensitivity = EV + available cash + nonoperating assets
                   − debt principal − selected lease claims
                   − other claims − assumed transaction costs
```

Every row reconciles. Negative equity residuals remain visible; nonpositive or
unavailable earnings withhold dependent multiple values. Multiple effects and
interaction remain investment-level calculations, never operating attribution.
Actual transaction proceeds, shareholder distributions, exit date and investment
returns remain null. The equity residual is a mechanical sensitivity, not a
fair-value measure or cash settlement result.

For context, the [2025 IPEV Guidelines](https://www.privateequityvaluation.com/Valuation-Guidelines)
distinguish enterprise allocation and multiple selection (sections 2.4 and 3.4).
Their transaction-cost discussion (5.14) also explains why a net cash illustration
must not be presented as fair value. This project does not claim compliance or
independent valuation review.

## Verification and remaining work

Tests exercise the signed decomposition, negative residuals, missing earnings,
nonpositive earnings, public-input binding, private-source rejection, date/stage
constraints, unchanged accounting and close baseline, successive exit revisions,
tenant scope, old hash compatibility and rendered output. The repository tests
run against both in-memory and disposable PostgreSQL implementations. Installed
package CI runs `pvc exit-review-demo`; browser checks inspect the exhibit at
desktop, tablet and phone widths.

This supplies the narrow constructed exit scenario in OP-15. It does not complete
initiative/KPI split lineage, a consolidated maintainable-earnings forecast,
publication-time reconstruction, independent executive review or an actual
company pilot. Actual settlement, ownership/dilution, taxes, costs and distribution
evidence are still required for any proceeds or return claim.
